from datetime import datetime
from .config import CONFIG
from .models import Position, TradeSignal

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
        print("QUANTNIFTY | LIVE TRADE")
        print(f"\nNIFTY: {s.symbol}")
        print(f"OPTION: {s.option_type} {s.strike:g}")
        print(f"\nENTRY: ₹{position.entry_price:.2f}")
        print(f"CURRENT: ₹{position.current_price:.2f}")
        print(f"STOP LOSS: ₹{s.stop:.2f}")
        print(f"TARGET: ₹{s.target:.2f}")
        print(f"QUANTITY: {position.quantity}")
        print(f"LIVE P&L: ₹{pnl:,.2f}")
        print(f"P&L %: {(pnl/(position.entry_price*position.quantity)*100):.2f}%")
        print(f"\nTIME: {datetime.now(CONFIG.__class__.__dict__.get('IST', None)) if False else datetime.now().strftime('%H:%M:%S')}")
        print("\nSTATUS: TRADE ACTIVE")

    @staticmethod
    def closed(position: Position):
        Terminal.clear()
        s = position.signal
        pnl = position.realized_pnl
        print("TRADE CLOSED")
        print(f"\nOPTION: {s.option_type} {s.strike:g}")
        print(f"ENTRY: ₹{position.entry_price:.2f}")
        print(f"EXIT: ₹{position.exit_price:.2f}")
        print(f"QUANTITY: {position.quantity}")
        print(f"NET P&L (before broker costs): ₹{pnl:,.2f}")
        print(f"REASON: {position.exit_reason}")
        print("\nNO TRADE YET\nWaiting for next mathematical edge...")
