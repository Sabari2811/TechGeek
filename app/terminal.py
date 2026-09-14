from datetime import datetime
from zoneinfo import ZoneInfo
from .config import CONFIG
from .models import Position, TradeSignal


IST = ZoneInfo("Asia/Kolkata")


class Terminal:
    """Single-screen terminal UI. Never appends a market-data log stream."""

    @staticmethod
    def clear():
        print("\033[2J\033[H", end="")

    @staticmethod
    def _check(label: str, passed: bool) -> str:
        return f"  {'✓' if passed else '✗'} {label:<29} {'PASS' if passed else 'WAIT'}"

    @staticmethod
    def _header(spot: float = 0.0):
        Terminal.clear()
        mode = CONFIG.trading_mode.upper()
        now = datetime.now(IST).strftime("%H:%M:%S")
        print("╔══════════════════════════════════════════════════════╗")
        print(f"║              QUANTNIFTY | {mode:<12}             ║")
        print("╠══════════════════════════════════════════════════════╣")
        print(f"║ TIME     {now} IST     NIFTY     {spot:,.2f}" if spot else f"║ TIME     {now} IST     NIFTY     --")
        print("╚══════════════════════════════════════════════════════╝")

    @staticmethod
    def waiting(spot: float = 0.0, reason: str = "Waiting for mathematical edge...", checks=None):
        Terminal._header(spot)
        print("\nSIGNAL")
        print("  🟡 WAIT")
        print(f"  {reason}")
        print("\nCHECKLIST")
        if checks:
            for label, passed in checks.items():
                print(Terminal._check(label, passed))
        else:
            print(Terminal._check("Risk / session", CONFIG.session_active()))
            print(Terminal._check("Mathematical edge", False))
        print("\nNo order. Waiting for the next valid mathematical edge.")

    @staticmethod
    def active(position: Position):
        Terminal._header()
        s = position.signal
        pnl = position.unrealized_pnl
        base = position.entry_price * position.quantity
        pct = (pnl / base * 100) if base else 0.0

        print("\nSIGNAL")
        print(f"  🟢 {s.action} NIFTY {s.strike:g} {s.option_type}")
        print(f"  Entry ₹{position.entry_price:.2f}   SL ₹{s.stop:.2f}   Target ₹{s.target:.2f}")
        print(f"  Qty {position.quantity}   Probability {s.probability:.1%}   Net EV ₹{s.net_expected_value:.2f}   Score {getattr(s, 'score', 0.0):.1f}")

        print("\nLIVE TRADE")
        print(f"  Entry       ₹{position.entry_price:,.2f}")
        print(f"  Current     ₹{position.current_price:,.2f}")
        print(f"  Live P&L    ₹{pnl:,.2f} ({pct:+.2f}%)")
        print(f"  Stop        ₹{s.stop:,.2f}")
        print(f"  Target      ₹{s.target:,.2f}")
        print("  Status      🟢 ACTIVE")

        print("\nCHECKLIST")
        checks = getattr(s, "checks", {})
        if checks:
            for label, passed in checks.items():
                print(Terminal._check(label, passed))
        else:
            print(Terminal._check("Positive net EV", s.net_expected_value > 0))
            print(Terminal._check("Risk controlled", True))

    @staticmethod
    def closed(position: Position):
        # Keep the same single-screen philosophy: show the completed trade briefly,
        # then the next loop replaces it with the waiting screen.
        Terminal._header()
        s = position.signal
        pnl = position.realized_pnl
        print("\nSIGNAL")
        print(f"  CLOSED {s.option_type} {s.strike:g}")
        print("\nLIVE TRADE")
        print(f"  Entry       ₹{position.entry_price:,.2f}")
        print(f"  Exit        ₹{position.exit_price:,.2f}")
        print(f"  P&L         ₹{pnl:,.2f}")
        print(f"  Reason      {position.exit_reason}")
        print("  Status      ✓ CLOSED")
        print("\nCHECKLIST")
        for label, passed in getattr(s, "checks", {}).items():
            print(Terminal._check(label, passed))
