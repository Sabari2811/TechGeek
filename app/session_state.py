"""Persist today's bounded spot history and closed trade ledger for safe restarts."""

import json
import math
import os
from datetime import date, datetime
from pathlib import Path

from .models import TradeRecord


STATE_PATH = Path(".quantnifty/session_state.json")
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
               closed_trades: list[TradeRecord] | None = None) -> None:
    today = today or date.today()
    cleaned = _clean_prices(prices)
    existing_trades = closed_trades if closed_trades is not None else load_today_trades(today)
    payload = {
        "date": today.isoformat(),
        "spot_history": cleaned,
        "closed_trades": [_trade_to_dict(t) for t in existing_trades[-MAX_TRADES:]],
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(temp_path, STATE_PATH)


OPEN_POSITION_PATH = Path(".quantnifty/open_position.json")


def _position_to_dict(position) -> dict:
    signal = position.signal
    return {
        "version": 1,
        "trade_date": position.opened_at.date().isoformat(),
        "signal": {
            "action": signal.action, "option_type": signal.option_type,
            "strike": signal.strike, "security_id": signal.security_id,
            "symbol": signal.symbol, "entry": signal.entry,
            "stop": signal.stop, "target": signal.target,
            "quantity": signal.quantity, "probability": signal.probability,
            "fair_value": signal.fair_value, "expected_value": signal.expected_value,
            "net_expected_value": signal.net_expected_value, "reason": signal.reason,
            "score": signal.score, "checks": signal.checks,
            "score_components": signal.score_components,
            "market_phase": signal.market_phase, "direction_bias": signal.direction_bias,
        },
        "entry_price": position.entry_price,
        "quantity": position.quantity,
        "opened_at": position.opened_at.isoformat(),
        "initial_quantity": position.initial_quantity,
        "exit_filled_quantity": position.exit_filled_quantity,
        "exit_proceeds": position.exit_proceeds,
        "exit_reason": position.exit_reason,
    }


def _dict_to_position(payload: object, today: date):
    from .models import Position, TradeSignal

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("unsupported or corrupt open-position state")
    if payload.get("trade_date") != today.isoformat():
        raise ValueError("open position belongs to a different trading date; manual review required")
    raw = payload.get("signal")
    if not isinstance(raw, dict):
        raise ValueError("open-position signal is missing")
    try:
        signal = TradeSignal(
            action=str(raw["action"]), option_type=str(raw["option_type"]),
            strike=float(raw["strike"]), security_id=str(raw["security_id"]),
            symbol=str(raw["symbol"]), entry=float(raw["entry"]),
            stop=float(raw["stop"]), target=float(raw["target"]),
            quantity=int(raw["quantity"]), probability=float(raw["probability"]),
            fair_value=float(raw["fair_value"]), expected_value=float(raw["expected_value"]),
            net_expected_value=float(raw["net_expected_value"]), reason=str(raw["reason"]),
            score=float(raw.get("score", 0.0)),
            checks=dict(raw.get("checks", {})),
            score_components=dict(raw.get("score_components", {})),
            market_phase=str(raw.get("market_phase", "UNKNOWN")),
            direction_bias=str(raw.get("direction_bias", "NEUTRAL")),
        )
        opened_at = datetime.fromisoformat(str(payload["opened_at"]))
        position = Position(
            signal=signal, entry_price=float(payload["entry_price"]),
            quantity=int(payload["quantity"]), opened_at=opened_at,
            current_price=float(payload["entry_price"]),
            initial_quantity=int(payload.get("initial_quantity", payload["quantity"])),
            exit_filled_quantity=int(payload.get("exit_filled_quantity", 0)),
            exit_proceeds=float(payload.get("exit_proceeds", 0.0)),
            exit_reason=str(payload.get("exit_reason", "")),
            quote_stale=True, quote_source="restart_restore",
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid open-position state; manual review required") from exc
    numeric = (position.entry_price, signal.entry, signal.stop, signal.target,
               position.exit_proceeds, signal.strike)
    if (not all(math.isfinite(v) for v in numeric) or position.entry_price <= 0
            or signal.stop <= 0 or signal.target <= 0 or position.quantity <= 0
            or position.initial_quantity < position.quantity
            or position.exit_filled_quantity + position.quantity != position.initial_quantity
            or position.exit_filled_quantity < 0 or position.exit_proceeds < 0
            or not signal.security_id or not signal.symbol):
        raise ValueError("open-position state failed integrity validation; manual review required")
    return position


def save_open_position(position, today: date | None = None) -> None:
    today = today or date.today()
    if position is None or position.quantity <= 0:
        raise ValueError("only a positive-quantity open position can be persisted")
    if position.opened_at.date() != today:
        raise ValueError("refusing to persist a position from another trading date")
    OPEN_POSITION_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = OPEN_POSITION_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(_position_to_dict(position), separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    os.replace(temp_path, OPEN_POSITION_PATH)


def load_open_position(today: date | None = None):
    today = today or date.today()
    try:
        payload = json.loads(OPEN_POSITION_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("open-position state is unreadable; manual review required") from exc
    return _dict_to_position(payload, today)


def clear_open_position() -> None:
    try:
        OPEN_POSITION_PATH.unlink()
    except FileNotFoundError:
        return
