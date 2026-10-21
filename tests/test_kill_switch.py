import asyncio
from datetime import datetime

import pytest

from app import kill_switch
from app.execution import ExecutionEngine
from app.models import TradeSignal


class NoOrderClient:
    async def place_order(self, *args, **kwargs):
        raise AssertionError("entry must be blocked before any broker call")


def make_signal():
    return TradeSignal(
        action="BUY", option_type="CE", strike=24500, security_id="123",
        symbol="NIFTY", entry=200.0, stop=180.0, target=236.0, quantity=1,
        probability=0.6, fair_value=210.0, expected_value=12.0,
        net_expected_value=10.0, reason="test",
    )


def test_missing_kill_switch_file_defaults_off(tmp_path, monkeypatch):
    monkeypatch.setattr(kill_switch, "KILL_SWITCH_PATH", tmp_path / "kill_switch.json")
    assert kill_switch.status() == (False, "not set")


def test_kill_switch_persists_enabled_state(tmp_path, monkeypatch):
    monkeypatch.setattr(kill_switch, "KILL_SWITCH_PATH", tmp_path / "kill_switch.json")
    kill_switch.set_enabled(True, "operator safety hold")
    assert kill_switch.status() == (True, "operator safety hold")
    kill_switch.set_enabled(False, "review completed")
    assert kill_switch.status() == (False, "review completed")


def test_corrupt_kill_switch_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "kill_switch.json"
    monkeypatch.setattr(kill_switch, "KILL_SWITCH_PATH", path)
    path.write_text("{not-json", encoding="utf-8")
    enabled, reason = kill_switch.status()
    assert enabled is True
    assert "fail-closed" in reason


def test_execution_entry_is_blocked_before_broker_call(tmp_path, monkeypatch):
    monkeypatch.setattr(kill_switch, "KILL_SWITCH_PATH", tmp_path / "kill_switch.json")
    kill_switch.set_enabled(True, "test lock")
    engine = ExecutionEngine(NoOrderClient())

    async def scenario():
        with pytest.raises(RuntimeError, match="persistent kill switch"):
            await engine.enter(make_signal(), 1)

    asyncio.run(scenario())
