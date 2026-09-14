import asyncio

from app.config import CONFIG
from app.execution import ExecutionEngine
from app.models import TradeSignal


def test_live_orders_require_explicit_second_key(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "NO")
    assert CONFIG.live_enabled() is False


def test_paper_entry_never_calls_broker_order(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "NO")
    calls = []

    class Client:
        async def place_order(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("paper mode must not place a broker order")

    signal = TradeSignal(
        action="BUY", option_type="CE", strike=23400, security_id="1", symbol="NIFTY",
        entry=100, stop=90, target=120, quantity=1, probability=0.6,
        fair_value=105, expected_value=12, net_expected_value=10, reason="test"
    )
    position = asyncio.run(ExecutionEngine(Client()).enter(signal, 1))
    assert position.entry_price == 100
    assert calls == []
