"""Persistent fail-closed entry kill switch.

The switch is local operator state, intentionally separate from strategy state.
A missing file means disabled; a malformed/unreadable file means enabled so
corrupt state can never silently re-enable entries.
"""
import json
import os
from datetime import datetime
from pathlib import Path

KILL_SWITCH_PATH = Path(".quantnifty/kill_switch.json")


def status() -> tuple[bool, str]:
    try:
        payload = json.loads(KILL_SWITCH_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False, "not set"
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return True, "state unreadable; fail-closed"
    if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
        return True, "state invalid; fail-closed"
    return payload["enabled"], str(payload.get("reason") or ("enabled" if payload["enabled"] else "not set"))


def set_enabled(enabled: bool, reason: str = "") -> None:
    """Persist an explicit operator choice using an atomic replace."""
    if not isinstance(enabled, bool):
        raise TypeError("enabled must be a boolean")
    KILL_SWITCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": enabled,
        "reason": str(reason).strip()[:300],
        "updated_at": datetime.now().astimezone().isoformat(),
    }
    temp_path = KILL_SWITCH_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(temp_path, KILL_SWITCH_PATH)
