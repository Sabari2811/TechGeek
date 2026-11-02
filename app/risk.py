from dataclasses import dataclass
import math
from datetime import datetime
from .config import CONFIG
from .models import MarketState, TradeSignal

@dataclass
class RiskState:
    trades_today: int = 0
    realized_pnl: float = 0.0
    halted: bool = False
    halt_reason: str = ""


def calculate_stop_target(entry_price: float, spot_price: float, reward_risk: float = 1.8) -> tuple[float, float]:
    """Calculate option stop/target from the executable entry price.

    The stop-distance policy retains the existing formula, but uses entry
    rather than last-traded price so risk sizing and the target use the same
    price basis as the proposed trade.
    """
    values = (entry_price, spot_price, reward_risk)
    if not all(
        isinstance(value, (int, float)) and math.isfinite(value) and value > 0
        for value in values
    ):
        raise ValueError("entry price, spot price, and reward/risk must be positive")
    stop = max(entry_price * 0.75, entry_price - spot_price * 0.001)
    if stop <= 0 or stop >= entry_price:
        raise ValueError("calculated stop must be positive and below entry")
    target = entry_price + (entry_price - stop) * reward_risk
    return stop, target


def cap_quantity_to_lots(raw_quantity: int, lot_size: int, max_lots: int) -> int:
    """Round risk-sized quantity down to a valid lot, capped at max_lots."""
    if any(not isinstance(value, int) or isinstance(value, bool) for value in (raw_quantity, lot_size, max_lots)):
        raise ValueError("quantity, lot size, and lot cap must be integers")
    if raw_quantity < 0 or lot_size <= 0 or max_lots <= 0:
        raise ValueError("quantity must be non-negative; lot size and lot cap must be positive")
    return min(raw_quantity // lot_size, max_lots) * lot_size


class RiskManager:
    def __init__(self):
        self.state = RiskState()

    def check_market(self, market: MarketState) -> tuple[bool, str]:
        if not CONFIG.entries_allowed():
            return False, "outside entry window"
        if market.spot <= 0:
            return False, "invalid spot"
        if len(market.spot_history) >= 10:
            recent = market.spot_history[-1]
            prev = market.spot_history[-10]
            move = abs(recent / prev - 1) if prev else 1
            if move > 0.01:
                return False, "abnormal spot move"
        if self.state.halted:
            return False, self.state.halt_reason
        if self.state.trades_today >= CONFIG.max_trades:
            return False, "maximum trades reached"
        if self.state.realized_pnl <= -CONFIG.max_daily_loss:
            self.state.halted = True
            self.state.halt_reason = "daily loss limit reached"
            return False, self.state.halt_reason
        return True, "ok"

    def size(self, signal: TradeSignal) -> int:
        risk_budget = CONFIG.risk_capital * CONFIG.risk_per_trade
        per_unit = max(signal.entry - signal.stop, 0.01)
        return max(0, int(risk_budget // per_unit))

    def record_trade(self, pnl: float):
        self.state.trades_today += 1
        self.state.realized_pnl += pnl
        if self.state.realized_pnl <= -CONFIG.max_daily_loss:
            self.state.halted = True
            self.state.halt_reason = "daily loss limit reached"
