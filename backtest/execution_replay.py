"""Offline replay of captured live-position quotes.

This is a diagnostic simulation, not a broker-fill reconstruction. It uses
recorded option LTP to detect stop/target triggers and recorded bid as a
conservative exit-price proxy. It cannot infer depth, partial fills, fees,
slippage, or whether an order actually filled.
"""
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class PositionReplay:
    security_id: str
    symbol: str
    opened_at: str
    entry_price: float
    quantity: int
    stop_price: float
    target_price: float
    quote_count: int = 0
    first_quote_at: str = ""
    last_quote_at: str = ""
    exit_reason: str = "OPEN_AT_END_OF_CAPTURE"
    exit_price: float = 0.0
    gross_pnl: float = 0.0
    pnl_is_realized: bool = False
    data_warnings: list[str] | None = None


def _finite_positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def load_audit_events(path: str | Path) -> list[dict]:
    events = []
    try:
        stream = Path(path).open("r", encoding="utf-8")
    except OSError:
        return events
    with stream:
        for line_number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not isinstance(row.get("payload"), dict):
                continue
            row["_line_number"] = line_number
            events.append(row)
    return events


def replay_position_quotes(path: str | Path) -> list[PositionReplay]:
    events = load_audit_events(path)
    quotes = [event for event in events
              if event.get("event_type") == "position_quote"]
    groups: dict[tuple[str, str], list[dict]] = {}
    for event in quotes:
        payload = event["payload"]
        key = (str(payload.get("security_id") or ""),
               str(payload.get("opened_at") or ""))
        if not key[0] or not key[1]:
            continue
        groups.setdefault(key, []).append(event)

    results = []
    for (security_id, opened_at), rows in groups.items():
        rows.sort(key=lambda row: str(row.get("timestamp") or ""))
        first = rows[0]["payload"]
        entry = _finite_positive(first.get("entry_price"))
        stop = _finite_positive(first.get("stop_price"))
        target = _finite_positive(first.get("target_price"))
        try:
            quantity = int(first.get("quantity", 0))
        except (TypeError, ValueError, OverflowError):
            quantity = 0
        warnings = []
        if not entry or not stop or not target or quantity <= 0:
            warnings.append("invalid entry/stop/target/quantity; P&L not calculated")
        result = PositionReplay(
            security_id=security_id,
            symbol=str(first.get("symbol") or ""),
            opened_at=opened_at,
            entry_price=entry or 0.0,
            quantity=max(quantity, 0),
            stop_price=stop or 0.0,
            target_price=target or 0.0,
            data_warnings=warnings,
        )
        for event in rows:
            payload = event["payload"]
            ltp = _finite_positive(payload.get("ltp"))
            bid = _finite_positive(payload.get("bid"))
            if ltp is None or bid is None:
                result.data_warnings.append(
                    f"line {event.get('_line_number')}: invalid LTP/bid ignored"
                )
                continue
            result.quote_count += 1
            stamp = str(event.get("timestamp") or "")
            if not result.first_quote_at:
                result.first_quote_at = stamp
            result.last_quote_at = stamp
            if result.exit_reason != "OPEN_AT_END_OF_CAPTURE":
                continue
            if not entry or not stop or not target or quantity <= 0:
                continue
            if ltp <= stop:
                result.exit_reason = "STOP_TRIGGER_OBSERVED"
                result.exit_price = bid
                result.pnl_is_realized = False
            elif ltp >= target:
                result.exit_reason = "TARGET_TRIGGER_OBSERVED"
                result.exit_price = bid
                result.pnl_is_realized = False

        if entry and result.exit_price > 0 and quantity > 0:
            result.gross_pnl = (result.exit_price - entry) * quantity
        elif entry and quantity > 0 and result.quote_count:
            # An open-at-end result is mark-to-market only, not realized P&L.
            last_valid = next((event["payload"] for event in reversed(rows)
                               if _finite_positive(event["payload"].get("bid"))), None)
            if last_valid:
                result.exit_price = float(last_valid["bid"])
                result.gross_pnl = (result.exit_price - entry) * quantity
        results.append(result)

    return sorted(results, key=lambda row: (row.opened_at, row.security_id))


