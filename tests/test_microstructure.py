from app.microstructure import MicrostructureEngine, MicrostructureState


def make_depth(bid_qty=100, ask_qty=100, bid=100.0, ask=100.1, ltp=100.05):
    return {"live_price": ltp, "market_depth": {"depth": [
        {"buy": {"quantity": bid_qty, "price": bid}, "sell": {"quantity": ask_qty, "price": ask}},
        {"buy": {"quantity": 50, "price": bid - 0.05}, "sell": {"quantity": 50, "price": ask + 0.05}},
    ]}}


def test_depth_imbalance_and_liquidity():
    state = MicrostructureState()
    snap = MicrostructureEngine.from_depth("NFO_1", make_depth(200, 50), state)
    assert snap is not None
    assert snap.imbalance > 0
    assert snap.liquidity_score > 0


def test_absorption_can_block_entry():
    state = MicrostructureState()
    MicrostructureEngine.from_depth("NFO_1", make_depth(100, 100), state)
    snap = MicrostructureEngine.from_depth("NFO_1", make_depth(1000, 100), state)
    assert snap is not None
    ok, reason = MicrostructureEngine.confirmation(snap)
    assert not ok
    assert "absorption" in reason


def test_sweep_proxy_is_bounded():
    state = MicrostructureState()
    MicrostructureEngine.from_depth("NFO_1", make_depth(100, 100), state)
    snap = MicrostructureEngine.from_depth("NFO_1", make_depth(100, 10, ask=100.2), state)
    assert snap is not None
    assert -1.0 <= snap.sweep_score <= 1.0


def test_requires_at_least_one_valid_depth_level():
    state = MicrostructureState()
    payload = make_depth()
    payload["market_depth"]["depth"] = payload["market_depth"]["depth"][:1]
    # A single valid provider depth row is still a real snapshot; missing
    # additional rows are not fabricated.
    assert MicrostructureEngine.from_depth("NFO_1", payload, state) is not None


def test_parses_provider_bid_ask_quantity_variants():
    state = MicrostructureState()
    levels = []
    for i in range(5):
        levels.append({
            "bid": {"bidPrice": 100.0 - i * 0.05, "bidQuantity": "100"},
            "ask": {"askPrice": 100.1 + i * 0.05, "askQuantity": "120"},
        })
    snap = MicrostructureEngine.from_depth("NFO_1", {"live_price": 100.05, "market_depth": {"depth": levels}}, state)
    assert snap is not None
    assert snap.total_bid_qty == 500
    assert snap.total_ask_qty == 600
