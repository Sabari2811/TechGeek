import asyncio
import uuid
from datetime import datetime

from .config import CONFIG
from .models import Position, TradeRecord, TradeSignal
from .market import IndstocksClient
from .kill_switch import status as kill_switch_status
from .raw_data import record_audit_event


class ExecutionEngine:
    def __init__(self, client: IndstocksClient):
        self.client = client
        self.position: Position | None = None
        self.closed_trades: list[TradeRecord] = []

    @staticmethod
    def _order_status(order: dict) -> str:
        return str(order.get("status") or order.get("order_status") or "").strip().upper()

    @staticmethod
    def _traded_quantity(order: dict) -> int:
        try:
            value = int(order.get("traded_qty", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            return 0
        return max(0, value)

    async def _find_order(self, order_id: str) -> dict | None:
        # Order IDs are the authoritative correlation key. Matching on a
        # reusable remark/tag can accidentally reconcile a different order.
        orders = await self.client.order_book()
        matches = [o for o in orders if str(o.get("id") or "") == order_id]
        return matches[-1] if matches else None

    async def _live_order(self, txn_type: str, security_id: str, qty: int, price: float, tag: str):
        if qty <= 0:
            raise ValueError("Order quantity must be positive")
        response = await self.client.place_order(txn_type, security_id, qty, price, tag)
        data = response.get("data", {}) if isinstance(response, dict) else {}
        status = str(data.get("order_status") or "").strip().upper()
        accepted = {"SUCCESS", "INITIATED", "PENDING", "PROCESSING", "QUEUED", "PARTIALLY FILLED"}
        if status not in accepted:
            raise RuntimeError(f"Order rejected: {response}")
        order_id = data.get("order_id")
        if not order_id:
            raise RuntimeError("Broker accepted order but returned no order_id")
        order_id = str(order_id)

        terminal = {
            "SUCCESS", "CANCELLED", "FAILED", "ABORTED", "EXPIRED",
            "PARTIALLY FILLED - CANCELLED", "PARTIALLY FILLED - EXPIRED",
        }
        latest = None
        for attempt in range(10):
            latest = await self._find_order(order_id)
            if latest:
                latest_status = self._order_status(latest)
                traded_qty = self._traded_quantity(latest)
                if latest_status in terminal:
                    if traded_qty > 0:
                        return latest
                    raise RuntimeError(f"Order finished without a fill: {latest_status}")
                # SUCCESS is terminal in some provider responses, but only
                # the order-book record is trusted for traded quantity.
            await asyncio.sleep(0.5)

        # Cancel the unfilled remainder, then reconcile again. A cancel request
        # is not itself proof that the order is terminal or that no more fills
        # can arrive.
        latest = await self._find_order(order_id)
        if latest and self._order_status(latest) not in terminal:
            try:
                await self.client.cancel_order(order_id)
            except Exception as exc:
                raise RuntimeError(
                    f"Order state unresolved after reconciliation timeout; cancellation failed "
                    f"(order_id={order_id}): {exc}"
                ) from exc

        for _ in range(4):
            latest = await self._find_order(order_id)
            if latest and self._order_status(latest) in terminal:
                if self._traded_quantity(latest) > 0:
                    return latest
                raise RuntimeError(f"Order finished without a fill: {self._order_status(latest)}")
            await asyncio.sleep(0.25)

        traded_qty = self._traded_quantity(latest or {})
        raise RuntimeError(
            f"Order state unresolved after cancellation; refusing to assume it is closed "
            f"(order_id={order_id}, observed_traded_qty={traded_qty})"
        )

    async def enter(self, signal: TradeSignal, quantity: int) -> Position:
        kill_enabled, kill_reason = kill_switch_status()
        if kill_enabled:
            raise RuntimeError(f"Entry blocked by persistent kill switch: {kill_reason}")
        if self.position is not None:
            raise RuntimeError("Cannot enter: a position is already open")
        if quantity <= 0:
            raise ValueError("Entry quantity must be positive")
        signal.quantity = quantity
        entry, qty = signal.entry, quantity
        if CONFIG.live_enabled():
            tag = f"quantnifty/entry-{uuid.uuid4().hex[:12]}"
            order = await self._live_order("BUY", signal.security_id, quantity, signal.entry, tag)
            traded_qty = self._traded_quantity(order)
            if traded_qty <= 0:
                raise RuntimeError("Entry order accepted but not filled")
            if traded_qty > quantity:
                raise RuntimeError("Broker-reported entry fill exceeds requested quantity")
            entry = float(order.get("traded_price") or signal.entry)
            qty = traded_qty
        signal.quantity = qty
        self.position = Position(
            signal=signal,
            entry_price=entry,
            quantity=qty,
            opened_at=datetime.now(),
            current_price=entry,
        )
        record_audit_event("entry_filled", {
            "symbol": signal.symbol,
            "security_id": signal.security_id,
            "option_type": signal.option_type,
            "strike": signal.strike,
            "entry_price": entry,
            "requested_quantity": quantity,
            "filled_quantity": qty,
            "mode": CONFIG.mode,
        })
        return self.position

    async def exit(self, price: float, reason: str) -> Position | None:
        if not self.position:
            return None
        p = self.position
        requested_qty = p.quantity
        if requested_qty <= 0:
            raise RuntimeError("Cannot exit a position with no remaining quantity")

        if CONFIG.live_enabled():
            tag = f"quantnifty/exit-{uuid.uuid4().hex[:12]}"
            order = await self._live_order("SELL", p.signal.security_id, requested_qty, price, tag)
            traded_qty = self._traded_quantity(order)
            if traded_qty <= 0:
                raise RuntimeError("Exit order accepted but not filled")
            if traded_qty > requested_qty:
                raise RuntimeError("Broker-reported exit fill exceeds remaining position quantity")
            fill_price = float(order.get("traded_price") or price)
        else:
            traded_qty = requested_qty
            fill_price = price

        # Track each confirmed fill separately. If only part of the position
        # exits, keep the remaining quantity open and do not record a closed
        # trade or train the learner on a partial outcome.
        p.exit_filled_quantity += traded_qty
        p.exit_proceeds += fill_price * traded_qty
        p.quantity -= traded_qty
        p.exit_reason = reason
        record_audit_event("exit_fill", {
            "symbol": p.signal.symbol,
            "security_id": p.signal.security_id,
            "reason": reason,
            "fill_price": fill_price,
            "filled_quantity": traded_qty,
            "remaining_quantity": p.quantity,
            "cumulative_exit_quantity": p.exit_filled_quantity,
            "cumulative_exit_proceeds": p.exit_proceeds,
            "mode": CONFIG.mode,
        })
        if p.quantity > 0:
            return None

        p.exit_price = p.exit_proceeds / p.exit_filled_quantity
        closed = p
        self.closed_trades.append(TradeRecord.from_position(closed))
        self.position = None
        return closed
