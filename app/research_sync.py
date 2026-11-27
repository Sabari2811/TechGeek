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
    """Return sorted ISO dates present in raw, audit, or reports folders."""
    days: set[str] = set()
    for folder in (DATA_ROOT / "raw", DATA_ROOT / "audit"):
        if folder.exists():
            for path in folder.glob("????-??-??.jsonl"):
                if path.is_file() and path.stat().st_size:
                    days.add(path.stem)
    reports = DATA_ROOT / "reports"
    if reports.exists():
        for path in reports.iterdir():
            if path.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name):
                if any(p.is_file() and p.stat().st_size for p in path.iterdir()):
                    days.add(path.name)
    return sorted(days)


def _read_new_bytes(path: Path, offset: int, max_bytes: int = MAX_SOURCE_BYTES) -> tuple[bytes, int]:
    if not path.exists():
        return b"", 0
    size = path.stat().st_size
    start = offset if 0 <= offset <= size else 0
    with path.open("rb") as stream:
        stream.seek(start)
        if path.suffix != ".jsonl":
            raw = stream.read()
            if len(raw) > max_bytes:
                raise ResearchSyncError(
                    f"{path} is {len(raw)} bytes; non-JSONL report exceeds the {max_bytes}-byte safe batch limit."
                )
            return raw, stream.tell()
        # Read complete JSONL records only. A single oversized record is allowed
        # through and then subject to the compressed archive cap.
        chunks = []
        total = 0
        while True:
            line = stream.readline()
            if not line:
                break
            if chunks and total + len(line) > max_bytes:
                stream.seek(-len(line), 1)
                break
            chunks.append(line)
            total += len(line)
            if total >= max_bytes:
                break
        return b"".join(chunks), stream.tell()


def build_batch_archive(
    day: str, state: dict | None = None, max_source_bytes: int = MAX_SOURCE_BYTES
) -> tuple[bytes, dict, int]:
    state = _load_state() if state is None else state
    offsets = dict(state.get("offsets", {}))
    manifest = {
        "schema_version": 2,
        "trading_date": day,
        "created_at": datetime.now(IST).isoformat(),
        "mode": CONFIG.mode,
        "files": [],
    }
    memory = BytesIO()
    total_new = 0
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in _candidate_files(day):
            key = path.as_posix()
            raw, end = _read_new_bytes(path, int(offsets.get(key, 0)), max_source_bytes)
            if not raw:
                continue
            safe = _redact_text(raw)
            if not safe:
                continue
            archive_name = str(path.relative_to(DATA_ROOT)).replace("\\", "/")
            archive.writestr(archive_name, safe)
            manifest["files"].append({
                "path": archive_name,
                "source_bytes": len(raw),
                "uploaded_bytes": len(safe),
                "start_offset": int(offsets.get(key, 0)),
                "end_offset": end,
            })
            offsets[key] = end
            total_new += len(raw)
        if not manifest["files"]:
            return b"", state, 0
        archive.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))
    payload = memory.getvalue()
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ResearchSyncError(
            f"Batch archive is {len(payload)} bytes; limit is {MAX_ARCHIVE_BYTES}. "
            "No cursor was advanced; reduce MAX_SOURCE_BYTES or inspect unusually large records."
        )
    return payload, {"offsets": offsets}, total_new


def _github_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _verify_private_repo(client: httpx.Client, repository: str) -> None:
    response = client.get(f"{API_ROOT}/repos/{repository}")
    response.raise_for_status()
    if response.json().get("private") is not True:
        raise ResearchSyncError(
            f"Destination {repository} is not private. Upload refused; create a private repository first."
        )


def _upload_one(day: str, token: str, repository: str) -> dict:
    state = _load_state()
    payload, next_state, source_bytes = build_batch_archive(day, state)
    if not payload:
        return {"status": "nothing_new", "trading_date": day, "source_bytes": 0}
    stamp = datetime.now(IST).strftime("%H%M%S")
    path = f"batches/{day}/paper-research-{stamp}-{time.time_ns()}.zip"
    with httpx.Client(headers=_github_headers(token), timeout=60.0) as client:
        _verify_private_repo(client, repository)
        response = client.put(
            f"{API_ROOT}/repos/{repository}/contents/{path}",
            json={
                "message": f"Add PAPER research batch {day} {stamp}",
                "content": base64.b64encode(payload).decode("ascii"),
            },
        )
        response.raise_for_status()
    # Advance offsets only after GitHub confirms the uploaded object.
    _save_state(next_state)
    return {
        "status": "uploaded",
        "repository": repository,
        "path": path,
        "trading_date": day,
        "source_bytes": source_bytes,
        "archive_bytes": len(payload),
    }


def upload_pending_batches(max_batches: int = DEFAULT_MAX_BATCHES_PER_RUN) -> dict:
    """Upload oldest pending date batches first, with bounded work per invocation."""
    if CONFIG.mode != "PAPER" or CONFIG.live_enabled():
        raise ResearchSyncError("Research sync is PAPER-only; live mode or live routing is not permitted.")
    token = os.getenv("GH_RESEARCH_TOKEN", "").strip()
    repository = os.getenv("GH_RESEARCH_REPOSITORY", "").strip()
    if not token or not repository or "/" not in repository:
        raise ResearchSyncError("Set GH_RESEARCH_TOKEN and GH_RESEARCH_REPOSITORY in the local environment.")
    if max_batches < 1:
        raise ValueError("max_batches must be at least 1")
    results = []
    for _ in range(max_batches):
        pending = discover_pending_dates()
        if not pending:
            break
        progressed = False
        for day in pending:
            result = _upload_one(day, token, repository)
            if result["status"] == "uploaded":
                results.append(result)
                progressed = True
                break
        if not progressed:
            break
    return {
        "status": "uploaded" if results else "nothing_new",
        "uploaded_batches": len(results),
        "remaining_dates": discover_pending_dates(),
        "batches": results,
    }


def upload_batch(day: str | None = None) -> dict:
    """Compatibility wrapper: upload one chunk for a date, or one oldest pending chunk."""
    if CONFIG.mode != "PAPER" or CONFIG.live_enabled():
        raise ResearchSyncError("Research sync is PAPER-only; live mode or live routing is not permitted.")
    token = os.getenv("GH_RESEARCH_TOKEN", "").strip()
    repository = os.getenv("GH_RESEARCH_REPOSITORY", "").strip()
    if not token or not repository or "/" not in repository:
        raise ResearchSyncError("Set GH_RESEARCH_TOKEN and GH_RESEARCH_REPOSITORY in the local environment.")
    target = day
    if target is None:
        dates = discover_pending_dates()
        if not dates:
            return {"status": "nothing_new", "trading_date": datetime.now(IST).date().isoformat(), "source_bytes": 0}
        target = dates[0]
    return _upload_one(target, token, repository)


def main() -> None:
    try:
        print(json.dumps(upload_pending_batches(), indent=2))
    except Exception as exc:
        raise SystemExit(f"Research sync failed: {type(exc).__name__}: {exc}") from exc


if __name__ == "__main__":
    main()
