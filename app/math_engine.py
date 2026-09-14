import math
from statistics import pstdev
from datetime import datetime
from zoneinfo import ZoneInfo
from .models import MarketState, OptionQuote, TradeSignal


IST = ZoneInfo("Asia/Kolkata")


class QuantEngine:
    """Deterministic mathematical signal engine. No EMA, VWAP or LLM in the hot path.

    Evidence is scored softly so the engine does not require every variable to
    agree. Hard entry controls remain EV, execution quality and risk.
    """

    @staticmethod
    def returns(prices: list[float]) -> list[float]:
        return [math.log(b / a) for a, b in zip(prices, prices[1:]) if a > 0 and b > 0]

    @classmethod
    def realized_vol(cls, prices: list[float], periods_per_year: int = 252 * 6 * 60) -> float:
        r = cls.returns(prices[-240:])
        if len(r) < 20:
            return 0.0
        return pstdev(r) * math.sqrt(periods_per_year)

    @staticmethod
    def normal_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    @classmethod
    def probability_above(cls, spot: float, level: float, vol: float, minutes: float) -> float:
        if spot <= 0 or level <= 0 or vol <= 0 or minutes <= 0:
            return 0.5
        t = minutes / (252 * 375)
        sigma = vol * math.sqrt(t)
        if sigma <= 0:
            return 1.0 if spot > level else 0.0
        d2 = (math.log(spot / level) - 0.5 * sigma * sigma) / sigma
        return cls.normal_cdf(d2)

    @staticmethod
    def intrinsic(spot: float, strike: float, option_type: str) -> float:
        return max(0.0, spot - strike) if option_type == "CE" else max(0.0, strike - spot)

    @classmethod
    def fair_value_proxy(cls, state: MarketState, q: OptionQuote) -> float:
        """Research baseline only; not a calibrated production option-pricing model."""
        rv = cls.realized_vol(state.spot_history)
        iv = q.iv / 100.0 if q.iv > 1 else q.iv
        vol = max(iv, rv, 0.05)
        distance = abs(state.spot - q.strike)
        time_factor = math.sqrt(30 / (252 * 375))
        time_value = state.spot * vol * time_factor * 0.40
        return cls.intrinsic(state.spot, q.strike, q.option_type) + time_value * math.exp(
            -distance / max(state.spot * 0.02, 1)
        )

    @staticmethod
    def _score(mispricing: float, probability: float, iv: float, rv: float,
               oi_change: float, oi: float, volume: float, delta: float) -> float:
        """Soft evidence score. Components rank candidates; they are not gates."""
        valuation = max(0.0, min(25.0, 12.5 + 25.0 * mispricing))
        probability_score = max(0.0, min(20.0, 40.0 * (probability - 0.50)))
        if rv > 0 and iv > 0:
            ratio = iv / rv
            volatility = max(0.0, 15.0 - abs(math.log(ratio)) * 8.0)
        else:
            volatility = 7.5
        participation = min(15.0, abs(oi_change) / max(oi, 1.0) * 150.0)
        volume_score = min(10.0, math.log1p(max(volume, 0.0)) / 10.0)
        greek_score = min(15.0, abs(delta) * 15.0)
        return valuation + probability_score + volatility + participation + volume_score + greek_score

    @classmethod
    def evaluate(cls, state: MarketState, q: OptionQuote, risk_per_share: float,
                 target_multiple: float = 1.8) -> TradeSignal | None:
        if q.ltp <= 0 or q.bid <= 0 or q.ask <= 0 or q.spread_pct > 0.04:
            return None

        fair = cls.fair_value_proxy(state, q)
        rv = cls.realized_vol(state.spot_history)
        iv = q.iv / 100.0 if q.iv > 1 else q.iv
        vol = max(rv, iv, 0.05)

        # Actual remaining time in the user's trading session (IST).
        now = datetime.now(IST)
        session_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
        session_end = now.replace(hour=15, minute=15, second=0, microsecond=0)
        if now < session_start:
            minutes = 345.0
        else:
            minutes = max(5.0, (session_end - now).total_seconds() / 60.0)

        p_spot = cls.probability_above(state.spot, q.strike, vol, minutes)
        if q.option_type == "PE":
            p_spot = 1.0 - p_spot

        mispricing = (fair - q.ltp) / q.ltp
        probability = min(0.90, max(0.10, 0.50 + 0.20 * (p_spot - 0.50) + 0.20 * max(-0.5, min(0.5, mispricing))))

        stop = max(q.ltp * 0.75, q.ltp - risk_per_share)
        target = q.ltp + (q.ltp - stop) * target_multiple
        win = max(0.0, target - q.ltp)
        loss = max(0.0, q.ltp - stop)
        ev = probability * win - (1 - probability) * loss
        net_ev = ev - q.spread * 0.5 - q.ltp * 0.002
        if net_ev < 0:
            return None

        score = cls._score(mispricing, probability, iv, rv, q.oi_change, q.oi, q.volume, q.delta)
        checks = {
            "Mathematical valuation": fair >= q.ltp,
            "Probability evidence": probability >= 0.55,
            "IV / RV data": iv > 0 and rv > 0,
            "OI activity": abs(q.oi_change) > 0,
            "Volume activity": q.volume > 0,
            "Greeks available": abs(q.delta) > 0 or abs(q.gamma) > 0,
            "Positive net EV": net_ev >= 0,
            "Spread within limit": q.spread_pct <= 0.04,
        }
        signal = TradeSignal(
            action="BUY", option_type=q.option_type, strike=q.strike,
            security_id=q.security_id, symbol=q.symbol, entry=q.ask,
            stop=stop, target=target, quantity=0, probability=probability,
            fair_value=fair, expected_value=ev, net_expected_value=net_ev,
            reason=f"score={score:.1f}/100, prob={probability:.2%}, fair={fair:.2f}, netEV={net_ev:.2f}",
        )
        signal.score = score
        signal.checks = checks
        return signal

    @classmethod
    def best_signal(cls, state: MarketState, min_net_ev: float) -> TradeSignal | None:
        candidates = []
        risk_per_share = max(5.0, state.spot * 0.001)
        for q in state.options.values():
            if q.option_type not in {"CE", "PE"}:
                continue
            s = cls.evaluate(state, q, risk_per_share)
            if s and s.net_expected_value >= min_net_ev:
                candidates.append(s)
        return max(candidates, key=lambda x: (x.net_expected_value, getattr(x, "score", 0.0)), default=None)
