import math
from statistics import mean, pstdev
from datetime import datetime, timezone
from .models import MarketState, OptionQuote, TradeSignal

class QuantEngine:
    """Deterministic first-pass quantitative engine. No LLM in the hot path."""

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
        """Conservative proxy until full calibrated IV surface pricing is added."""
        rv = cls.realized_vol(state.spot_history)
        iv = q.iv / 100.0 if q.iv > 1 else q.iv
        vol = max(iv, rv, 0.05)
        distance = abs(state.spot - q.strike)
        time_factor = math.sqrt(30 / (252 * 375))
        time_value = state.spot * vol * time_factor * 0.40
        return cls.intrinsic(state.spot, q.strike, q.option_type) + time_value * math.exp(-distance / max(state.spot * 0.02, 1))

    @classmethod
    def evaluate(cls, state: MarketState, q: OptionQuote, risk_per_share: float, target_multiple: float = 1.8) -> TradeSignal | None:
        if q.ltp <= 0 or q.bid <= 0 or q.ask <= 0 or q.spread_pct > 0.04:
            return None
        fair = cls.fair_value_proxy(state, q)
        vol = max(cls.realized_vol(state.spot_history), q.iv / 100.0 if q.iv > 1 else q.iv, 0.05)
        # Short-horizon directional probability based on spot-to-strike distance and volatility.
        minutes = max(5.0, (15 * 60) - (datetime.now(timezone.utc).minute % 60))
        p_touch = cls.probability_above(state.spot, q.strike, vol, minutes)
        if q.option_type == "PE":
            p_touch = 1.0 - p_touch
        # Premium discount adds a modest valuation edge; cap to avoid overconfidence.
        mispricing = (fair - q.ltp) / q.ltp
        probability = min(0.90, max(0.10, 0.50 + 0.20 * (p_touch - 0.50) + 0.20 * max(-0.5, min(0.5, mispricing))))
        stop = max(q.ltp * 0.75, q.ltp - risk_per_share)
        target = q.ltp + (q.ltp - stop) * target_multiple
        win = max(0.0, target - q.ltp)
        loss = max(0.0, q.ltp - stop)
        ev = probability * win - (1 - probability) * loss
        net_ev = ev - q.spread * 0.5 - q.ltp * 0.002
        if net_ev < 0:
            return None
        return TradeSignal(
            action="BUY",
            option_type=q.option_type,
            strike=q.strike,
            security_id=q.security_id,
            symbol=q.symbol,
            entry=q.ask,
            stop=stop,
            target=target,
            quantity=0,
            probability=probability,
            fair_value=fair,
            expected_value=ev,
            net_expected_value=net_ev,
            reason=f"prob={probability:.2%}, fair={fair:.2f}, netEV={net_ev:.2f}",
        )

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
        return max(candidates, key=lambda x: x.net_expected_value, default=None)
