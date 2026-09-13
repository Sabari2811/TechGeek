import uuid
from datetime import datetime
from .config import CONFIG
from .models import Position, TradeSignal
from .market import IndstocksClient

class ExecutionEngine:
    def __init__(self, client: IndstocksClient):
        self.client = client
        self.position: Position | None = None

    async def enter(self, signal: TradeSignal, quantity: int) -> Position:
        signal.quantity = quantity
        if CONFIG.mode == "LIVE":
            tag = f"quantnifty/{uuid.uuid4().hex[:12]}"
            response = await self.client.place_order(signal.security_id, quantity, signal.entry, tag)
            status = response.get("data", {}).get("order_status")
            if status not in {"SUCCESS", "INITIATED", "PENDING", "PROCESSING"}:
                raise RuntimeError(f"Order rejected: {response}")
            # The broker fill must be reconciled before treating the position as live.
            orders = await self.client.order_book()
            matches = [o for o in orders if o.get("remarks") == tag]
            if not matches:
                raise RuntimeError("Order accepted but could not be reconciled")
            order = matches[-1]
            if float(order.get("traded_qty", 0) or 0) <= 0:
                raise RuntimeError("Order not filled yet; position remains pending")
            entry = float(order.get("traded_price") or signal.entry)
            qty = int(order.get("traded_qty") or quantity)
        else:
            entry, qty = signal.entry, quantity
        self.position = Position(signal=signal, entry_price=entry, quantity=qty, opened_at=datetime.now(), current_price=entry)
        return self.position

    async def exit(self, price: float, reason: str) -> Position | None:
        if not self.position:
            return None
        p = self.position
        if CONFIG.mode == "LIVE":
            tag = f"quantnifty/exit-{uuid.uuid4().hex[:10]}"
            response = await self.client.place_order(p.signal.security_id, p.quantity, price, tag)
            if response.get("status") != "success":
                raise RuntimeError(f"Exit rejected: {response}")
        p.exit_price = price
        p.exit_reason = reason
        p.current_price = price
        self.position = None
        return p
