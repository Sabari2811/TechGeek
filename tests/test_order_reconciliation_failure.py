import asyncio

import pytest

from app import kill_switch, order_journal
from app.execution import ExecutionEngine


class ReconciliationFailureClient:
    async def place_order(self, *args, **kwargs):
        return {"data": {"order_status": "PENDING", "order_id": "order-uncertain"}}

    async def order_book(self):
        raise OSError("simulated order-book outage")

    async def cancel_order(self, order_id):
        raise AssertionError("should fail closed before cancellation")


def test_order_book_failure_trips_kill_switch_and_keeps_journal_unresolved(tmp_path, monkeypatch):
    monkeypatch.setattr(kill_switch, "KILL_SWITCH_PATH", tmp_path / "kill_switch.json")
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path / "orders")

    async def scenario():
        engine = ExecutionEngine(ReconciliationFailureClient())
        with pytest.raises(RuntimeError, match="entry kill switch enabled"):
            await engine._live_order("BUY", "123", 50, 100.0, "entry-test")

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.execution.asyncio.sleep", no_sleep)
    asyncio.run(scenario())
    assert kill_switch.status()[0] is True
    assert "entry-test" in order_journal.unresolved_orders()
