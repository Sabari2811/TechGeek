"""Persist today's bounded spot history and closed trade ledger for safe restarts."""

import json
import math
import os
from datetime import date, datetime
from pathlib import Path

from .models import Position, TradeRecord, TradeSignal


STATE_PATH = Path(".quantnifty/session_state.json")
_PRESERVE_POSITION = object()
MAX_POINTS = 600
MAX_TRADES = 100


def _clean_prices(values: object) -> list[float]:
    if not isinstance(values, list):
        return []
    prices: list[float] = []
    for value in values[-MAX_POINTS:]:
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(price) and price > 0:
            if not prices or prices[-1] != price:
                prices.append(price)
    return prices[-MAX_POINTS:]


def _trade_to_dict(trade: TradeRecord) -> dict:
    return {
        "symbol": trade.symbol,
        "option_type": trade.option_type,
        "strike": trade.strike,
        "entry_price": trade.entry_price,
        "stop_price": trade.stop_price,
        "exit_price": trade.exit_price,
        "quantity": trade.quantity,
        "opened_at": trade.opened_at.isoformat(),
        "closed_at": trade.closed_at.isoformat(),
        "pnl": trade.pnl,
        "exit_reason": trade.exit_reason,
    }


def _dict_to_trade(value: object) -> TradeRecord | None:
    if not isinstance(value, dict):
        return None
    try:
        opened_at = datetime.fromisoformat(str(value["opened_at"]))
        closed_at = datetime.fromisoformat(str(value["closed_at"]))
        record = TradeRecord(
            symbol=str(value["symbol"]),
            option_type=str(value["option_type"]),
            strike=float(value["strike"]),
            entry_price=float(value["entry_price"]),
            stop_price=float(value["stop_price"]),
            exit_price=float(value["exit_price"]),
            quantity=int(value["quantity"]),
            opened_at=opened_at,
            closed_at=closed_at,
            pnl=float(value["pnl"]),
            exit_reason=str(value["exit_reason"]),
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    numeric = (record.strike, record.entry_price, record.stop_price,
               record.exit_price, record.pnl)
    if not all(math.isfinite(v) for v in numeric) or record.quantity <= 0:
        return None
    return record


def load_today(today: date | None = None) -> list[float]:
    today = today or date.today()
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
        return []

    if not isinstance(payload, dict) or payload.get("date") != today.isoformat():
        return []
    return _clean_prices(payload.get("spot_history"))


def load_today_trades(today: date | None = None) -> list[TradeRecord]:
    today = today or date.today()
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(payload, dict) or payload.get("date") != today.isoformat():
        return []
    raw = payload.get("closed_trades", [])
    if not isinstance(raw, list):
        return []
    trades = []
    for value in raw[-MAX_TRADES:]:
        trade = _dict_to_trade(value)
        if trade is not None:
            trades.append(trade)
    return trades


def save_today(prices: list[float], today: date | None = None,
               closed_trades: list[TradeRecord] | None = None,
               open_position=_PRESERVE_POSITION) -> None:
    today = today or date.today()
    cleaned = _clean_prices(prices)
    existing_trades = closed_trades if closed_trades is not None else load_today_trades(today)
    if open_position is _PRESERVE_POSITION:
        try:
            previous = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if not isinstance(previous, dict) or previous.get("date") != today.isoformat():
                previous = {}
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
            previous = {}
        stored_position = previous.get("open_position")
    else:
        stored_position = _position_to_dict(open_position)
    payload = {
        "date": today.isoformat(),
        "spot_history": cleaned,
        "closed_trades": [_trade_to_dict(t) for t in existing_trades[-MAX_TRADES:]],
        "open_position": stored_position,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(temp_path, STATE_PATH)


def _position_to_dict(position: Position | None) -> dict | None:
    if position is None:
        return None
    s = position.signal
    return {
        "signal": {
            "action": s.action, "option_type": s.option_type, "strike": s.strike,
            "security_id": s.security_id, "symbol": s.symbol, "entry": s.entry,
            "stop": s.stop, "target": s.target, "quantity": s.quantity,
            "probability": s.probability, "fair_value": s.fair_value,
            "expected_value": s.expected_value, "net_expected_value": s.net_expected_value,
            "reason": s.reason, "score": s.score, "checks": s.checks,
            "score_components": s.score_components, "market_phase": s.market_phase,
            "direction_bias": s.direction_bias,
        },
        "entry_price": position.entry_price, "quantity": position.quantity,
        "opened_at": position.opened_at.isoformat(), "current_price": position.current_price,
        "exit_price": position.exit_price, "exit_reason": position.exit_reason,
        "initial_quantity": position.initial_quantity,
        "exit_filled_quantity": position.exit_filled_quantity,
        "exit_proceeds": position.exit_proceeds,
    }


def _dict_to_position(value: object) -> Position | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("signal"), dict):
        raise ValueError("Persisted open position is malformed; startup must remain blocked")
    try:
        signal = TradeSignal(**value["signal"])
        position = Position(
            signal=signal, entry_price=float(value["entry_price"]),
            quantity=int(value["quantity"]),
            opened_at=datetime.fromisoformat(str(value["opened_at"])),
            current_price=float(value.get("current_price", value["entry_price"])),
            exit_price=float(value.get("exit_price", 0.0)),
            exit_reason=str(value.get("exit_reason", "")),
            initial_quantity=int(value.get("initial_quantity", value["quantity"])),
            exit_filled_quantity=int(value.get("exit_filled_quantity", 0)),
            exit_proceeds=float(value.get("exit_proceeds", 0.0)),
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Persisted open position is invalid; startup must remain blocked") from exc
    numbers = (position.entry_price, position.current_price, position.exit_price,
               position.exit_proceeds, signal.entry, signal.stop, signal.target, signal.strike)
    if (not all(math.isfinite(number) for number in numbers) or position.entry_price <= 0
            or position.quantity <= 0 or position.initial_quantity <= 0
            or position.exit_filled_quantity < 0
            or position.exit_filled_quantity >= position.initial_quantity
            or position.quantity + position.exit_filled_quantity != position.initial_quantity):
        raise ValueError("Persisted open position failed integrity checks; startup must remain blocked")
    position.quote_stale = True
    position.quote_source = "restart_recovery"
    position.quote_bid = 0.0
    position.quote_ask = 0.0
    position.quote_age_seconds = float("inf")
    return position


def load_today_open_position(today: date | None = None) -> Position | None:
    today = today or date.today()
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("Session state cannot be read; refusing startup with unknown position state") from exc
    if not isinstance(payload, dict):
        raise ValueError("Session state format is invalid; refusing startup with unknown position state")
    if payload.get("date") != today.isoformat():
        if payload.get("open_position") is not None:
            raise ValueError("Prior-session PAPER position remains unresolved; manual review required")
        return None
    return _dict_to_position(payload.get("open_position"))
