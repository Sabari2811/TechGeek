from datetime import datetime
from types import SimpleNamespace

from app import execution as execution_module
from app.models import TradeSignal


def test_paper_entry_and_exit_emit_explicit_simulated_order_audit(monkeypatch):
    events = []
    monkeypatch.setattr(execution_module, "CONFIG", SimpleNamespace(
        mode="PAPER", live_enabled=lambda: False
    ))
    monkeypatch.setattr(execution_module, "kill_switch_status", lambda: (False, ""))
    monkeypatch.setattr(execution_module, "save_open_position", lambda *args, **kwargs: None)
    monkeypatch.setattr(execution_module, "clear_open_position", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        execution_module, "record_audit_event",
        lambda event, payload: events.append((event, payload)),
    )

    signal = TradeSignal(
        action="BUY",
        option_type="CE",
        strike=25000,
        security_id="12345",
        symbol="NIFTY-25000-CE",
        entry=100.0,
        stop=80.0,
        target=140.0,
        quantity=65,
        probability=0.68,
        fair_value=120.0,
        expected_value=20.0,
        net_expected_value=18.0,
        reason="positive mathematical edge",
        score=8.5,
        checks={"Mathematical valuation": True, "Microstructure confirmation": True},
        score_components={"edge": 8.5},
        market_phase="BREAKOUT",
        direction_bias="BULLISH",
    )
    engine = execution_module.ExecutionEngine(client=None)

    import asyncio

    async def scenario():
        position = await engine.enter(signal, 65)
        assert position.entry_price == 100.0
        closed = await engine.exit(110.0, "TARGET", price_basis="BID")
        assert closed is not None
        assert closed.realized_pnl == 650.0

    asyncio.run(scenario())

    paper_events = [payload for name, payload in events if name == "paper_order_simulated"]
    assert len(paper_events) == 2
    assert paper_events[0]["side"] == "BUY"
    assert paper_events[0]["fill_model"] == "BUY_AT_OPTION_ASK"
    assert paper_events[0]["broker_order_submitted"] is False
    assert paper_events[0]["probability"] == 0.68
    assert paper_events[0]["checks"]["Microstructure confirmation"] is True
    assert paper_events[1]["side"] == "SELL"
    assert paper_events[1]["fill_model"] == "SELL_AT_FRESH_BID"
    assert paper_events[1]["gross_pnl_for_fill"] == 650.0
