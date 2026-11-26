import json
import zipfile
from io import BytesIO

import pytest

import app.research_sync as sync


def test_jsonl_batch_contains_only_new_records_and_redacts(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "DATA_ROOT", tmp_path / ".quantnifty")
    monkeypatch.setattr(sync, "STATE_PATH", tmp_path / "sync-state.json")
    raw_dir = sync.DATA_ROOT / "raw"
    audit_dir = sync.DATA_ROOT / "audit"
    raw_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    day = "2026-11-26"
    raw_path = raw_dir / f"{day}.jsonl"
    audit_path = audit_dir / f"{day}.jsonl"
    raw_path.write_text(
        '{"timestamp":"2026-11-26T10:00:00+05:30","data":{"ltp":123,"access_token":"secret"}}\n',
        encoding="utf-8",
    )
    audit_path.write_text(
        '{"event_type":"signal_rejected","payload":{"reason":"spread too wide"}}\n',
        encoding="utf-8",
    )

    archive, state, source_bytes = sync.build_batch_archive(day, {})
    assert source_bytes > 0
    with zipfile.ZipFile(BytesIO(archive)) as zf:
        raw = zf.read(f"raw/{day}.jsonl").decode()
        audit = zf.read(f"audit/{day}.jsonl").decode()
    assert "secret" not in raw
    assert "[REDACTED]" in raw
    assert "spread too wide" in audit

    # Simulate a successful first upload cursor: next batch must be empty.
    second, _, _ = sync.build_batch_archive(day, state)
    assert second == b""


def test_report_json_is_parsed_redacted_and_raw_arrays_are_not_duplicated():
    report = {
        "summary": {"closed_session_ledger_trades": 1},
        "trades": [{"symbol": "NIFTY", "pnl": -125.0}],
        "api_token": "must-not-leak",
        "raw_audit_events": [{"event_type": "duplicate"}],
        "raw_option_chain_snapshots": [{"data": "duplicate"}],
    }
    safe = json.loads(sync._redact_text(json.dumps(report).encode()))
    assert safe["summary"]["closed_session_ledger_trades"] == 1
    assert safe["api_token"] == "[REDACTED]"
    assert "raw_audit_events" not in safe
    assert "raw_option_chain_snapshots" not in safe


def test_non_private_destination_is_refused():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"private": False}

    class Client:
        def get(self, url):
            return Response()

    with pytest.raises(sync.ResearchSyncError, match="not private"):
        sync._verify_private_repo(Client(), "owner/public-repo")


def test_live_mode_is_refused_before_network(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(sync, "CONFIG", SimpleNamespace(mode="LIVE", live_enabled=lambda: False))
    with pytest.raises(sync.ResearchSyncError, match="PAPER-only"):
        sync.upload_batch("2026-11-26")


def test_explicit_empty_state_does_not_load_persisted_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "DATA_ROOT", tmp_path / ".quantnifty")
    monkeypatch.setattr(sync, "STATE_PATH", tmp_path / "sync-state.json")
    raw_dir = sync.DATA_ROOT / "raw"
    raw_dir.mkdir(parents=True)
    day = "2026-11-26"
    raw_path = raw_dir / f"{day}.jsonl"
    raw_path.write_text('{"ltp":123}\n', encoding="utf-8")

    # An explicit empty cursor means upload from byte zero, even if a saved
    # cursor exists from an earlier run.
    sync.STATE_PATH.write_text(json.dumps({"offsets": {raw_path.as_posix(): raw_path.stat().st_size}}), encoding="utf-8")
    archive, next_state, source_bytes = sync.build_batch_archive(day, {})

    assert source_bytes > 0
    assert next_state["offsets"][raw_path.as_posix()] == raw_path.stat().st_size
    with zipfile.ZipFile(BytesIO(archive)) as zf:
        assert zf.read(f"raw/{day}.jsonl").decode().strip() == '{"ltp":123}'
