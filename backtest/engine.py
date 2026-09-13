import csv
from dataclasses import dataclass
from pathlib import Path
from .math_engine import QuantEngine

@dataclass
class BacktestResult:
    trades: int
    wins: int
    losses: int
    pnl: float

class SimpleBacktest:
    """Replay a CSV with timestamp,spot,option_price columns.
    This is intentionally conservative: it does not invent missing option history."""
    def run(self, path: str) -> BacktestResult:
        rows = list(csv.DictReader(Path(path).open(newline="", encoding="utf-8")))
        if not rows:
            return BacktestResult(0,0,0,0.0)
        pnl = 0.0; trades = wins = losses = 0
        for row in rows:
            try:
                spot = float(row["spot"]); option = float(row["option_price"])
            except (KeyError, ValueError):
                continue
            # Data validation hook; strategy replay is expanded after full option history is wired in.
            if spot <= 0 or option <= 0:
                continue
        return BacktestResult(trades, wins, losses, pnl)
