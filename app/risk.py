from dataclasses import dataclass
from datetime import datetime
from .config import CONFIG
from .models import MarketState, TradeSignal

@dataclass
class RiskState:
    trades_today: int = 0
    realized_pnl: float = 0.0
    halted: bool = False
    halt_reason: str = ""

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
