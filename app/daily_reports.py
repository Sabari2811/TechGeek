"""Daily trade intelligence reports built from local QuantNifty evidence.

Reports are local artifacts under .quantnifty/reports and are never committed.
Recorded fills are distinguished from quote-based diagnostic estimates.
"""
import json
from collections import Counter
from datetime import date
from pathlib import Path

from .raw_data import RAW_ROOT, AUDIT_ROOT, load_option_chain_records
from .session_state import load_today_trades
from backtest.execution_replay import load_audit_events, reconcile_recorded_fills

REPORT_ROOT = Path(".quantnifty/reports")


def _redact(value):
    sensitive = ("token", "authorization", "password", "secret", "api_key", "apikey")
    if isinstance(value, dict):
        return {
            str(k): ("[REDACTED]" if any(word in str(k).lower() for word in sensitive)
                     else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _trade_dict(trade):
    return {
        "symbol": trade.symbol, "option_type": trade.option_type,
        "strike": trade.strike, "entry_price": trade.entry_price,
        "stop_price": trade.stop_price, "exit_price": trade.exit_price,
        "quantity": trade.quantity, "opened_at": trade.opened_at.isoformat(),
        "closed_at": trade.closed_at.isoformat(), "gross_or_recorded_pnl": trade.pnl,
        "exit_reason": trade.exit_reason,
        "pnl_quality": "SESSION_LEDGER_RECORDED; fees/net charges not independently verified",
    }


def build_daily_report(day: date, include_raw: bool = True) -> dict:
    audit_path = AUDIT_ROOT / f"{day.isoformat()}.jsonl"
    chain_path = RAW_ROOT / f"{day.isoformat()}.jsonl"
    events = load_audit_events(audit_path)
    event_counts = Counter(str(e.get("event_type", "unknown")) for e in events)
    trades = [_trade_dict(t) for t in load_today_trades(day)]
    fills = reconcile_recorded_fills(audit_path) if audit_path.exists() else []
    realized = round(sum(float(t["gross_or_recorded_pnl"]) for t in trades), 2)

    accepted = [e for e in events if e.get("event_type") == "signal_accepted_for_execution"]
    rejected = [e for e in events if e.get("event_type") == "signal_rejected"]
    micro = [e for e in events if e.get("event_type") == "microstructure_check"]
    chain_records = load_option_chain_records(chain_path)
    raw_events = _redact(events) if include_raw else None

    warnings = []
    if not audit_path.exists():
        warnings.append("No audit file exists for this date; trade reasoning cannot be reconstructed.")
    if not chain_path.exists():
        warnings.append("No raw option-chain file exists for this date.")
    if not trades and not fills:
        warnings.append("No closed session-ledger trades or recorded fill events were found; this does not prove no trade occurred.")
    if any(not f.get("pnl_is_realized_in_recorded_events") for f in fills):
        warnings.append("At least one recorded entry is not fully reconciled with recorded exit fills.")
    warnings.append("Session-ledger P&L is recorded application P&L; fees, taxes and broker statements are not independently verified.")

    report = {
        "report_type": "quantnifty_daily_trade_intelligence",
        "schema_version": 1,
        "trading_date": day.isoformat(),
        "generated_from": {
            "audit_file": str(audit_path), "audit_file_exists": audit_path.exists(),
            "option_chain_file": str(chain_path), "option_chain_file_exists": chain_path.exists(),
            "report_is_local_only": True,
        },
        "summary": {
            "closed_session_ledger_trades": len(trades),
            "recorded_entry_fill_positions": len(fills),
            "accepted_execution_candidates": len(accepted),
            "signal_rejection_cycles": len(rejected),
            "microstructure_checks": len(micro),
            "option_chain_snapshots": len(chain_records),
            "recorded_session_ledger_pnl": realized,
            "audit_event_counts": dict(event_counts),
        },
        "trades": trades,
        "recorded_fill_reconciliation": fills,
        "accepted_candidates": [_redact(e) for e in accepted],
        "rejection_decisions": [_redact(e) for e in rejected],
        "microstructure_evidence": [_redact(e) for e in micro],
        "warnings": warnings,
        "raw_audit_events": raw_events,
        "raw_data_manifest": {
            "option_chain_snapshot_count": len(chain_records),
            "option_chain_timestamps": [r.get("timestamp") for r in chain_records],
            "audit_event_count": len(events),
            "audit_event_types": dict(event_counts),
        },
    }
    return report


def write_daily_report(day: date) -> dict:
    report = build_daily_report(day, include_raw=True)
    folder = REPORT_ROOT / day.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "daily_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    analysis = [
        f"# QuantNifty Daily Trade Report — {day.isoformat()}",
        "",
        f"- Closed ledger trades: {report['summary']['closed_session_ledger_trades']}",
        f"- Recorded session P&L: ₹{report['summary']['recorded_session_ledger_pnl']:,.2f}",
        f"- Accepted candidates: {report['summary']['accepted_execution_candidates']}",
        f"- Rejection cycles: {report['summary']['signal_rejection_cycles']}",
        f"- Option-chain snapshots: {report['summary']['option_chain_snapshots']}",
        "",
        "## Trade ledger",
    ]
    if report["trades"]:
        for i, t in enumerate(report["trades"], 1):
            analysis.append(
                f"{i}. {t['symbol']} — entry ₹{t['entry_price']:.2f}, exit ₹{t['exit_price']:.2f}, "
                f"qty {t['quantity']}, P&L ₹{t['gross_or_recorded_pnl']:.2f}; {t['exit_reason']}."
            )
    else:
        analysis.append("No closed trades found in the session ledger.")
    analysis += ["", "## Warnings"] + [f"- {w}" for w in report["warnings"]]
    analysis += ["", "## Evidence", "See daily_report.json for candidate decisions, microstructure checks, fill reconciliation and raw audit events."]
    (folder / "analysis.md").write_text("\n".join(analysis) + "\n", encoding="utf-8")
    return report
