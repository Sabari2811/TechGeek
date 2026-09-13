from datetime import datetime
from .models import Position

class Terminal:
    @staticmethod
    def clear():
        print("\033[2J\033[H", end="")

    @staticmethod
    def waiting(spot: float = 0.0, reason: str = "Waiting for mathematical edge..."):
        Terminal.clear()
        print("QUANTNIFTY | LIVE")
        print(f"\nNIFTY: {spot:,.2f}" if spot else "\nNIFTY: --")
        print(f"\nNO TRADE YET\n{reason}")

    @staticmethod
    def active(position: Position):
        Terminal.clear()
        s = position.signal
        pnl = position.unrealized_pnl
        base = position.entry_price * position.quantity
        pct = (pnl / base * 100) if base else 0.0
        print("QUANTNIFTY | LIVE TRADE")
        print(f"\nOPTION: {s.symbol}")
        print(f"STRIKE: {s.strike:g} {s.option_type}")
        print(f"\nENTRY: ₹{position.entry_price:.2f}")
        print(f"CURRENT: ₹{position.current_price:.2f}")
        print(f"STOP LOSS: ₹{s.stop:.2f}")
        print(f"TARGET: ₹{s.target:.2f}")
        print(f"QUANTITY: {position.quantity}")
        print(f"LIVE P&L: ₹{pnl:,.2f}")
        print(f"P&L %: {pct:.2f}%")
        print(f"TIME: {datetime.now().strftime('%H:%M:%S')}")
        print("\nSTATUS: TRADE ACTIVE")

    @staticmethod
    def closed(position: Position):
        Terminal.clear()
        s = position.signal
        pnl = position.realized_pnl
        print("TRADE CLOSED")
        print(f"\nOPTION: {s.symbol}")
        print(f"STRIKE: {s.strike:g} {s.option_type}")
        print(f"ENTRY: ₹{position.entry_price:.2f}")
        print(f"EXIT: ₹{position.exit_price:.2f}")
        print(f"QUANTITY: {position.quantity}")
        print(f"P&L (before broker costs): ₹{pnl:,.2f}")
        print(f"REASON: {position.exit_reason}")
        print("\nNO TRADE YET\nWaiting for next mathematical edge...")
