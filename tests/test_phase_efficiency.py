from datetime import datetime, timedelta

from app.math_engine import QuantEngine
from app.models import MarketState


def test_directional_efficiency_is_exposed():
    state = MarketState(spot=100.0)
    start = datetime(2026, 9, 30, 10, 0)
    prices = [100.0 + 0.004 * i for i in range(80)]
    state.spot_observations = [
        (start + timedelta(seconds=4 * i), price) for i, price in enumerate(prices)
    ]
    state.spot_history = prices
    metrics = QuantEngine.phase_metrics(state)
    assert metrics["directional_efficiency"] > 0.95


def test_real_timestamped_directional_regime_can_confirm_before_fast_threshold():
    state = MarketState(spot=100.0)
    start = datetime(2026, 9, 30, 10, 0)
    prices = []
    price = 100.0
    for i in range(80):
        # Broad drift is directional, while the final minute stays below the
        # normal 0.04% fast-window threshold.
        if i < 50:
            price += 0.004
        else:
            price += 0.001
        prices.append(price)
    state.spot_observations = [
        (start + timedelta(seconds=4 * i), p) for i, p in enumerate(prices)
    ]
    state.spot_history = prices

    phase, direction, confidence = QuantEngine.market_phase(state)
    metrics = QuantEngine.phase_metrics(state)

    assert direction == "BULLISH"
    assert metrics["regime_move_pct"] >= 0.0004
    assert metrics["fast_move_pct"] < 0.0004
    assert metrics["directional_efficiency"] >= 0.35
    assert phase == "EARLY_CONFIRMATION"
    assert confidence > 0.5


def test_phase_metrics_include_window_counts_and_efficiency():
    state = MarketState(spot=100.0)
    start = datetime(2026, 9, 30, 10, 0)
    prices = [100.0 + 0.01 * i for i in range(80)]
    state.spot_observations = [
        (start + timedelta(seconds=4 * i), p) for i, p in enumerate(prices)
    ]
    state.spot_history = prices
    metrics = QuantEngine.phase_metrics(state)
    assert metrics["spot_points"] == 76
    assert metrics["fast_points"] >= 5
    assert metrics["directional_efficiency"] > 0.95


def test_established_trend_continuation_can_confirm_after_short_term_compression():
    state = MarketState(spot=100.0)
    start = datetime(2026, 9, 30, 10, 0)
    prices = []
    price = 100.0
    for i in range(500):
        if i < 300:
            price -= 0.01
        elif i < 425:
            price += 0.002
        else:
            price -= 0.0005
        prices.append(price)
    state.spot_observations = [
        (start + timedelta(seconds=2 * i), p) for i, p in enumerate(prices)
    ]
    state.spot_history = prices

    phase, direction, confidence = QuantEngine.market_phase(state)
    assert phase == "EARLY_CONFIRMATION"
    assert direction == "BEARISH"
    assert confidence > 0.5
