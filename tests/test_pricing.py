from app.math_engine import QuantEngine
from app.models import MarketState, OptionQuote


def test_black_scholes_greeks_are_finite_and_directional():
    g_call = QuantEngine.black_scholes_greeks(23398.1, 23400, 14.0, "CE", "2026-09-15")
    g_put = QuantEngine.black_scholes_greeks(23398.1, 23400, 14.0, "PE", "2026-09-15")
    assert 0.0 < g_call["delta"] < 1.0
    assert -1.0 < g_put["delta"] < 0.0
    assert g_call["gamma"] > 0
    assert g_call["vega"] > 0
    assert g_call["theta"] < 0


def test_missing_broker_greeks_are_filled_locally():
    state = MarketState(spot=23398.1, expiry="2026-09-15")
    q = OptionQuote(23400, "CE", "1", "NIFTY", 100, 99, 101, 1000, 10000, 9000, 14.0)
    QuantEngine.ensure_greeks(state, q)
    assert q.delta > 0
    assert q.gamma > 0
    assert q.vega > 0


def test_supplied_greeks_are_not_overwritten():
    state = MarketState(spot=23398.1, expiry="2026-09-15")
    q = OptionQuote(23400, "CE", "1", "NIFTY", 100, 99, 101, 1000, 10000, 9000, 14.0,
                    delta=0.42, gamma=0.001, theta=-2.0, vega=8.0)
    QuantEngine.ensure_greeks(state, q)
    assert q.delta == 0.42
    assert q.gamma == 0.001
    assert q.theta == -2.0
    assert q.vega == 8.0
