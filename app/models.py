from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

@dataclass
class OptionQuote:
    strike: float
    option_type: str
    security_id: str
    symbol: str
    ltp: float
    bid: float
    ask: float
    volume: float
    oi: float
    previous_oi: float
    iv: float
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    lot_size: int = 1

    @property
    def oi_change(self) -> float:
        return self.oi - self.previous_oi

    @property
    def spread(self) -> float:
        return max(0.0, self.ask - self.bid)

    @property
    def spread_pct(self) -> float:
        return self.spread / self.ltp if self.ltp > 0 else 1.0

@dataclass
class MarketState:
    timestamp: Optional[datetime] = None
    spot: float = 0.0
    futures: float = 0.0
    vix: float = 0.0
    expiry: Optional[str] = None
    options: Dict[str, OptionQuote] = field(default_factory=dict)
    spot_history: list[float] = field(default_factory=list)
    last_tick_epoch_ms: int = 0

    def set_spot(self, price: float, timestamp: datetime) -> None:
        if price > 0:
            self.spot = price
            self.timestamp = timestamp
            self.spot_history.append(price)
            if len(self.spot_history) > 600:
                self.spot_history.pop(0)

    def key(self, strike: float, option_type: str) -> str:
        return f"{strike:.2f}:{option_type.upper()}"

    def get_option(self, strike: float, option_type: str) -> Optional[OptionQuote]:
        return self.options.get(self.key(strike, option_type))

@dataclass
class TradeSignal:
    action: str
    option_type: str
    strike: float
    security_id: str
    symbol: str
    entry: float
    stop: float
    target: float
    quantity: int
    probability: float
    fair_value: float
    expected_value: float
    net_expected_value: float
    reason: str

@dataclass
class Position:
    signal: TradeSignal
    entry_price: float
    quantity: int
    opened_at: datetime
    current_price: float = 0.0
    exit_price: float = 0.0
    exit_reason: str = ""

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.entry_price) * self.quantity

    @property
    def realized_pnl(self) -> float:
        if self.exit_price <= 0:
            return 0.0
        return (self.exit_price - self.entry_price) * self.quantity
