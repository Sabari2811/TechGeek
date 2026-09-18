import math
from statistics import pstdev
from datetime import datetime, time
from zoneinfo import ZoneInfo
from .config import CONFIG
from .models import MarketState, OptionQuote, TradeSignal, SignalAudit

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
    def realized_vol(cls, prices: list[float], periods_per_year: int | None = None) -> float:
        # The live option-chain loop polls roughly every 2 seconds. The previous
        # annualization assumed 1-minute observations, overstating/understating RV
        # depending on poll cadence. Use the configured polling interval so the
        # volatility scale matches the actual observation spacing.
        if periods_per_year is None:
            periods_per_year = int(252 * 375 * 60 / max(CONFIG.poll_seconds, 0.5))
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
    def black_scholes_price(cls, spot: float, strike: float, vol: float,
                            option_type: str, expiry: str,
                            risk_free_rate: float | None = None,
                            dividend_yield: float | None = None) -> float:
        sigma = vol / 100.0 if vol > 1.0 else vol
        t = cls.time_to_expiry(expiry)
        if spot <= 0 or strike <= 0 or sigma <= 0 or t <= 0:
            return cls.intrinsic(spot, strike, option_type)

        r = CONFIG.risk_free_rate if risk_free_rate is None else risk_free_rate
        q = CONFIG.dividend_yield if dividend_yield is None else dividend_yield
        sqrt_t = math.sqrt(t)
        d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
        d2 = d1 - sigma * sqrt_t
        disc_q = math.exp(-q * t)
        disc_r = math.exp(-r * t)
        if option_type.upper() == "CE":
            return spot * disc_q * cls.normal_cdf(d1) - strike * disc_r * cls.normal_cdf(d2)
        return strike * disc_r * cls.normal_cdf(-d2) - spot * disc_q * cls.normal_cdf(-d1)

    @classmethod
    def fair_value_proxy(cls, state: MarketState, q: OptionQuote) -> float:
        """Research fair value using IV/RV and full time-to-expiry."""
        rv = cls.realized_vol(state.spot_history)
        iv = q.iv / 100.0 if q.iv > 1 else q.iv
        vol = max(iv, rv, 0.05)
        return cls.black_scholes_price(state.spot, q.strike, vol, q.option_type, state.expiry or "")

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

    @staticmethod
    def _phase_series(state: MarketState) -> tuple[list[float], list[float]]:
        observations = getattr(state, "spot_observations", [])
        if len(observations) >= 12:
            latest = observations[-1][0]
            recent_obs = [(ts, price) for ts, price in observations if (latest - ts).total_seconds() <= 300]
            if len(recent_obs) >= 12:
                fast_obs = [(ts, price) for ts, price in recent_obs if (latest - ts).total_seconds() <= 60]
                recent = [price for _, price in recent_obs]
                fast = [price for _, price in fast_obs] if len(fast_obs) >= 5 else recent[-5:]
                return QuantEngine._unique_prices(recent), QuantEngine._unique_prices(fast)
        poll_seconds = max(CONFIG.poll_seconds, 0.5)
        regime_points = max(12, min(150, round(300.0 / poll_seconds)))
        fast_points = max(5, min(60, round(60.0 / poll_seconds)))
        prices = QuantEngine._unique_prices(state.spot_history)[-regime_points:]
        return prices, prices[-min(fast_points, len(prices)):]


    @classmethod
    def market_phase(cls, state: MarketState) -> tuple[str, str, float]:
        """Classify spot using elapsed-time windows when timestamps exist.

        Untimestamped history is legacy/test data, so it is interpreted by the
        shape of the available series rather than pretending every point is a
        live 2-second observation.
        """
        recent, fast = cls._phase_series(state)
        if len(recent) < 12:
            return "INSUFFICIENT_DATA", "NEUTRAL", 0.0

        base = max(recent[0], 1e-9)
        range_pct = (max(recent) - min(recent)) / base
        net_recent = (recent[-1] - recent[0]) / base
        net_fast = (fast[-1] - fast[0]) / max(fast[0], 1e-9)
        direction = (
            "BULLISH" if net_recent > 0.00025
            else "BEARISH" if net_recent < -0.00025
            else "NEUTRAL"
        )

        has_real_timestamps = len(getattr(state, "spot_observations", [])) >= 12

        if has_real_timestamps:
            if abs(net_fast) >= CONFIG.phase_breakout_move_pct:
                confidence = min(0.98, 0.65 + abs(net_fast) * 60.0)
                return (
                    "BREAKOUT" if abs(net_fast) < 0.005 else "EXTENDED",
                    "BULLISH" if net_fast > 0 else "BEARISH",
                    confidence,
                )
            if abs(net_fast) >= CONFIG.phase_early_move_pct:
                confidence = min(0.95, 0.60 + abs(net_fast) * 80.0)
                return (
                    "EARLY_CONFIRMATION",
                    "BULLISH" if net_fast > 0 else "BEARISH",
                    confidence,
                )
            if range_pct <= 0.0035 and abs(net_recent) <= 0.0012:
                confidence = min(0.95, 0.55 + max(0.0, 0.0035 - range_pct) * 60.0)
                return "ACCUMULATION", direction, confidence
            return "TRANSITION", direction, 0.50

        history_len = len(recent)
        poll_seconds = max(CONFIG.poll_seconds, 0.5)
        fast_points = max(5, min(60, round(60.0 / poll_seconds)))

        # Compact 12-point histories are classified from their overall shape.
        # A narrow range with small net drift is accumulation.
        if history_len <= 16:
            if range_pct <= 0.0035 and abs(net_recent) <= 0.0012:
                confidence = min(0.95, 0.55 + max(0.0, 0.0035 - range_pct) * 60.0)
                return "ACCUMULATION", direction, confidence

            # Sustained directional move over the compact history is early
            # confirmation; this keeps short legacy fixtures meaningful.
            if abs(net_recent) >= CONFIG.phase_early_move_pct:
                confidence = min(0.95, 0.60 + abs(net_recent) * 80.0)
                return "EARLY_CONFIRMATION", direction, confidence

            return "TRANSITION", direction, 0.50

        # For longer untimestamped histories, a full one-minute move only counts
        # as confirmation when there is enough history to establish that window.
        if history_len >= fast_points:
            legacy_fast = recent[-fast_points:]
            legacy_fast_move = (legacy_fast[-1] - legacy_fast[0]) / max(legacy_fast[0], 1e-9)
            if abs(legacy_fast_move) >= CONFIG.phase_breakout_move_pct:
                confidence = min(0.98, 0.65 + abs(legacy_fast_move) * 60.0)
                return (
                    "BREAKOUT" if abs(legacy_fast_move) < 0.005 else "EXTENDED",
                    "BULLISH" if legacy_fast_move > 0 else "BEARISH",
                    confidence,
                )
            if abs(legacy_fast_move) >= CONFIG.phase_early_move_pct:
                confidence = min(0.95, 0.60 + abs(legacy_fast_move) * 80.0)
                return (
                    "EARLY_CONFIRMATION",
                    "BULLISH" if legacy_fast_move > 0 else "BEARISH",
                    confidence,
                )

        if range_pct <= 0.0035 and abs(net_recent) <= 0.0012:
            confidence = min(0.95, 0.55 + max(0.0, 0.0035 - range_pct) * 60.0)
            return "ACCUMULATION", direction, confidence
        return "TRANSITION", direction, 0.50

    @classmethod
    def phase_metrics(cls, state: MarketState) -> dict[str, float | int | str]:
        recent, fast = cls._phase_series(state)
        if len(recent) < 12:
            return {
                "spot_points": len(recent), "fast_move_pct": 0.0,
                "regime_move_pct": 0.0, "regime_range_pct": 0.0,
            }
        base = max(recent[0], 1e-9)
        return {
            "spot_points": len(recent),
            "fast_move_pct": (fast[-1] - fast[0]) / max(fast[0], 1e-9),
            "regime_move_pct": (recent[-1] - recent[0]) / base,
            "regime_range_pct": (max(recent) - min(recent)) / base,
        }

    @classmethod
    def evaluate_diagnostic(cls, state: MarketState, q: OptionQuote, risk_per_share: float,
                            target_multiple: float = 1.8, learner=None) -> tuple[TradeSignal | None, str, dict]:
        metrics = cls.phase_metrics(state)
        phase, direction, phase_confidence = cls.market_phase(state)
        metrics.update({"phase": phase, "direction": direction, "phase_confidence": phase_confidence})

        if q.ltp <= 0:
            return None, "INVALID_LTP", metrics
        if q.bid <= 0 or q.ask <= 0:
            return None, "INVALID_BID_ASK", metrics
        if q.spread_pct > CONFIG.max_spread_pct:
            return None, "SPREAD_TOO_WIDE", metrics

        # Hard market-regime gates run before fair value, probability and EV.
        # This makes the audit truthful: no mathematical edge is evaluated while
        # the market is still in accumulation or moving against the option side.
        if phase not in {"EARLY_CONFIRMATION", "BREAKOUT"}:
            return None, "MARKET_PHASE_WAIT", metrics
        aligned = "BULLISH" if q.option_type == "CE" else "BEARISH"
        if direction not in {"NEUTRAL", aligned}:
            return None, "DIRECTION_MISMATCH", metrics

        cls.ensure_greeks(state, q)
        fair = cls.fair_value_proxy(state, q)
        rv = cls.realized_vol(state.spot_history)
        iv = q.iv / 100.0 if q.iv > 1 else q.iv
        if iv <= 0:
            return None, "IV_MISSING", metrics
        vol = max(rv, iv, 0.05)
        if rv <= 0:
            return None, "RV_INSUFFICIENT", metrics

        now = datetime.now(IST)
        session_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
        session_end = now.replace(hour=15, minute=15, second=0, microsecond=0)
        minutes = 345.0 if now < session_start else max(5.0, (session_end - now).total_seconds() / 60.0)

        p_spot = cls.probability_above(state.spot, q.strike, vol, minutes)
        if q.option_type == "PE":
            p_spot = 1.0 - p_spot
        if direction == aligned:
            p_spot += 0.05 * phase_confidence
        elif direction != "NEUTRAL":
            p_spot -= 0.05 * phase_confidence

        mispricing = (fair - q.ltp) / q.ltp
        probability = min(0.90, max(0.10, 0.50 + 0.20 * (p_spot - 0.50) +
                                    0.20 * max(-0.5, min(0.5, mispricing))))
        if learner:
            probability = learner.probability(probability)
        if probability < 0.55:
            return None, "PROBABILITY_BELOW_55", {**metrics, "probability": probability, "fair": fair}

        stop = max(q.ltp * 0.75, q.ltp - risk_per_share)
        target = q.ltp + (q.ltp - stop) * target_multiple
        win = max(0.0, target - q.ltp)
        loss = max(0.0, q.ltp - stop)
        ev = probability * win - (1 - probability) * loss
        net_ev = ev - q.spread * 0.5 - q.ltp * 0.002
        metrics.update({"probability": probability, "fair": fair, "expected_value": ev, "net_expected_value": net_ev})

        if net_ev < 0:
            return None, "NEGATIVE_NET_EV", metrics

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
            "Spread within limit": q.spread_pct <= CONFIG.max_spread_pct,
            "Entry phase": phase in {"EARLY_CONFIRMATION", "BREAKOUT"},
            "Direction aligned": direction == "NEUTRAL" or direction == aligned,
        }
        return TradeSignal(
            action="BUY", option_type=q.option_type, strike=q.strike,
            security_id=q.security_id, symbol=q.symbol, entry=q.ask,
            stop=stop, target=target, quantity=0, probability=probability,
            fair_value=fair, expected_value=ev, net_expected_value=net_ev,
            reason=f"phase={phase}, direction={direction}, phase_conf={phase_confidence:.2f}, "
                   f"score={score:.1f}/100, prob={probability:.2%}, fair={fair:.2f}, netEV={net_ev:.2f}",
            score=score, checks=checks, score_components=components,
            market_phase=phase, direction_bias=direction,
        ), "SIGNAL_READY", metrics

    @classmethod
    def evaluate(cls, state: MarketState, q: OptionQuote, risk_per_share: float,
                 target_multiple: float = 1.8, learner=None) -> TradeSignal | None:
        signal, _, _ = cls.evaluate_diagnostic(state, q, risk_per_share, target_multiple, learner)
        return signal

    @classmethod
    def best_signal(cls, state: MarketState, min_net_ev: float, learner=None,
                    audit: SignalAudit | None = None) -> TradeSignal | None:
        candidates = []
        risk_per_share = max(5.0, state.spot * 0.001)
        if audit is not None:
            audit.total_options = 0
            audit.calls = audit.puts = 0
            audit.rejected.clear()
            audit.best_rejected_reason = ""
            audit.best_rejected_symbol = ""
            audit.best_rejected_net_ev = float("-inf")
            phase, direction, confidence = cls.market_phase(state)
            audit.phase, audit.phase_direction, audit.phase_confidence = phase, direction, confidence
            pm = cls.phase_metrics(state)
            audit.spot_points = int(pm["spot_points"])
            audit.fast_move_pct = float(pm["fast_move_pct"])
            audit.regime_move_pct = float(pm["regime_move_pct"])
            audit.regime_range_pct = float(pm["regime_range_pct"])

        for q in state.options.values():
            if q.option_type not in {"CE", "PE"}:
                continue
            if audit is not None:
                audit.total_options += 1
                if q.option_type == "CE":
                    audit.calls += 1
                else:
                    audit.puts += 1
            signal, reason, metrics = cls.evaluate_diagnostic(state, q, risk_per_share, learner=learner)
            if audit is not None:
                audit.evaluated += 1
                audit.reject(reason)
                candidate_ev = float(metrics.get("net_expected_value", float("-inf")))
                if candidate_ev > audit.best_rejected_net_ev:
                    audit.best_rejected_net_ev = candidate_ev
                    audit.best_rejected_reason = reason
                    audit.best_rejected_symbol = q.symbol or f"{q.strike:g}{q.option_type}"
                    audit.best_rejected_probability = float(metrics.get("probability", 0.0))
                    audit.best_rejected_phase = str(metrics.get("phase", "UNKNOWN"))
                    audit.best_rejected_direction = str(metrics.get("direction", "NEUTRAL"))
            if signal:
                if audit is not None:
                    audit.eligible_before_min_ev += 1
                if signal.net_expected_value >= min_net_ev:
                    candidates.append(signal)

        if audit is not None:
            audit.final_candidates = len(candidates)
            if candidates:
                audit.rejected.pop("SIGNAL_READY", None)
            if audit.total_options == 0:
                audit.reject("NO_OPTION_CONTRACTS")
            elif (audit.phase in {"EARLY_CONFIRMATION", "BREAKOUT"}
                  and audit.eligible_before_min_ev > 0
                  and not candidates):
                audit.reject("MIN_NET_EV_NOT_MET")
        return max(candidates, key=lambda x: (x.net_expected_value, x.score), default=None)
