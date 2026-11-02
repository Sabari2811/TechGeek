from datetime import date, datetime

import pytest

import app.session_state as session_state
from app.models import Position, TradeSignal


def make_position():
    signal = TradeSignal(
        action="BUY", option_type="CE", strike=23500, security_id="SEC123",
        symbol="NIFTY-23500-CE", entry=120.0, stop=105.0, target=150.0,
        quantity=65, probability=0.62, fair_value=130.0, expected_value=12.0,
        net_expected_value=10.0, reason="paper test", score=0.7,
        checks={"spread": True, "depth": True},
        score_components={"momentum": 0.4}, market_phase="BREAKOUT",
        direction_bias="BULLISH",
    )
    return Position(
        signal=signal, entry_price=120.0, quantity=65,
        opened_at=datetime(2026, 11, 2, 10, 0),
        current_price=118.0,
    )


def test_open_position_round_trip_restores_as_stale(tmp_path, monkeypatch):
    path = tmp_path / "open_position.json"
    monkeypatch.setattr(session_state, "OPEN_POSITION_PATH", path)
    position = make_position()

    session_state.save_open_position(position, date(2026, 11, 2))
    restored = session_state.load_open_position(date(2026, 11, 2))

    assert restored is not None
    assert restored.signal.security_id == "SEC123"
    assert restored.quantity == 65
    assert restored.initial_quantity == 65
    assert restored.entry_price == 120.0
    assert restored.signal.stop == 105.0
    assert restored.signal.target == 150.0
    assert restored.quote_stale is True
    assert restored.quote_source == "restart_restore"


def test_partial_exit_state_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "open_position.json"
    monkeypatch.setattr(session_state, "OPEN_POSITION_PATH", path)
    position = make_position()
    position.quantity = 40
    position.exit_filled_quantity = 25
    position.exit_proceeds = 2900.0

    session_state.save_open_position(position, date(2026, 11, 2))
    restored = session_state.load_open_position(date(2026, 11, 2))

    assert restored.quantity == 40
    assert restored.exit_filled_quantity == 25
    assert restored.exit_proceeds == 2900.0
    assert restored.initial_quantity == 65


def test_previous_day_position_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "open_position.json"
    monkeypatch.setattr(session_state, "OPEN_POSITION_PATH", path)
    session_state.save_open_position(make_position(), date(2026, 11, 2))

    with pytest.raises(ValueError, match="different trading date"):
        session_state.load_open_position(date(2026, 11, 3))


def test_corrupt_open_position_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "open_position.json"
    monkeypatch.setattr(session_state, "OPEN_POSITION_PATH", path)
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="unreadable"):
        session_state.load_open_position(date(2026, 11, 2))


def test_clear_open_position_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "open_position.json"
    monkeypatch.setattr(session_state, "OPEN_POSITION_PATH", path)
    session_state.save_open_position(make_position(), date(2026, 11, 2))

    session_state.clear_open_position()
    session_state.clear_open_position()

    assert session_state.load_open_position(date(2026, 11, 2)) is None
