import os
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()
IST = ZoneInfo("Asia/Kolkata")

@dataclass(frozen=True)
class Config:
    mode: str = os.getenv("TRADING_MODE", "PAPER").upper()
    access_token: str = os.getenv("INDSTOCKS_ACCESS_TOKEN", "")
    base_url: str = os.getenv("INDSTOCKS_BASE_URL", "https://api.indstocks.com")
    nifty_underlying_id: str = os.getenv("NIFTY_UNDERLYING_ID", "40000001")
    risk_capital: float = float(os.getenv("RISK_CAPITAL", "2000000"))
    risk_per_trade: float = float(os.getenv("RISK_PER_TRADE", "0.005"))
    max_daily_loss: float = float(os.getenv("MAX_DAILY_LOSS", "20000"))
    max_trades: int = int(os.getenv("MAX_TRADES", "3"))
    min_net_ev: float = float(os.getenv("MIN_NET_EV", "10"))
    max_spread_pct: float = float(os.getenv("MAX_SPREAD_PCT", "0.04"))
    stale_seconds: float = float(os.getenv("STALE_SECONDS", "3"))
    strike_count: int = int(os.getenv("STRIKE_COUNT", "10"))
    poll_seconds: float = float(os.getenv("POLL_SECONDS", "2"))
    start_time: time = time(9, 15)
    new_entry_cutoff: time = time(15, 15)
    squareoff_time: time = time(15, 30)
    end_time: time = time(15, 35)

    def market_time(self):
        from datetime import datetime
        return datetime.now(IST).time()

    def entries_allowed(self) -> bool:
        t = self.market_time()
        return self.start_time <= t < self.new_entry_cutoff

    def session_active(self) -> bool:
        t = self.market_time()
        return self.start_time <= t <= self.end_time

CONFIG = Config()
