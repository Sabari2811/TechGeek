from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from .config import IST
from .storage import DATA_ROOT
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
    processed_outcome_ids: List[str] = field(default_factory=list)


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
            if not isinstance(raw, dict):
                raise ValueError("learning state must be an object")
            state = LearningState(**{k: raw[k] for k in LearningState.__dataclass_fields__ if k in raw})
            merged = dict(DEFAULT_WEIGHTS)
            merged.update(state.weights or {})
            cleaned_weights = {}
            for key, value in merged.items():
                try:
                    number = float(value)
                except (TypeError, ValueError, OverflowError):
                    number = 1.0
                cleaned_weights[str(key)] = max(0.5, min(1.5, number)) if math.isfinite(number) else 1.0
            state.weights = cleaned_weights
            if not isinstance(state.pending, list):
                state.pending = []
            if not isinstance(state.processed_outcome_ids, list):
                state.processed_outcome_ids = []
            known = {str(value) for value in state.processed_outcome_ids if str(value).strip()}
            known.update(
                str(item.get("outcome_id"))
                for item in state.pending
                if isinstance(item, dict) and item.get("outcome_id")
            )
            state.processed_outcome_ids = list(known)[-5000:]
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
            "processed_outcome_ids": self.state.processed_outcome_ids[-5000:],
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

    def record(self, signal, pnl: float, outcome_id: str | None = None) -> bool:
        """Persist a completed outcome once; return False for a duplicate ID."""
        pnl_value = float(pnl)
        if not math.isfinite(pnl_value):
            raise ValueError("learning P&L must be finite")
        identity = str(outcome_id).strip() if outcome_id is not None else ""
        if identity and identity in self.state.processed_outcome_ids:
            return False

        item = {
            "date": datetime.now(IST).date().isoformat(),
            "probability": self._result_probability(signal),
            "pnl": pnl_value,
            "components": dict(getattr(signal, "score_components", {})),
        }
        if identity:
            item["outcome_id"] = identity
            self.state.processed_outcome_ids.append(identity)
            self.state.processed_outcome_ids = self.state.processed_outcome_ids[-5000:]
        self.state.pending.append(item)
        self.state.pending = self.state.pending[-500:]
        self._save()
        return True

    def probability(self, raw_probability: float) -> float:
        """Apply the learned calibration bias, bounded to ±5 percentage points."""
        return max(0.10, min(0.90, raw_probability + self.state.probability_bias))

    def weight(self, name: str) -> float:
        return self.state.weights.get(name, 1.0)

    def learn_if_new_day(self, current_date: str | None = None) -> bool:
        today_text = current_date or datetime.now(IST).date().isoformat()
        try:
            today = date.fromisoformat(today_text)
        except (TypeError, ValueError) as exc:
            raise ValueError("current_date must be an ISO date") from exc

        if not self.state.pending:
            self.state.last_learning_date = today.isoformat()
            self._save()
            return False

        eligible = []
        remaining = []
        for item in self.state.pending:
            if not isinstance(item, dict):
                continue
            try:
                outcome_date = date.fromisoformat(str(item.get("date", "")))
            except ValueError:
                remaining.append(item)
                continue
            if outcome_date < today:
                eligible.append(item)
            else:
                # Never train on same-day or future-dated outcomes.
                remaining.append(item)

        if not eligible:
            return False

        for item in eligible:
            try:
                p = float(item.get("probability", 0.5))
                pnl_value = float(item.get("pnl", 0.0))
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(p) or not math.isfinite(pnl_value):
                continue
            p = max(0.01, min(0.99, p))
            y = 1.0 if pnl_value > 0 else 0.0
            reward = 1.0 if y else -1.0
            self.state.total_outcomes += 1
            self.state.wins += int(y == 1.0)
            self.state.losses += int(y == 0.0)
            self.state.brier_sum += (p - y) ** 2

            error = y - p
            self.state.probability_bias = max(
                -0.05,
                min(0.05, self.state.probability_bias + 0.02 * error),
            )

            components = item.get("components") or {}
            if not isinstance(components, dict):
                components = {}
            valid_components = {}
            for name, value in components.items():
                try:
                    number = float(value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if math.isfinite(number) and number > 0:
                    valid_components[str(name)] = number
            total = sum(valid_components.values()) or 1.0
            for name, value in valid_components.items():
                share = value / total
                delta = 0.015 * reward * share
                old = self.state.weights.get(name, 1.0)
                self.state.weights[name] = max(0.5, min(1.5, old + delta))

        self.state.pending = remaining[-500:]
        self.state.last_learning_date = today.isoformat()
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
