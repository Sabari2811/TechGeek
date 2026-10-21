import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app import raw_data


def test_audit_events_are_separate_jsonl_and_timestamped(tmp_path, monkeypatch):
    monkeypatch.setattr(raw_data, "AUDIT_ROOT", tmp_path)
    timestamp = datetime(2026, 10, 21, 12, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    path = raw_data.record_audit_event(
        "microstructure_check",
        {"confirmed": False, "reason": "not enough depth", "value": float("nan")},
        timestamp=timestamp,
    )
    assert path.name == "2026-10-21.jsonl"
    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    event = json.loads(rows[0])
    assert event["event_type"] == "microstructure_check"
    assert event["timestamp"] == timestamp.isoformat()
    assert event["payload"]["confirmed"] is False
    assert event["payload"]["value"] is None


def test_option_chain_replay_loader_ignores_audit_files(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    path = raw / "2026-10-21.jsonl"
    path.write_text(
        json.dumps({"timestamp": "2026-10-21T12:00:00+05:30", "data": {"strikes": {}}}) + "\n",
        encoding="utf-8",
    )
    assert len(raw_data.load_option_chain_records(path)) == 1
