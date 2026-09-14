from datetime import datetime
from zoneinfo import ZoneInfo
from .config import CONFIG
from .models import Position


IST = ZoneInfo("Asia/Kolkata")
RESET = "\033[0m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"


class Terminal:
    """Single-screen terminal UI with ANSI color-coded status states."""

    @staticmethod
    def clear():
        print("\033[2J\033[H", end="")

    @staticmethod
    def _paint(text: str, color: str) -> str:
        return f"{color}{text}{RESET}"

    @staticmethod
    def _check(label: str, passed: bool) -> str:
        if passed:
            return f"  {Terminal._paint('✓', GREEN)} {label:<29} {Terminal._paint('PASS', GREEN)}"
        return f"  {Terminal._paint('✗', RED)} {label:<29} {Terminal._paint('WAIT', RED)}"

    @staticmethod
    def _header(spot: float = 0.0):
        Terminal.clear()
        mode = CONFIG.mode.upper()
        now = datetime.now(IST).strftime("%H:%M:%S")
        print("╔══════════════════════════════════════════════════════╗")
        print(f"║              {Terminal._paint(f'QUANTNIFTY | {mode:<12}', BOLD + CYAN)}             ║")
        print("╠══════════════════════════════════════════════════════╣")
        if spot:
            print(f"║ TIME     {now} IST     NIFTY     {spot:,.2f}          ║")
        else:
            print(f"║ TIME     {now} IST     NIFTY     --               ║")
        print("╚══════════════════════════════════════════════════════╝")

    @staticmethod
    def waiting(spot: float = 0.0, reason: str = "Waiting for mathematical edge...", checks=None):
        Terminal._header(spot)
        print("\nSIGNAL")
        print(f"  {Terminal._paint('●', YELLOW)} {Terminal._paint('WAIT', YELLOW)}")
        print(f"  {reason}")
        print("\nCHECKLIST")
        if checks:
            for label, passed in checks.items():
                print(Terminal._check(label, passed))
        else:
            print(Terminal._check("Session / risk", CONFIG.session_active()))
            print(Terminal._check("Mathematical edge", False))
        print("\nNo order. Waiting for the next mathematical edge.")

    @staticmethod
    def active(position: Position, spot: float = 0.0):
        Terminal._header(spot)
        s = position.signal
        pnl = position.unrealized_pnl
        base = position.entry_price * position.quantity
        pct = (pnl / base * 100) if base else 0.0

        print("\nSIGNAL")
        print(f"  {Terminal._paint('●', GREEN)} {Terminal._paint(f'{s.action} NIFTY {s.strike:g} {s.option_type}', GREEN)}")
        print(f"  Entry ₹{position.entry_price:.2f}   SL ₹{s.stop:.2f}   Target ₹{s.target:.2f}")
        print(f"  Qty {position.quantity}   Probability {s.probability:.1%}   Net EV ₹{s.net_expected_value:.2f}   Score {getattr(s, 'score', 0.0):.1f}")

        print("\nLIVE TRADE")
        print(f"  Entry       ₹{position.entry_price:,.2f}")
        print(f"  Current     ₹{position.current_price:,.2f}")
        pnl_color = GREEN if pnl >= 0 else RED
        print(f"  Live P&L    {Terminal._paint(f'₹{pnl:,.2f} ({pct:+.2f}%)', pnl_color)}")
        print(f"  Stop        ₹{s.stop:,.2f}")
        print(f"  Target      ₹{s.target:,.2f}")
        print(f"  Status      {Terminal._paint('● ACTIVE', GREEN)}")

        print("\nCHECKLIST")
        for label, passed in getattr(s, "checks", {}).items():
            print(Terminal._check(label, passed))

    @staticmethod
    def closed(position: Position, spot: float = 0.0):
        Terminal._header(spot)
        s = position.signal
        pnl = position.realized_pnl
        pnl_color = GREEN if pnl >= 0 else RED
        print("\nSIGNAL")
        print(f"  CLOSED {s.option_type} {s.strike:g}")
        print("\nLIVE TRADE")
        print(f"  Entry       ₹{position.entry_price:,.2f}")
        print(f"  Exit        ₹{position.exit_price:,.2f}")
        print(f"  P&L         {Terminal._paint(f'₹{pnl:,.2f}', pnl_color)}")
        print(f"  Reason      {position.exit_reason}")
        print(f"  Status      {Terminal._paint('✓ CLOSED', GREEN if pnl >= 0 else RED)}")
        print("\nCHECKLIST")
        for label, passed in getattr(s, "checks", {}).items():
            print(Terminal._check(label, passed))
