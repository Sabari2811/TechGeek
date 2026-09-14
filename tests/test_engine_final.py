from app.math_engine import QuantEngine
from app.models import MarketState, OptionQuote


def make_state():
    state = MarketState(spot=25000)
    state.spot_history = [25000 + i * 0.5 for i in range(40)]
    return state


def test_soft_score_does_not_require_all_evidence():
    state = make_state()
    q = OptionQuote(25000, "CE", "1", "NIFTY", 100, 99.5, 100.5, 500, 10000, 9990, 14, delta=0.5, gamma=0.01)
    s = QuantEngine.evaluate(state, q, 5)
    assert s is not None
    assert 0 <= s.score <= 100
    assert set(s.score_components) == {"valuation", "probability", "volatility", "participation", "volume", "greeks"}


def test_no_chart_indicators_in_engine_source():
    import inspect
    source = inspect.getsource(QuantEngine)
    assert "VWAP" not in source
    assert "EMA" not in source


def test_signal_has_structured_checklist():
    state = make_state()
    q = OptionQuote(25000, "CE", "1", "NIFTY", 100, 99.5, 100.5, 500, 10000, 9990, 14, delta=0.5, gamma=0.01)
    s = QuantEngine.evaluate(state, q, 5)
    assert s is not None
    assert "Positive net EV" in s.checks
    assert "Spread within limit" in s.checks
