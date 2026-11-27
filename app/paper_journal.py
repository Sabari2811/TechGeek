"""Append-only journal for simulated PAPER order lifecycle events."""
import json
from datetime import datetime
from .config import IST
from .storage import DATA_ROOT, CAMPAIGN_ID


PAPER_TRADE_ROOT = DATA_ROOT / "paper_trades"


def record_paper_trade_event(trade_id: str, event: str, details: dict | None = None) -> None:
    now = datetime.now(IST)
    path = PAPER_TRADE_ROOT / f"{now.date().isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": now.isoformat(),
        "campaign_id": CAMPAIGN_ID,
        "trade_id": str(trade_id),
        "event": str(event),
        "details": details if isinstance(details, dict) else {},
        "simulated": True,
        "broker_order_submitted": False,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False, default=str) + "\n")
