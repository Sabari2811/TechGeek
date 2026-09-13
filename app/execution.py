import uuid
from datetime import datetime
from .config import CONFIG
from .models import Position, TradeSignal
from .market import IndstocksClient

class ExecutionEngine:
    def __init__(self, client: IndstocksClient):
        self.client = client
        self.position: Position | None = None

    async def _live_order(self, txn_type: str, security_id: str, qty: int, price: float, tag: str):
        response = await self.client.place_order(txn_type, security_id, qty, price, tag)
        status = response.get("data", {}).get("order_status")
        if status not in {"SUCCESS", "INITIATED", "PENDING", "PROCESSING"}:
            raise RuntimeError(f"Order rejected: {response}")
        orders = await self.client.order_book()
        matches = [o for o in orders if o.get("remarks") == tag]
        if not matches:
            raise RuntimeError("Order accepted but could not be reconciled")
        return matches[-1]

    async def enter(self, signal: TradeSignal, quantity: int) -> Position:
        signal.quantity = quantity
        entry, qty = signal.entry, quantity
        if CONFIG.mode == "LIVE":
            tag = f"quantnifty/entry-{uuid.uuid4().hex[:12]}"
            order = await self._live_order("BUY", signal.security_id, quantity, signal.entry, tag)
            traded_qty = int(order.get("traded_qty", 0) or 0)
            if traded_qty <= 0:
                raise RuntimeError("Entry order accepted but not filled; refusing to create a live position")
            entry = float(order.get("traded_price") or signal.entry)
            qty = traded_qty
        self.position = Position(signal=signal, entry_price=entry, quantity=qty,
                                 opened_at=datetime.now(), current_price=entry)
        return self.position

    async def exit(self, price: float, reason: str) -> Position | None:
        if not self.position:
            return None
        p = self.position
        if CONFIG.mode == "LIVE":
            tag = f"quantnifty/exit-{uuid.uuid4().hex[:10]}"
            order = await self._live_order("SELL", p.signal.security_id, p.quantity, price, tag)
            traded_qty = int(order.get("traded_qty", 0) or 0)
            if traded_qty <= 0:
                raise RuntimeError("Exit order accepted but not filled; keeping position state")
            p.exit_price = float(order.get("traded_price") or price)
        else:
            p.exit_price = price
        p.exit_reason = reason
        p.current_price = p.exit_price
        self.position = None
        return p
