"""Post-market replay of captured QuantNifty option-chain snapshots.

This module intentionally reuses the live mathematical engine. It does not place
orders and it does not call the broker. Its purpose is to explain what blocked
each snapshot and to make historical sessions reproducible.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.models import MarketState, SignalAudit
from app.market import load_chain_into_state
from app.math_engine import QuantEngine
from app.raw_data import load_option_chain_records

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class ReplaySummary:
    snapshots: int = 0
    option_snapshots: int = 0
    signal_snapshots: int = 0
    blocked_by_phase: int = 0
    blocked_by_ev: int = 0
    top_rejections: dict[str, int] | None = None


def replay_file(path: str | Path, min_net_ev: float = 10.0) -> ReplaySummary:
    records = load_option_chain_records(path)
    state = MarketState()
    summary = ReplaySummary(top_rejections={})

    for row in records:
        summary.snapshots += 1
        data = row["data"]
        try:
            timestamp = datetime.fromisoformat(str(row.get("timestamp", "")))
        except (TypeError, ValueError):
            timestamp = None
        load_chain_into_state(state, data, timestamp=timestamp)
        if not state.options:
            continue
        summary.option_snapshots += 1
        audit = SignalAudit()
        signal = QuantEngine.best_signal(state, min_net_ev, audit=audit)
        if signal:
            summary.signal_snapshots += 1
        if audit.phase not in {"EARLY_CONFIRMATION", "BREAKOUT"}:
            summary.blocked_by_phase += 1
        if signal is None and audit.final_candidates == 0:
            summary.blocked_by_ev += 1
        for reason, count in audit.rejected.items():
            summary.top_rejections[reason] = summary.top_rejections.get(reason, 0) + count

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Replay a captured QuantNifty JSONL session")
    parser.add_argument("file", help="Path to .quantnifty/raw/YYYY-MM-DD.jsonl")
    parser.add_argument("--min-net-ev", type=float, default=10.0)
    args = parser.parse_args()
    result = replay_file(args.file, args.min_net_ev)
    print(f"snapshots={result.snapshots}")
    print(f"option_snapshots={result.option_snapshots}")
    print(f"signal_snapshots={result.signal_snapshots}")
    print(f"blocked_by_phase={result.blocked_by_phase}")
    print(f"blocked_by_ev={result.blocked_by_ev}")
    print("top_rejections=" + str(sorted((result.top_rejections or {}).items(),
                                         key=lambda x: x[1], reverse=True)[:10]))
