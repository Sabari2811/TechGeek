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
