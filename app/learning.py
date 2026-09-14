from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List


DEFAULT_WEIGHTS = {
    "valuation": 1.0,
    "probability": 1.0,
    "volatility": 1.0,
    "participation": 1.0,
    "volume": 1.0,
    "greeks": 1.0,
}


@dataclass
class LearningState:
    version: int = 1
    total_outcomes: int = 0
    wins: int = 0
    losses: int = 0
    probability_bias: float = 0.0
    brier_sum: float = 0.0
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    pending: List[dict] = field(default_factory=list)
    last_learning_date: str = ""


class IncrementalLearner:
    """Small, persistent, bounded online learner.

    Trades are recorded immediately. Model parameters are updated once per
    completed trading day. Updates are deliberately capped so a small sample
    cannot rewrite the strategy.
    """

    def __init__(self, path: str = ".quantnifty/learning_state.json"):
        self.path = Path(path)
        self.state = self._load()

    def _load(self) -> LearningState:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            state = LearningState(**{k: raw[k] for k in LearningState.__dataclass_fields__ if k in raw})
            merged = dict(DEFAULT_WEIGHTS)
            merged.update(state.weights or {})
            state.weights = {k: float(max(0.5, min(1.5, v))) for k, v in merged.items()}
            return state
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return LearningState()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.state.version,
            "total_outcomes": self.state.total_outcomes,
            "wins": self.state.wins,
            "losses": self.state.losses,
            "probability_bias": self.state.probability_bias,
            "brier_sum": self.state.brier_sum,
            "weights": self.state.weights,
            "pending": self.state.pending[-500:],
            "last_learning_date": self.state.last_learning_date,
        }
        fd, tmp = tempfile.mkstemp(prefix="learning_", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    @staticmethod
    def _result_probability(signal) -> float:
        return max(0.01, min(0.99, float(signal.probability)))

    def record(self, signal, pnl: float) -> None:
        outcome = 1.0 if pnl > 0 else 0.0
        self.state.pending.append({
            "date": datetime.now().date().isoformat(),
            "probability": self._result_probability(signal),
            "pnl": float(pnl),
            "components": dict(getattr(signal, "score_components", {})),
        })
        self._save()

    def probability(self, raw_probability: float) -> float:
        """Apply the learned calibration bias, bounded to ±5 percentage points."""
        return max(0.10, min(0.90, raw_probability + self.state.probability_bias))

    def weight(self, name: str) -> float:
        return self.state.weights.get(name, 1.0)

    def learn_if_new_day(self, current_date: str | None = None) -> bool:
        today = current_date or datetime.now().date().isoformat()
        if not self.state.pending:
            self.state.last_learning_date = today
            self._save()
            return False

        dates = {item.get("date") for item in self.state.pending}
        eligible = [item for item in self.state.pending if item.get("date") != today]
        if not eligible:
            return False

        reward_sum = 0.0
        for item in eligible:
            p = max(0.01, min(0.99, float(item.get("probability", 0.5))))
            y = 1.0 if float(item.get("pnl", 0.0)) > 0 else 0.0
            reward = 1.0 if y else -1.0
            reward_sum += reward
            self.state.total_outcomes += 1
            self.state.wins += int(y == 1.0)
            self.state.losses += int(y == 0.0)
            self.state.brier_sum += (p - y) ** 2

            error = y - p
            self.state.probability_bias = max(-0.05, min(0.05, self.state.probability_bias + 0.02 * error))

            components = item.get("components") or {}
            total = sum(max(0.0, float(v)) for v in components.values()) or 1.0
            for name, value in components.items():
                share = max(0.0, float(value)) / total
                delta = 0.015 * reward * share
                old = self.state.weights.get(name, 1.0)
                self.state.weights[name] = max(0.5, min(1.5, old + delta))

        self.state.pending = [item for item in self.state.pending if item.get("date") == today]
        self.state.last_learning_date = today
        self._save()
        return True

    def summary(self) -> dict:
        total = self.state.total_outcomes
        return {
            "outcomes": total,
            "wins": self.state.wins,
            "losses": self.state.losses,
            "win_rate": self.state.wins / total if total else 0.0,
            "brier_score": self.state.brier_sum / total if total else 0.0,
            "probability_bias": self.state.probability_bias,
            "weights": dict(self.state.weights),
            "pending": len(self.state.pending),
        }
