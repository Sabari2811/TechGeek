import asyncio
from datetime import datetime

import app.execution as execution_module
import app.kill_switch as kill_switch
import app.session_state as session_state
from app.config import CONFIG, IST
from app.execution import ExecutionEngine
from app.models import TradeSignal


class NoBrokerOrders:
    async def place_order(self, *args, **kwargs):
        raise AssertionError("PAPER execution must not call broker order placement")


def make_signal():
    return TradeSignal(
        action="BUY",
        option_type="CE",
        strike=23500,
        security_id="SEC123",
        symbol="NIFTY-23500-CE",
        entry=120.0,
        stop=105.0,
        target=150.0,
        quantity=65,
        probability=0.62,
        fair_value=130.0,
        expected_value=12.0,
        net_expected_value=10.0,
        reason="paper persistence test",
    )


def setup_isolated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(session_state, "OPEN_POSITION_PATH", tmp_path / "open_position.json")
    monkeypatch.setattr(kill_switch, "KILL_SWITCH_PATH", tmp_path / "kill_switch.json")
    monkeypatch.setattr(execution_module, "record_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "NO")
    assert CONFIG.mode == "PAPER"
    assert CONFIG.live_enabled() is False


def test_paper_entry_persists_and_full_exit_clears_position(tmp_path, monkeypatch):
    setup_isolated_state(monkeypatch, tmp_path)
    engine = ExecutionEngine(NoBrokerOrders())

    position = asyncio.run(engine.enter(make_signal(), 65))
    saved = session_state.load_open_position(position.opened_at.date())
    assert saved is not None
    assert saved.signal.security_id == "SEC123"
    assert saved.quantity == 65

    closed = asyncio.run(engine.exit(140.0, "TARGET", price_basis="LTP_ESTIMATE"))
    assert closed is not None
    assert closed.quantity == 0
    assert engine.position is None
    assert session_state.load_open_position(position.opened_at.date()) is None


def test_paper_entry_persistence_failure_trips_kill_switch(tmp_path, monkeypatch):
    setup_isolated_state(monkeypatch, tmp_path)

    def fail_save(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(execution_module, "save_open_position", fail_save)
    engine = ExecutionEngine(NoBrokerOrders())

    try:
        asyncio.run(engine.enter(make_signal(), 65))
    except RuntimeError as exc:
        assert "durably persisted" in str(exc)
    else:
        raise AssertionError("entry should fail when PAPER position cannot be persisted")

    enabled, reason = kill_switch.status()
    assert enabled is True
    assert "persist" in reason.lower()
    assert engine.position is not None
