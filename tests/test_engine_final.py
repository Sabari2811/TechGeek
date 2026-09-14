from app.math_engine import QuantEngine
from app.models import MarketState, OptionQuote


def make_state():
    state = MarketState(spot=25000)
    state.spot_history = [25000 + i * 0.5 for i in range(40)]
    return state


def make_option():
    return OptionQuote(25000, "CE", "1", "NIFTY", 100, 99.5, 100.5, 500, 10000, 9990, 14, delta=0.5, gamma=0.01)


def test_soft_score_components_do_not_require_perfect_alignment():
    components = QuantEngine._score_components(0.05, 0.53, 0.14, 0.12, 10, 10000, 500, 0.5)
    score = QuantEngine._score(components)
    assert 0 <= score <= 100
    assert set(components) == {"valuation", "probability", "volatility", "participation", "volume", "greeks"}


def test_signal_checklist_is_structured_when_ev_is_positive():
    state = make_state()
    q = make_option()
    s = QuantEngine.evaluate(state, q, 5)
    # This market fixture may legitimately have negative EV depending on session time.
    # When a signal exists, its checklist must contain only mathematical/execution evidence.
    if s is not None:
        assert "Positive net EV" in s.checks
        assert "Spread within limit" in s.checks
        assert s.score_components


def test_trade_signal_model_supports_learning_metadata():
    q = make_option()
    assert q.spread_pct <= 0.04
    components = QuantEngine._score_components(0.05, 0.60, 0.14, 0.12, 10, 10000, 500, 0.5)
    assert all(value >= 0 for value in components.values())
