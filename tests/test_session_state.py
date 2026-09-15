from datetime import date
import json

import app.session_state as session_state


def test_save_and_load_today(tmp_path, monkeypatch):
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", path)

    session_state.save_today([23300, 23301, 23301, 23302], date(2026, 9, 15))

    assert session_state.load_today(date(2026, 9, 15)) == [23300.0, 23301.0, 23302.0]


def test_previous_day_is_never_restored(tmp_path, monkeypatch):
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", path)

    session_state.save_today([23300, 23310], date(2026, 9, 14))

    assert session_state.load_today(date(2026, 9, 15)) == []


def test_corrupt_state_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", path)
    path.write_text("not-json", encoding="utf-8")

    assert session_state.load_today(date(2026, 9, 15)) == []


def test_history_is_bounded_and_invalid_values_are_removed(tmp_path, monkeypatch):
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", path)

    session_state.save_today([float(i) for i in range(1, 1000)] + [0, -1, "bad"], date(2026, 9, 15))
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert len(payload["spot_history"]) == 597
    assert payload["spot_history"][0] == 403.0
    assert payload["spot_history"][-1] == 999.0
    assert all(float(x) > 0 for x in payload["spot_history"])
