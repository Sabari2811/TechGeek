import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app import daily_reports, raw_data, session_state
from app.models import TradeRecord


def test_daily_report_includes_raw_audit_and_manifest(tmp_path, monkeypatch):
    day = date(2026, 11, 3)
    audit = tmp_path / "audit"
    raw = tmp_path / "raw"
    reports = tmp_path / "reports"
    audit.mkdir()
    raw.mkdir()
    monkeypatch.setattr(daily_reports, "AUDIT_ROOT", audit)
    monkeypatch.setattr(daily_reports, "RAW_ROOT", raw)
    monkeypatch.setattr(daily_reports, "REPORT_ROOT", reports)
    monkeypatch.setattr(raw_data, "AUDIT_ROOT", audit)
    monkeypatch.setattr(raw_data, "RAW_ROOT", raw)
    monkeypatch.setattr(session_state, "STATE_PATH", tmp_path / "session_state.json")

    raw_data.record_audit_event(
        "signal_rejected",
        {"blocking_reason": "MARKET_PHASE_WAIT", "api_token": "never-return"},
        datetime(2026, 11, 3, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    raw_data.record_option_chain(
        {"contracts": [{"symbol": "NIFTY"}]},
        timestamp=datetime(2026, 11, 3, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    report = daily_reports.write_daily_report(day)

    assert report["summary"]["signal_rejection_cycles"] == 1
    assert report["summary"]["option_chain_snapshots"] == 1
    assert report["raw_audit_events"][0]["payload"]["api_token"] == "[REDACTED]"
    assert (reports / day.isoformat() / "daily_report.json").exists()
    assert (reports / day.isoformat() / "analysis.md").exists()


def test_daily_report_includes_closed_session_ledger_trade(tmp_path, monkeypatch):
    day = date(2026, 11, 3)
    audit = tmp_path / "audit"
    raw = tmp_path / "raw"
    audit.mkdir()
    raw.mkdir()
    monkeypatch.setattr(daily_reports, "AUDIT_ROOT", audit)
    monkeypatch.setattr(daily_reports, "RAW_ROOT", raw)
    monkeypatch.setattr(daily_reports, "REPORT_ROOT", tmp_path / "reports")
    state = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", state)
    trade = TradeRecord(
        "NIFTY25000CE", "CE", 25000, 100, 90, 110, 65,
        datetime(2026, 11, 3, 10, 0),
        datetime(2026, 11, 3, 10, 5),
        650, "TARGET",
    )
    session_state.save_today([], day, [trade])
    report = daily_reports.build_daily_report(day)
    assert report["summary"]["closed_session_ledger_trades"] == 1
    assert report["summary"]["recorded_session_ledger_pnl"] == 650
    assert report["trades"][0]["exit_reason"] == "TARGET"
