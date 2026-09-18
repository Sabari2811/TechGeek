import math
from statistics import pstdev
from datetime import datetime, time
from zoneinfo import ZoneInfo
from .config import CONFIG
from .models import MarketState, OptionQuote, TradeSignal

IST = ZoneInfo("Asia/Kolkata")


class QuantEngine:
    """Deterministic quantitative signal engine.

    VWAP/EMA-style indicators are context only; they are not used as a
    mechanical entry trigger. The engine instead looks for a compressed,
    directionally developing market and then seeks early confirmation.
    """

    @staticmethod
    def returns(prices: list[float]) -> list[float]:
        return [math.log(b / a) for a, b in zip(prices, prices[1:]) if a > 0 and b > 0]

    @classmethod
    def realized_vol(cls, prices: list[float], periods_per_year: int = 252 * 375) -> float:
        r = cls.returns(prices[-240:])
        if len(r) < 20:
            return 0.0
        return pstdev(r) * math.sqrt(periods_per_year)

    @staticmethod
    def normal_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    @staticmethod
    def normal_pdf(x: float) -> float:
        return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

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

    @staticmethod
    def time_to_expiry(expiry: str, now: datetime | None = None) -> float:
        if not expiry:
            return 0.0
        try:
            d = datetime.strptime(expiry, "%Y-%m-%d").date()
        except ValueError:
            return 0.0
        now = now or datetime.now(IST)
        expiry_dt = datetime.combine(d, time(15, 30), tzinfo=IST)
        seconds = max(60.0, (expiry_dt - now).total_seconds())
        return seconds / (365.0 * 24.0 * 60.0 * 60.0)

    @classmethod
    def black_scholes_greeks(cls, spot: float, strike: float, iv: float,
                             option_type: str, expiry: str,
                             risk_free_rate: float | None = None,
                             dividend_yield: float | None = None) -> dict[str, float]:
        sigma = iv / 100.0 if iv > 1.0 else iv
        t = cls.time_to_expiry(expiry)
        if spot <= 0 or strike <= 0 or sigma <= 0 or t <= 0:
            return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

        r = CONFIG.risk_free_rate if risk_free_rate is None else risk_free_rate
        q = CONFIG.dividend_yield if dividend_yield is None else dividend_yield
        sqrt_t = math.sqrt(t)
        d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
        d2 = d1 - sigma * sqrt_t
        nd1 = cls.normal_pdf(d1)
        disc_q = math.exp(-q * t)
        disc_r = math.exp(-r * t)
        is_call = option_type.upper() == "CE"

        if is_call:
            delta = disc_q * cls.normal_cdf(d1)
            theta_year = (-spot * disc_q * nd1 * sigma / (2.0 * sqrt_t)
                          - r * strike * disc_r * cls.normal_cdf(d2)
                          + q * spot * disc_q * cls.normal_cdf(d1))
        else:
            delta = disc_q * (cls.normal_cdf(d1) - 1.0)
            theta_year = (-spot * disc_q * nd1 * sigma / (2.0 * sqrt_t)
                          + r * strike * disc_r * cls.normal_cdf(-d2)
                          - q * spot * disc_q * cls.normal_cdf(-d1))

        gamma = disc_q * nd1 / (spot * sigma * sqrt_t)
        vega = spot * disc_q * nd1 * sqrt_t / 100.0
        theta = theta_year / 365.0
        return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}

    @classmethod
    def ensure_greeks(cls, state: MarketState, q: OptionQuote) -> None:
        if q.iv <= 0 or state.spot <= 0 or not state.expiry:
            return
        if abs(q.delta) > 0 or abs(q.gamma) > 0 or abs(q.theta) > 0 or abs(q.vega) > 0:
            return
        greeks = cls.black_scholes_greeks(state.spot, q.strike, q.iv, q.option_type, state.expiry)
        q.delta = greeks["delta"]
        q.gamma = greeks["gamma"]
        q.theta = greeks["theta"]
        q.vega = greeks["vega"]

    @classmethod
    def fair_value_proxy(cls, state: MarketState, q: OptionQuote) -> float:
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
    def _score_components(mispricing: float, probability: float, iv: float, rv: float,
                          oi_change: float, oi: float, volume: float, delta: float) -> dict[str, float]:
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
        return {"valuation": valuation, "probability": probability_score, "volatility": volatility,
                "participation": participation, "volume": volume_score, "greeks": greek_score}

    @classmethod
    def _score(cls, components: dict[str, float], learner=None) -> float:
        weighted = sum(value * (learner.weight(name) if learner else 1.0)
                       for name, value in components.items())
        weight_sum = sum((learner.weight(name) if learner else 1.0) for name in components) or 1.0
        return weighted / weight_sum * 6.0

    @staticmethod
    def _unique_prices(prices: list[float]) -> list[float]:
        out = []
        for price in prices:
            if price > 0 and (not out or price != out[-1]):
                out.append(price)
        return out

    @classmethod
    def market_phase(cls, state: MarketState) -> tuple[str, str, float]:
        """Classify the spot market without requiring a completed breakout.

        Returns (phase, direction, confidence). Thresholds are deliberately
        modest so the engine can flag early development rather than waiting for
        a large move. Accumulation is a watch state; only early confirmation or
        a still-acceptable breakout can become an entry candidate.
        """
        # Spot observations are deduplicated and arrive roughly every poll interval.
        # The old 12/5-point windows therefore represented only ~24/~10 seconds at
        # the default 2-second poll rate. That made a multi-minute move look like
        # "ACCUMULATION" whenever the last few seconds were quiet. Use a stable
        # time-based approximation instead: 5 minutes for regime/direction and
        # 1 minute for acceleration/confirmation.
        poll_seconds = max(CONFIG.poll_seconds, 0.5)
        regime_points = max(12, min(150, round(300.0 / poll_seconds)))
        fast_points = max(5, min(60, round(60.0 / poll_seconds)))
        prices = cls._unique_prices(state.spot_history)[-regime_points:]
        if len(prices) < 12:
            return "INSUFFICIENT_DATA", "NEUTRAL", 0.0

        recent = prices
        fast = prices[-min(fast_points, len(prices)):]
        base = max(recent[0], 1e-9)
        range_pct = (max(recent) - min(recent)) / base
        net_recent = (recent[-1] - recent[0]) / base
        net_fast = (fast[-1] - fast[0]) / max(fast[0], 1e-9)
        direction = "BULLISH" if net_recent > 0.00025 else "BEARISH" if net_recent < -0.00025 else "NEUTRAL"

        # Accumulation means both price compression and limited directional drift
        # across the full 5-minute regime window. A quiet last few seconds must not
        # erase a meaningful multi-minute move.
        if range_pct <= 0.0035 and abs(net_recent) <= 0.0012:
            confidence = min(0.95, 0.55 + max(0.0, 0.0035 - range_pct) * 60.0)
            return "ACCUMULATION", direction, confidence

        # Confirm acceleration over roughly one minute rather than five polling
        # observations (~10 seconds at the default poll interval).
        if abs(net_fast) >= 0.0025:
            confidence = min(0.98, 0.65 + abs(net_fast) * 60.0)
            phase = "BREAKOUT" if abs(net_fast) < 0.005 else "EXTENDED"
            return phase, ("BULLISH" if net_fast > 0 else "BEARISH"), confidence

        if abs(net_fast) >= 0.0012 and direction != "NEUTRAL":
            confidence = min(0.95, 0.60 + abs(net_fast) * 80.0)
            return "EARLY_CONFIRMATION", ("BULLISH" if net_fast > 0 else "BEARISH"), confidence

        return "TRANSITION", direction, 0.50

    @classmethod
    def evaluate(cls, state: MarketState, q: OptionQuote, risk_per_share: float,
                 target_multiple: float = 1.8, learner=None) -> TradeSignal | None:
        if q.ltp <= 0 or q.bid <= 0 or q.ask <= 0 or q.spread_pct > 0.04:
            return None

        cls.ensure_greeks(state, q)
        phase, direction, phase_confidence = cls.market_phase(state)
        fair = cls.fair_value_proxy(state, q)
        rv = cls.realized_vol(state.spot_history)
        iv = q.iv / 100.0 if q.iv > 1 else q.iv
        vol = max(rv, iv, 0.05)

        now = datetime.now(IST)
        session_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
        session_end = now.replace(hour=15, minute=15, second=0, microsecond=0)
        minutes = 345.0 if now < session_start else max(5.0, (session_end - now).total_seconds() / 60.0)

        p_spot = cls.probability_above(state.spot, q.strike, vol, minutes)
        if q.option_type == "PE":
            p_spot = 1.0 - p_spot

        # Early-development evidence nudges probability only when direction agrees;
        # it never creates a signal by itself.
        if direction == ("BULLISH" if q.option_type == "CE" else "BEARISH"):
            p_spot += 0.05 * phase_confidence
        elif direction != "NEUTRAL":
            p_spot -= 0.05 * phase_confidence

        mispricing = (fair - q.ltp) / q.ltp
        probability = min(0.90, max(0.10, 0.50 + 0.20 * (p_spot - 0.50) +
                                    0.20 * max(-0.5, min(0.5, mispricing))))
        if learner:
            probability = learner.probability(probability)

        stop = max(q.ltp * 0.75, q.ltp - risk_per_share)
        target = q.ltp + (q.ltp - stop) * target_multiple
        win = max(0.0, target - q.ltp)
        loss = max(0.0, q.ltp - stop)
        ev = probability * win - (1 - probability) * loss
        net_ev = ev - q.spread * 0.5 - q.ltp * 0.002
        if net_ev < 0:
            return None

        components = cls._score_components(mispricing, probability, iv, rv, q.oi_change, q.oi, q.volume, q.delta)
        score = cls._score(components, learner)
        checks = {
            "Mathematical valuation": fair >= q.ltp,
            "Probability evidence": probability >= 0.55,
            "IV / RV data": iv > 0 and rv > 0,
            "OI activity": abs(q.oi_change) > 0,
            "Volume activity": q.volume > 0,
            "Greeks available": abs(q.delta) > 0 or abs(q.gamma) > 0,
            "Positive net EV": net_ev >= 0,
            "Spread within limit": q.spread_pct <= 0.04,
            "Pre-breakout / early phase": phase in {"ACCUMULATION", "EARLY_CONFIRMATION", "BREAKOUT"},
            "Direction aligned": direction == "NEUTRAL" or direction == ("BULLISH" if q.option_type == "CE" else "BEARISH"),
        }
        # Accumulation alone is never an entry. Early confirmation is the preferred
        # entry phase; breakout is allowed only if the mathematical edge remains.
        if phase not in {"EARLY_CONFIRMATION", "BREAKOUT"}:
            return None
        if direction not in {"NEUTRAL", "BULLISH" if q.option_type == "CE" else "BEARISH"}:
            return None
        if probability < 0.55:
            return None

        return TradeSignal(
            action="BUY", option_type=q.option_type, strike=q.strike,
            security_id=q.security_id, symbol=q.symbol, entry=q.ask,
            stop=stop, target=target, quantity=0, probability=probability,
            fair_value=fair, expected_value=ev, net_expected_value=net_ev,
            reason=f"phase={phase}, direction={direction}, phase_conf={phase_confidence:.2f}, "
                   f"score={score:.1f}/100, prob={probability:.2%}, fair={fair:.2f}, netEV={net_ev:.2f}",
            score=score, checks=checks, score_components=components,
            market_phase=phase, direction_bias=direction,
        )

    @classmethod
    def best_signal(cls, state: MarketState, min_net_ev: float, learner=None) -> TradeSignal | None:
        candidates = []
        risk_per_share = max(5.0, state.spot * 0.001)
        for q in state.options.values():
            if q.option_type not in {"CE", "PE"}:
                continue
            s = cls.evaluate(state, q, risk_per_share, learner=learner)
            if s and s.net_expected_value >= min_net_ev:
                candidates.append(s)
        return max(candidates, key=lambda x: (x.net_expected_value, x.score), default=None)
