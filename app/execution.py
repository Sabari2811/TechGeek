import asyncio
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
        if status not in {"SUCCESS", "INITIATED", "PENDING", "PROCESSING", "QUEUED", "PARTIALLY FILLED"}:
            raise RuntimeError(f"Order rejected: {response}")
        order_id = response.get("data", {}).get("order_id")
        if not order_id:
            raise RuntimeError("Broker accepted order but returned no order_id")

        # Never assume an accepted order is filled. Reconcile repeatedly so a delayed
        # exchange/broker fill cannot leave the strategy with false position state.
        terminal = {"SUCCESS", "CANCELLED", "FAILED", "ABORTED", "EXPIRED",
                    "PARTIALLY FILLED - CANCELLED", "PARTIALLY FILLED - EXPIRED"}
        latest = None
        for _ in range(10):
            orders = await self.client.order_book()
            matches = [o for o in orders if o.get("id") == order_id or o.get("remarks") == tag]
            if matches:
                latest = matches[-1]
                latest_status = str(latest.get("status") or latest.get("order_status") or "").upper()
                traded_qty = int(latest.get("traded_qty", 0) or 0)
                if traded_qty > 0 and (latest_status == "SUCCESS" or latest_status.startswith("PARTIALLY FILLED")):
                    return latest
                if latest_status in terminal and traded_qty <= 0:
                    raise RuntimeError(f"Order finished without a fill: {latest_status}")
            await asyncio.sleep(0.5)

        # A limit order that is still working is not a live position. Cancel the
        # remaining quantity rather than allowing an old signal to fill later.
        if latest:
            current_status = str(latest.get("status") or "").upper()
            if current_status not in terminal:
                try:
                    await self.client.cancel_order(str(latest.get("id") or order_id))
                except Exception as exc:
                    raise RuntimeError(f"Order remained pending and cancellation failed: {exc}") from exc
            traded_qty = int(latest.get("traded_qty", 0) or 0)
            if traded_qty > 0:
                return latest
        raise RuntimeError("Order not filled within reconciliation window; remaining quantity cancelled")

    async def enter(self, signal: TradeSignal, quantity: int) -> Position:
        signal.quantity = quantity
        entry, qty = signal.entry, quantity
        if CONFIG.live_enabled():
            tag = f"quantnifty/entry-{uuid.uuid4().hex[:12]}"
            order = await self._live_order("BUY", signal.security_id, quantity, signal.entry, tag)
            traded_qty = int(order.get("traded_qty", 0) or 0)
            if traded_qty <= 0:
                raise RuntimeError("Entry order accepted but not filled")
            entry = float(order.get("traded_price") or signal.entry)
            qty = traded_qty
        self.position = Position(signal=signal, entry_price=entry, quantity=qty,
                                 opened_at=datetime.now(), current_price=entry)
        return self.position

    async def exit(self, price: float, reason: str) -> Position | None:
        if not self.position:
            return None
        p = self.position
        if CONFIG.live_enabled():
            tag = f"quantnifty/exit-{uuid.uuid4().hex[:12]}"
            order = await self._live_order("SELL", p.signal.security_id, p.quantity, price, tag)
            traded_qty = int(order.get("traded_qty", 0) or 0)
            if traded_qty <= 0:
                raise RuntimeError("Exit order accepted but not filled")
            p.exit_price = float(order.get("traded_price") or price)
            p.quantity = traded_qty
        else:
            p.exit_price = price
        p.exit_reason = reason
        self.position = None
        return p
