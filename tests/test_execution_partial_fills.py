import asyncio
import json
from datetime import datetime

import pytest

from app.config import CONFIG
from app.execution import ExecutionEngine
from app.models import Position, TradeSignal


class FakeClient:
    def __init__(self, fills):
        self.fills = list(fills)
        self.orders = []
        self.next_id = 1

    async def place_order(self, txn_type, security_id, qty, price, tag):
        order_id = str(self.next_id)
        self.next_id += 1
        fill = self.fills.pop(0)
        order = {
            "id": order_id,
            "status": fill["status"],
            "traded_qty": fill["traded_qty"],
            "traded_price": fill["traded_price"],
            "remarks": tag,
        }
        self.orders.append(order)
        return {"data": {"order_status": "PENDING", "order_id": order_id}}

    async def order_book(self):
        return list(self.orders)

    async def cancel_order(self, order_id):
        raise AssertionError("Terminal test orders should not need cancellation")


def make_signal(quantity=5):
    return TradeSignal(
        action="BUY",
        option_type="CE",
        strike=24500,
        security_id="123",
        symbol="NIFTY",
        entry=200.0,
        stop=180.0,
        target=236.0,
        quantity=quantity,
        probability=0.6,
        fair_value=210.0,
        expected_value=12.0,
        net_expected_value=10.0,
        reason="test",
    )


@pytest.fixture
def live_mode(monkeypatch, tmp_path):
    # Keep simulated broker events out of the real .quantnifty/orders journal.
    monkeypatch.setattr("app.order_journal.JOURNAL_ROOT", tmp_path / "orders")
    # Keep simulated lifecycle events out of the real .quantnifty/audit journal.
    monkeypatch.setattr("app.raw_data.AUDIT_ROOT", tmp_path / "audit")
    monkeypatch.setattr(type(CONFIG), "live_enabled", lambda self: True)
    async def no_sleep(_seconds):
        return None
    monkeypatch.setattr("app.execution.asyncio.sleep", no_sleep)
    return tmp_path


def test_partial_exit_keeps_remaining_position_and_accumulates_fills(live_mode):
    tmp_path = live_mode
    async def scenario():
        client = FakeClient([
            {"status": "PARTIALLY FILLED - CANCELLED", "traded_qty": 2, "traded_price": 190.0},
            {"status": "SUCCESS", "traded_qty": 3, "traded_price": 185.0},
        ])
        engine = ExecutionEngine(client)
        signal = make_signal()
        engine.position = Position(
            signal=signal,
            entry_price=200.0,
            quantity=5,
            opened_at=datetime(2026, 10, 21, 10, 0),
            current_price=190.0,
        )
    
        first = await engine.exit(190.0, "STOP LOSS")
    
        assert first is None
        assert engine.position is not None
        assert engine.position.quantity == 3
        assert engine.position.exit_filled_quantity == 2
        assert engine.position.exit_proceeds == 380.0
        assert engine.closed_trades == []
    
        closed = await engine.exit(185.0, "STOP LOSS")
    
        assert closed is not None
        assert engine.position is None
        assert closed.quantity == 0
        assert closed.initial_quantity == 5
        assert closed.exit_filled_quantity == 5
        assert closed.exit_price == pytest.approx(187.0)
        assert closed.realized_pnl == pytest.approx(-65.0)
        assert len(engine.closed_trades) == 1
        assert engine.closed_trades[0].quantity == 5
        assert engine.closed_trades[0].exit_price == pytest.approx(187.0)
        assert engine.closed_trades[0].pnl == pytest.approx(-65.0)

        audit_files = list((tmp_path / "audit").glob("*.jsonl"))
        assert len(audit_files) == 1
        events = [json.loads(line) for line in audit_files[0].read_text().splitlines()]
        exits = [event["payload"] for event in events if event["event_type"] == "exit_fill"]
        assert len(exits) == 2
        assert exits[0]["gross_pnl_for_fill"] == pytest.approx(-20.0)
        assert exits[1]["gross_pnl_for_fill"] == pytest.approx(-45.0)
        assert exits[1]["cumulative_gross_pnl"] == pytest.approx(-65.0)
        assert all(event["estimated_charges"] is None for event in exits)
        assert all(event["net_pnl"] is None for event in exits)
        assert all(event["charges_status"] == "NOT_ESTIMATED" for event in exits)

    asyncio.run(scenario())


def test_duplicate_entry_is_rejected(monkeypatch, tmp_path):
    import app.kill_switch as kill_switch
    monkeypatch.setattr(kill_switch, "KILL_SWITCH_PATH", tmp_path / "kill_switch.json")

    async def scenario():
        engine = ExecutionEngine(FakeClient([]))
        engine.position = Position(
            signal=make_signal(),
            entry_price=200.0,
            quantity=5,
            opened_at=datetime(2026, 10, 21, 10, 0),
        )

        with pytest.raises(RuntimeError, match="position is already open"):
            await engine.enter(make_signal(), 5)

    asyncio.run(scenario())
