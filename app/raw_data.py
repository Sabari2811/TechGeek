"""Local raw market snapshot capture for deterministic post-market replay.

The recorder stores only provider responses, timestamps, and session metadata.
Secrets are never written. Files live under .quantnifty/ and are ignored by git.
"""
import json
import math
import re
from datetime import datetime
from pathlib import Path
from .config import IST

RAW_ROOT = Path(".quantnifty/raw")
AUDIT_ROOT = Path(".quantnifty/audit")


_SECRET_KEY_FRAGMENTS = (
    "token", "secret", "password", "authorization", "api_key", "apikey", "cookie",
)
_SECRET_VALUE_PATTERNS = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)([?&](?:access_token|refresh_token|api_key|apikey|token|client_secret|password)=)[^&\s]+"),
     r"\1[REDACTED]"),
)


def _json_safe(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            key_text = str(key)
            if any(fragment in key_text.lower() for fragment in _SECRET_KEY_FRAGMENTS):
                safe[key_text] = "[REDACTED]"
            else:
                safe[key_text] = _json_safe(item)
        return safe
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, str):
        safe_text = value
        for pattern, replacement in _SECRET_VALUE_PATTERNS:
            safe_text = pattern.sub(replacement, safe_text)
        return safe_text
    return value


def record_option_chain(payload: dict, expiry: str | None = None,
                        timestamp: datetime | None = None) -> Path:
    timestamp = timestamp or datetime.now(IST)
    day = timestamp.date().isoformat()
    path = RAW_ROOT / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": timestamp.isoformat(),
        "expiry": expiry,
        "source": "indstocks_option_chain",
        "data": _json_safe(payload),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
    return path


def load_option_chain_records(path: str | Path) -> list[dict]:
    p = Path(path)
    records = []
    if not p.exists():
        return records
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and isinstance(row.get("data"), dict):
                records.append(row)
    return records



def record_audit_event(event_type: str, payload: dict,
                       timestamp: datetime | None = None) -> Path:
    """Append a timestamped, JSON-safe decision/depth/execution audit event."""
    timestamp = timestamp or datetime.now(IST)
    path = AUDIT_ROOT / f"{timestamp.date().isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": timestamp.isoformat(),
        "event_type": str(event_type)[:80],
        "payload": _json_safe(payload if isinstance(payload, dict) else {}),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
    return path
