from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


@dataclass(frozen=True)
class DepthLevel:
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float


@dataclass
class MicrostructureSnapshot:
    timestamp: datetime
    ltp: float
    best_bid: float
    best_ask: float
    total_bid_qty: float
    total_ask_qty: float
    imbalance: float
    spread_pct: float
    sweep_score: float = 0.0
    absorption_score: float = 0.0
    liquidity_score: float = 0.0
    buy_pressure: float = 0.0
    reason: str = ""


@dataclass
class MicrostructureState:
    previous: Dict[str, MicrostructureSnapshot] = field(default_factory=dict)


class MicrostructureEngine:
    """Market-depth confirmation layer using public five-level snapshots."""

    @staticmethod
    def _num(value) -> float:
        if value is None:
            return 0.0
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def from_depth(cls, instrument: str, payload: dict, state: MicrostructureState) -> MicrostructureSnapshot | None:
        depth = payload.get("market_depth", {}) if isinstance(payload, dict) else {}
        levels = depth.get("depth", []) or []
        if not levels:
            return None

        bids, asks = [], []
        for row in levels[:5]:
            buy = row.get("buy", {}) or {}
            sell = row.get("sell", {}) or {}
            bp, bq = cls._num(buy.get("price")), cls._num(buy.get("quantity"))
            ap, aq = cls._num(sell.get("price")), cls._num(sell.get("quantity"))
            if bp > 0:
                bids.append((bp, bq))
            if ap > 0:
                asks.append((ap, aq))
        if not bids or not asks:
            return None

        best_bid, _ = bids[0]
        best_ask, _ = asks[0]
        total_bid = sum(q for _, q in bids)
        total_ask = sum(q for _, q in asks)
        denom = total_bid + total_ask
        imbalance = (total_bid - total_ask) / denom if denom else 0.0
        mid = (best_bid + best_ask) / 2.0
        spread_pct = (best_ask - best_bid) / mid if mid > 0 else 1.0
        previous = state.previous.get(instrument)
        sweep = 0.0
        absorption = 0.0
        reasons: List[str] = []

        if previous:
            bid_drop = max(0.0, previous.total_bid_qty - total_bid)
            ask_drop = max(0.0, previous.total_ask_qty - total_ask)
            base = max(previous.total_bid_qty + previous.total_ask_qty, 1.0)
            # This is a quote-depletion/repricing proxy, not a claim of seeing every trade.
            if ask_drop / base > 0.20 and best_ask >= previous.best_ask:
                sweep += min(1.0, ask_drop / base * 2.5)
                reasons.append("ask liquidity depleted")
            if bid_drop / base > 0.20 and best_bid <= previous.best_bid:
                sweep -= min(1.0, bid_drop / base * 2.5)
                reasons.append("bid liquidity depleted")

            previous_mid = (previous.best_bid + previous.best_ask) / 2.0
            price_move = (mid - previous_mid) / max(mid, 1e-9)
            if abs(imbalance) > 0.25 and abs(price_move) < 0.0005:
                absorption = min(1.0, abs(imbalance) * 1.8)
                reasons.append("pressure absorbed")
            elif abs(price_move) > 0.001 and abs(imbalance) > 0.20:
                reasons.append("pressure has price follow-through")

        liquidity = max(0.0, 1.0 - min(1.0, spread_pct / 0.01))
        snapshot = MicrostructureSnapshot(
            timestamp=datetime.now(timezone.utc),
            ltp=cls._num(payload.get("live_price")),
            best_bid=best_bid,
            best_ask=best_ask,
            total_bid_qty=total_bid,
            total_ask_qty=total_ask,
            imbalance=imbalance,
            spread_pct=spread_pct,
            sweep_score=sweep,
            absorption_score=absorption,
            liquidity_score=liquidity,
            buy_pressure=max(-1.0, min(1.0, imbalance)),
            reason=", ".join(reasons) if reasons else "stable depth",
        )
        state.previous[instrument] = snapshot
        return snapshot

    @staticmethod
    def confirmation(snapshot: MicrostructureSnapshot | None, min_liquidity: float = 0.35) -> tuple[bool, str]:
        if snapshot is None:
            return False, "microstructure unavailable"
        if snapshot.liquidity_score < min_liquidity:
            return False, "liquidity too thin"
        if snapshot.absorption_score > 0.75:
            return False, "strong absorption / poor follow-through"
        if snapshot.buy_pressure < -0.75:
            return False, "strong offer-side pressure"
        return True, snapshot.reason