def reconcile_recorded_fills(path: str | Path) -> list[dict]:
    """Reconcile recorded entry/exit fill events without inferring missing fills.

    LIVE-mode events are emitted only after a broker-reported fill. PAPER-mode
    events represent simulated fills. This function does not query the broker.
    """
    events = load_audit_events(path)
    positions: dict[tuple[str, str], dict] = {}
    for event in events:
        kind = event.get("event_type")
        payload = event["payload"]
        if kind not in {"entry_filled", "exit_fill"}:
            continue
        security_id = str(payload.get("security_id") or "")
        opened_at = str(payload.get("position_opened_at") or "")
        if not security_id or not opened_at:
            continue
        key = (security_id, opened_at)
        if kind == "entry_filled":
            try:
                entry_price = float(payload.get("entry_price"))
                quantity = int(payload.get("filled_quantity"))
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(entry_price) or entry_price <= 0 or quantity <= 0:
                continue
            positions[key] = {
                "security_id": security_id,
                "symbol": str(payload.get("symbol") or ""),
                "position_opened_at": opened_at,
                "entry_price": entry_price,
                "entry_filled_quantity": quantity,
                "mode": str(payload.get("mode") or "UNKNOWN"),
                "exit_filled_quantity": 0,
                "exit_proceeds": 0.0,
                "exit_events": 0,
                "last_exit_reason": "",
                "last_event_at": str(event.get("timestamp") or ""),
                "warnings": [],
            }
            continue
        position = positions.get(key)
        if position is None:
            # Do not synthesize an entry when an exit is found without its entry.
            continue
        try:
            fill_price = float(payload.get("fill_price"))
            filled_quantity = int(payload.get("filled_quantity"))
        except (TypeError, ValueError, OverflowError):
            position["warnings"].append("invalid exit fill event ignored")
            continue
        if not math.isfinite(fill_price) or fill_price <= 0 or filled_quantity <= 0:
            position["warnings"].append("invalid exit fill event ignored")
            continue
        position["exit_filled_quantity"] += filled_quantity
        position["exit_proceeds"] += fill_price * filled_quantity
        position["exit_events"] += 1
        position["last_exit_reason"] = str(payload.get("reason") or "")
        position["last_event_at"] = str(event.get("timestamp") or "")
        if position["exit_filled_quantity"] > position["entry_filled_quantity"]:
            position["warnings"].append("exit fills exceed recorded entry fills")

    results = []
    for position in positions.values():
        exited = position["exit_filled_quantity"]
        entered = position["entry_filled_quantity"]
        position["remaining_quantity"] = max(0, entered - exited)
        position["fully_exited_in_recorded_events"] = exited == entered
        position["average_exit_price"] = (
            position["exit_proceeds"] / exited if exited > 0 else None
        )
        position["recorded_gross_pnl"] = round(
            position["exit_proceeds"] - position["entry_price"] * exited, 2
        )
        position["pnl_is_realized_in_recorded_events"] = exited == entered and entered > 0
        position["classification"] = (
            "PAPER_SIMULATED_FILL" if position["mode"].upper() != "LIVE"
            else ("RECORDED_LIVE_FILL_EVENTS" if exited == entered
                  else "LIVE_POSITION_NOT_FULLY_RECONCILED")
        )
        results.append(position)
    return sorted(results, key=lambda row: (row["position_opened_at"], row["security_id"]))


def write_report(audit_path: str | Path, output_path: str | Path) -> dict:
    positions = replay_position_quotes(audit_path)
    closed_triggered = sum(row.exit_reason != "OPEN_AT_END_OF_CAPTURE" for row in positions)
    recorded_fills = reconcile_recorded_fills(audit_path)
    payload = {
        "report_type": "diagnostic_position_quote_replay",
        "source": str(audit_path),
        "positions": [asdict(row) for row in positions],
        "recorded_fill_reconciliation": recorded_fills,
        "summary": {
            "positions_observed": len(positions),
            "positions_with_stop_or_target_trigger": closed_triggered,
            "positions_open_at_end_of_capture": len(positions) - closed_triggered,
            "gross_pnl_sum": round(sum(row.gross_pnl for row in positions), 2),
            "warning": (
                "Diagnostic estimate only. Gross P&L uses captured bid as a proxy; "
                "no broker fills, partial fills, fees, slippage, or depth are reconstructed."
            ),
        },
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Replay recorded position quotes (diagnostic only)")
    parser.add_argument("audit_file", help="Path to .quantnifty/audit/YYYY-MM-DD.jsonl")
    parser.add_argument("--output", default=".quantnifty/reports/execution-replay.json")
    args = parser.parse_args()
    report = write_report(args.audit_file, args.output)
    print(json.dumps(report["summary"], indent=2))
    print(f"report={args.output}")
