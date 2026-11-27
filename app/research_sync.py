"""Batch-publish PAPER research evidence to a separately configured PRIVATE GitHub repo.

Uploads are incremental, date-discovered and bounded. This module never places
broker orders and refuses to run outside PAPER mode or against a public repo.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

import httpx

from .config import CONFIG, IST

STATE_PATH = Path(".quantnifty/github_sync_state.json")
DATA_ROOT = Path(".quantnifty")
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_BATCHES_PER_RUN = 5
API_ROOT = "https://api.github.com"
SECRET_KEY_PARTS = ("token", "secret", "password", "authorization", "api_key", "apikey", "cookie")
SECRET_PATTERNS = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)([?&](?:access_token|refresh_token|api_key|apikey|token|client_secret|password)=)[^&\s]+"), r"\1[REDACTED]"),
)


class ResearchSyncError(RuntimeError):
    pass


def _redact_text(raw: bytes) -> bytes:
    text = raw.decode("utf-8", errors="replace")
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        document = None
    if isinstance(document, dict):
        document.pop("raw_audit_events", None)
        document.pop("raw_option_chain_snapshots", None)
        return (json.dumps(_redact_value(document), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    lines = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            safe = line
            for pattern, replacement in SECRET_PATTERNS:
                safe = pattern.sub(replacement, safe)
            lines.append(safe)
            continue
        lines.append(json.dumps(_redact_value(row), ensure_ascii=False, separators=(",", ":")))
    return (("\n".join(lines) + "\n") if lines else "").encode("utf-8")


def _redact_value(value):
    if isinstance(value, dict):
        return {
            str(k): ("[REDACTED]" if any(p in str(k).lower() for p in SECRET_KEY_PARTS)
                     else _redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, str):
        for pattern, replacement in SECRET_PATTERNS:
            value = pattern.sub(replacement, value)
    return value


def _load_state() -> dict:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(value: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temp, STATE_PATH)


def _candidate_files(day: str) -> list[Path]:
    return [
        DATA_ROOT / "raw" / f"{day}.jsonl",
        DATA_ROOT / "audit" / f"{day}.jsonl",
        DATA_ROOT / "reports" / day / "daily_report.json",
        DATA_ROOT / "reports" / day / "analysis.md",
    ]


def discover_pending_dates() -> list[str]:
    """Return sorted dates with bytes beyond their durable upload cursors."""
    days: set[str] = set()
    state = _load_state()
    offsets = state.get("offsets", {})
    for folder in (DATA_ROOT / "raw", DATA_ROOT / "audit"):
        if folder.exists():
            for path in folder.glob("????-??-??.jsonl"):
                if path.is_file() and path.stat().st_size:
                    days.add(path.stem)
    reports = DATA_ROOT / "reports"
    if reports.exists():
        for path in reports.iterdir():
            if path.is_dir() and re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", path.name):
                days.add(path.name)
    pending = []
    for day in sorted(days):
        for path in _candidate_files(day):
            if not path.is_file() or not path.stat().st_size:
                continue
            offset = int(offsets.get(path.as_posix(), 0))
            if offset < path.stat().st_size or offset > path.stat().st_size:
                pending.append(day)
                break
    return pending
