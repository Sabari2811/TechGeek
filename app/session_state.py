"""Persist only today's intraday spot history for safe process restarts."""

import json
import math
import os
from datetime import date
from pathlib import Path


STATE_PATH = Path(".quantnifty/session_state.json")
MAX_POINTS = 600


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


def load_today(today: date | None = None) -> list[float]:
    """Load history only when the persisted date is today."""
    today = today or date.today()
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
        return []

    if not isinstance(payload, dict) or payload.get("date") != today.isoformat():
        return []
    return _clean_prices(payload.get("spot_history"))


def save_today(prices: list[float], today: date | None = None) -> None:
    """Atomically persist today's bounded spot history; never persist secrets."""
    today = today or date.today()
    cleaned = _clean_prices(prices)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"date": today.isoformat(), "spot_history": cleaned}
    temp_path = STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(temp_path, STATE_PATH)
