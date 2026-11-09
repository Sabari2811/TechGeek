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

from datetime import datetime
from app.models import Position, TradeSignal


def _sample_position():
    signal = TradeSignal(
        action="BUY", option_type="CE", strike=22750, security_id="53792",
        symbol="NIFTY", entry=535.75, stop=512.45, target=577.68,
        quantity=65, probability=0.6, fair_value=550, expected_value=16,
        net_expected_value=14, reason="test", score=1.2,
        checks={"microstructure": True}, score_components={"trend": 0.4},
        market_phase="BREAKOUT", direction_bias="BULLISH",
    )
    return Position(signal=signal, entry_price=535.75, quantity=65,
                    opened_at=datetime(2026, 11, 2, 9, 38, 43), current_price=559.5)


def test_open_paper_position_survives_restart_and_quote_is_stale(tmp_path, monkeypatch):
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", path)
    session_state.save_today([23300], date(2026, 11, 2), [], _sample_position())
    restored = session_state.load_today_open_position(date(2026, 11, 2))
    assert restored is not None
    assert restored.signal.security_id == "53792"
    assert restored.quantity == 65
    assert restored.entry_price == 535.75
    assert restored.quote_stale is True
    assert restored.quote_bid == 0
    assert restored.quote_ask == 0


def test_malformed_open_position_fails_closed(tmp_path, monkeypatch):
    import pytest
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", path)
    path.write_text('{"date":"2026-11-02","open_position":{"bad":true}}')
    with pytest.raises(ValueError, match="startup must remain blocked"):
        session_state.load_today_open_position(date(2026, 11, 2))


def test_save_today_preserves_open_position_when_not_explicitly_changed(tmp_path, monkeypatch):
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", path)
    session_state.save_today([23300], date(2026, 11, 2), [], _sample_position())
    session_state.save_today([23300, 23301], date(2026, 11, 2), [])
    assert session_state.load_today_open_position(date(2026, 11, 2)) is not None


def test_prior_day_open_position_is_not_silently_discarded(tmp_path, monkeypatch):
    import pytest
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(session_state, "STATE_PATH", path)
    session_state.save_today([23300], date(2026, 11, 2), [], _sample_position())
    with pytest.raises(ValueError, match="Prior-session PAPER position"):
        session_state.load_today_open_position(date(2026, 11, 3))
