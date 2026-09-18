from datetime import datetime

from app.models import MarketState, OptionQuote
from app.math_engine import QuantEngine


def test_normal_cdf_midpoint():
    assert abs(QuantEngine.normal_cdf(0) - 0.5) < 1e-9


def test_option_spread():
    q = OptionQuote(24500, "CE", "1", "NIFTY", 100, 99, 101, 1000, 10000, 9000, 12)
    assert q.spread == 2
    assert q.spread_pct == 0.02


def test_probability_bounds():
    p = QuantEngine.probability_above(24500, 24500, 0.12, 30)
    assert 0 < p < 1


def test_realized_vol_requires_data():
    assert QuantEngine.realized_vol([100, 101, 102]) == 0.0


def test_market_phase_detects_accumulation():
    state = MarketState(spot=100.0)
    state.spot_history = [100.0, 100.2, 99.9, 100.1, 100.0, 100.15,
                          99.95, 100.05, 100.1, 99.98, 100.08, 100.12]
    phase, direction, confidence = QuantEngine.market_phase(state)
    assert phase == "ACCUMULATION"
    assert direction == "BULLISH"
    assert confidence > 0.5


def test_market_phase_detects_early_confirmation():
    state = MarketState(spot=100.0)
    state.spot_history = [99.5, 99.7, 99.8, 99.75, 99.85, 99.9,
                          99.95, 100.0, 100.05, 100.10, 100.15, 100.20]
    phase, direction, confidence = QuantEngine.market_phase(state)
    assert phase == "EARLY_CONFIRMATION"
    assert direction == "BULLISH"
    assert confidence > 0.5


def test_set_spot_deduplicates_polling_observations():
    state = MarketState()
    now = datetime.now()
    state.set_spot(100.0, now)
    state.set_spot(100.0, now)
    state.set_spot(100.1, now)
    assert state.spot_history == [100.0, 100.1]


def test_market_phase_uses_multi_minute_regime_window():
    state = MarketState(spot=100.0)
    # Simulate a 5-minute, ~0.16% upward drift with a quiet final minute.
    state.spot_history = [100.0 + (0.16 * i / 149) for i in range(150)]
    state.spot_history.extend([100.16, 100.16, 100.16, 100.16, 100.16])
    phase, direction, confidence = QuantEngine.market_phase(state)
    assert phase == "TRANSITION"
    assert direction == "BULLISH"
    assert confidence == 0.50



def test_black_scholes_price_is_positive():
    price = QuantEngine.black_scholes_price(23300, 23300, 0.10, "CE", "2026-09-22")
    assert price > 0


def test_market_phase_early_threshold_is_not_28_points_per_minute():
    state = MarketState(spot=100.0)
    # 31 unique observations represent about one minute at a 2-second poll.
    state.spot_history = [100.0 + (0.05 * i / 30) for i in range(31)]
    phase, direction, confidence = QuantEngine.market_phase(state)
    assert phase == "EARLY_CONFIRMATION"
    assert direction == "BULLISH"
    assert confidence > 0.5
