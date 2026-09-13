from app.models import MarketState, OptionQuote
from app.math_engine import QuantEngine

def test_normal_cdf_midpoint():
    assert abs(QuantEngine.normal_cdf(0) - 0.5) < 1e-9

def test_option_spread():
    q = OptionQuote(24500,"CE","1","NIFTY",100,99,101,1000,10000,9000,12)
    assert q.spread == 2
    assert q.spread_pct == 0.02

def test_probability_bounds():
    p = QuantEngine.probability_above(24500, 24500, 0.12, 30)
    assert 0 < p < 1

def test_realized_vol_requires_data():
    assert QuantEngine.realized_vol([100,101,102]) == 0.0
