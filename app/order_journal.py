"""Durable local journal for broker order intent and reconciliation.

Any order intent without a confirmed terminal journal event is unresolved.
On startup, unresolved intents must block new entries until manually reconciled.
This journal deliberately does not guess whether a broker order filled.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JOURNAL_ROOT = Path(".quantnifty/orders")
IST = ZoneInfo("Asia/Kolkata")


def record_order_event(client_order_ref: str, event: str, details: dict | None = None) -> Path:
    now = datetime.now(IST)
    path = JOURNAL_ROOT / f"{now.date().isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": now.isoformat(),
        "client_order_ref": str(client_order_ref),
        "event": str(event),
        "details": details if isinstance(details, dict) else {},
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False, default=str) + "\n")
    return path


def unresolved_orders(root: Path | None = None) -> dict[str, dict]:
    """Return latest order states without a confirmed terminal outcome."""
    root = root or JOURNAL_ROOT
    latest: dict[str, dict] = {}
    if not root.exists():
        return {}
    for path in sorted(root.glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            # Unreadable journal is itself a fail-closed condition.
            return {"__journal_unreadable__": {"event": "unreadable", "path": str(path)}}
        for line in lines:
            try:
                row = json.loads(line)
                ref = str(row["client_order_ref"])
                event = str(row["event"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return {"__journal_corrupt__": {"event": "corrupt", "path": str(path)}}
            latest[ref] = row
    terminal = {"terminal_filled", "terminal_no_fill", "terminal_partial_fill"}
    return {ref: row for ref, row in latest.items() if row.get("event") not in terminal}


def enforce_startup_reconciliation() -> dict[str, dict]:
    """Trip the entry kill switch if any order journal item is unresolved."""
    from .kill_switch import set_enabled

    unresolved = unresolved_orders()
    if unresolved:
        refs = ", ".join(list(unresolved)[:5])
        set_enabled(True, f"unresolved order journal at startup: {refs}")
    return unresolved
