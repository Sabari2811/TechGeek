"""Local raw market snapshot capture for deterministic post-market replay.

The recorder stores only provider responses, timestamps, and session metadata.
Secrets are never written. Files live under .quantnifty/ and are ignored by git.
"""
import json
import math
from datetime import datetime
from pathlib import Path
from .config import IST

RAW_ROOT = Path(".quantnifty/raw")


def _json_safe(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
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
