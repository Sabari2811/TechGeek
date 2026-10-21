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
    terminal = {"terminal_no_fill", "reconciled"}
    return {ref: row for ref, row in latest.items() if row.get("event") not in terminal}


def enforce_startup_reconciliation() -> dict[str, dict]:
    """Trip the entry kill switch if any order journal item is unresolved."""
    from .kill_switch import set_enabled

    unresolved = unresolved_orders()
    if unresolved:
        refs = ", ".join(list(unresolved)[:5])
        set_enabled(True, f"unresolved order journal at startup: {refs}")
    return unresolved



def mark_reconciled(client_order_ref: str, reason: str) -> Path:
    """Record explicit operator reconciliation after checking broker state."""
    if not str(reason).strip():
        raise ValueError("A reconciliation reason is required")
    return record_order_event(
        client_order_ref,
        "reconciled",
        {"reason": str(reason).strip()[:300], "operator_confirmed": True},
    )


def read_only_broker_order_reconciliation(broker_orders, root: Path | None = None) -> dict:
    """Compare journaled order IDs with a supplied broker order-book snapshot.

    This function is intentionally read-only: it never marks journal entries
    reconciled, never submits/cancels orders, and cannot establish whether the
    account has an open position. Callers must supply an order-book response
    already obtained through the existing, documented client method.
    """
    if not isinstance(broker_orders, list):
        raise TypeError("broker_orders must be a list returned by the broker order-book client")

    latest_by_ref: dict[str, dict] = {}
    root = root or JOURNAL_ROOT
    if root.exists():
        for path in sorted(root.glob("*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                return {"status": "BLOCKED", "reason": "journal_unreadable", "path": str(path), "error": str(exc), "orders": []}
            for line_number, line in enumerate(lines, 1):
                try:
                    row = json.loads(line)
                    ref = str(row["client_order_ref"])
                    event = str(row["event"])
                    details = row.get("details", {})
                    if not isinstance(details, dict):
                        raise ValueError("details must be an object")
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    return {"status": "BLOCKED", "reason": "journal_corrupt", "path": str(path), "line": line_number, "error": str(exc), "orders": []}
                latest_by_ref[ref] = row

    broker_by_id: dict[str, list[dict]] = {}
    for order in broker_orders:
        if not isinstance(order, dict):
            continue
        order_id = order.get("id") or order.get("order_id")
        if order_id is not None and str(order_id).strip():
            broker_by_id.setdefault(str(order_id), []).append(order)

    results = []
    for ref, row in latest_by_ref.items():
        if row.get("event") in {"reconciled", "terminal_no_fill"}:
            continue
        details = row.get("details", {})
        order_id = details.get("order_id")
        if not order_id:
            results.append({
                "client_order_ref": ref,
                "journal_event": row.get("event"),
                "status": "MANUAL_REVIEW_REQUIRED",
                "reason": "journal_has_no_broker_order_id",
            })
            continue
        matches = broker_by_id.get(str(order_id), [])
        if len(matches) != 1:
            results.append({
                "client_order_ref": ref,
                "order_id": str(order_id),
                "journal_event": row.get("event"),
                "status": "MANUAL_REVIEW_REQUIRED",
                "reason": "broker_order_missing_or_ambiguous",
                "broker_match_count": len(matches),
            })
            continue
        broker = matches[0]
        results.append({
            "client_order_ref": ref,
            "order_id": str(order_id),
            "journal_event": row.get("event"),
            "broker_status": str(broker.get("status") or broker.get("order_status") or "").strip().upper(),
            "broker_traded_quantity": _safe_nonnegative_int(broker.get("traded_qty", broker.get("filled_quantity", 0))),
            "journal_traded_quantity": _safe_nonnegative_int(details.get("traded_quantity", details.get("filled_quantity", 0))),
            "status": "MATCHED_ORDER_ONLY_MANUAL_POSITION_CHECK_REQUIRED",
        })

    return {
        "status": "REVIEW_REQUIRED" if results else "NO_UNRESOLVED_JOURNAL_ORDERS",
        "read_only": True,
        "broker_positions_checked": False,
        "orders": results,
        "warning": "Order-book matching does not prove the account is flat. Do not clear the kill switch until broker positions and fills are independently verified.",
    }


def _safe_nonnegative_int(value) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, number)



if __name__ == "__main__":
    import argparse
    import asyncio
    import json

    parser = argparse.ArgumentParser(
        description="Order journal tools. Broker order-book report is read-only; position confirmation remains manual."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--reconcile", metavar="CLIENT_ORDER_REF", help="Record operator-confirmed reconciliation (after checking broker orders AND positions)")
    action.add_argument("--report-broker-order-book", action="store_true", help="Fetch the broker order book and print a read-only journal comparison")
    parser.add_argument("--reason", help="Required operator reason when using --reconcile")
    args = parser.parse_args()

    if args.report_broker_order_book:
        from .market import IndstocksClient
        from .config import CONFIG

        if not CONFIG.access_token:
            parser.error("INDSTOCKS_ACCESS_TOKEN is required for a read-only broker order-book report")
        async def run_report():
            client = IndstocksClient()
            try:
                orders = await client.order_book()
                report = read_only_broker_order_reconciliation(orders)
                print(json.dumps(report, indent=2, sort_keys=True))
            finally:
                await client.close()
        asyncio.run(run_report())
    else:
        if not args.reason or not args.reason.strip():
            parser.error("--reason is required with --reconcile")
        mark_reconciled(args.reconcile, args.reason)
        print(f"Recorded operator reconciliation for {args.reconcile}.")
