from types import SimpleNamespace

from app.trader import squareoff_limit_price


def test_squareoff_requires_fresh_positive_bid():
    position = SimpleNamespace(quote_stale=False, quote_bid=99.5)
    assert squareoff_limit_price(position) == 99.5


def test_squareoff_rejects_stale_quote_even_if_bid_present():
    position = SimpleNamespace(quote_stale=True, quote_bid=99.5)
    assert squareoff_limit_price(position) is None


def test_squareoff_rejects_missing_zero_or_invalid_bid():
    for bid in (0, -1, None, float("nan"), float("inf"), "bad"):
        position = SimpleNamespace(quote_stale=False, quote_bid=bid)
        assert squareoff_limit_price(position) is None


def test_squareoff_rejects_missing_position():
    assert squareoff_limit_price(None) is None
