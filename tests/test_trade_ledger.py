from datetime import date, datetime

from app.models import TradeRecord
import app.session_state as session_state


def test_trade_record_round_trips_through_session_state(tmp_path, monkeypatch):
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", path)
    trade = TradeRecord(
        symbol="NIFTY25000CE",
        option_type="CE",
        strike=25000,
        entry_price=100.0,
        stop_price=75.0,
        exit_price=110.0,
        quantity=75,
        opened_at=datetime(2026, 9, 30, 10, 0),
        closed_at=datetime(2026, 9, 30, 10, 5),
        pnl=750.0,
        exit_reason="TARGET",
    )
    session_state.save_today([25000, 25001], date(2026, 9, 30), [trade])
    loaded = session_state.load_today_trades(date(2026, 9, 30))
    assert len(loaded) == 1
    assert loaded[0].symbol == trade.symbol
    assert loaded[0].entry_price == trade.entry_price
    assert loaded[0].exit_price == trade.exit_price
    assert loaded[0].pnl == trade.pnl
    assert loaded[0].exit_reason == "TARGET"


def test_previous_day_trade_ledger_is_not_restored(tmp_path, monkeypatch):
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", path)
    trade = TradeRecord(
        "NIFTY25000CE", "CE", 25000, 100, 75, 90, 75,
        datetime(2026, 9, 29, 10, 0),
        datetime(2026, 9, 29, 10, 5),
        -750, "STOP LOSS",
    )
    session_state.save_today([], date(2026, 9, 29), [trade])
    assert session_state.load_today_trades(date(2026, 9, 30)) == []
