import asyncio
import json
from datetime import datetime
import httpx
import websockets
from .config import CONFIG, IST
from .models import MarketState, OptionQuote


class IndstocksClient:
    def __init__(self):
        self.base_url = CONFIG.base_url.rstrip("/")
        self.headers = {"Authorization": CONFIG.access_token}
        self.http = httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=8.0)

    async def close(self):
        await self.http.aclose()

    async def option_chain(self, expiry: str) -> dict:
        params = {"exchange":"NSE", "segment":"INDEX", "underlying-scrip":CONFIG.nifty_underlying_id,
                  "expiry":expiry, "strike_count":CONFIG.strike_count}
        r = await self.http.get("/market/option-chain", params=params)
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != "success":
            raise RuntimeError(payload)
        return payload["data"]

    async def market_depth(self, security_ids: list[str]) -> dict:
        """Return verified provider depth without ever fabricating levels.

        Transport order:
          1. documented 5-level /market/quotes/mkt endpoint (with one retry)
          2. documented /market/quotes/full endpoint (with one retry)
          3. WebSocket quote snapshot as an opportunistic provider fallback

        A successful HTTP envelope is not treated as usable depth unless the
        response actually contains depth levels for the requested instrument.
        A transient/provider error on the first endpoint does not prevent the
        independent full-quote fallback from being attempted.
        """
        codes = [f"NFO_{sid}" for sid in security_ids if sid]
        if not codes:
            return {}
        params = {"scrip-codes": ",".join(codes)}

        last_payload = {}
        for attempt in range(2):
            try:
                r = await self.http.get("/market/quotes/mkt", params=params)
                r.raise_for_status()
                payload = r.json()
                last_payload = payload
                if payload.get("status") == "success" and extract_market_depth(payload, str(security_ids[0])):
                    return payload
            except Exception:
                # Retry the documented endpoint once, then continue to the
                # independent fallback rather than failing the whole depth path.
                if attempt == 0:
                    await asyncio.sleep(0.12)

        full = await self.market_quote_fallback(security_ids)
        if extract_market_depth(full, str(security_ids[0])):
            return full

        ws = await self.websocket_quote_snapshot(security_ids)
        if extract_market_depth(ws, str(security_ids[0])):
            return ws

        # Preserve the most informative successful REST payload for diagnostics.
        return full if isinstance(full, dict) else last_payload

    async def market_quote_fallback(self, security_ids: list[str]) -> dict:
        codes = [f"NFO_{sid}" for sid in security_ids if sid]
        if not codes:
            return {}
        params = {"scrip-codes": ",".join(codes)}
        last_payload = {}
        for attempt in range(2):
            try:
                r = await self.http.get("/market/quotes/full", params=params)
                r.raise_for_status()
                payload = r.json()
                last_payload = payload
                if payload.get("status") == "success":
                    return payload
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(0.12)
        return last_payload

    async def websocket_quote_snapshot(self, security_ids: list[str], timeout_seconds: float = 1.5) -> dict:
        """Read a short quote-mode snapshot without weakening the depth gate.

        INDstocks documents quote mode but does not publish its complete quote-mode
        response schema. The same hardened depth normalizer is therefore used against
        the complete message. If the stream carries no depth, this returns the raw
        message and the caller continues to WAIT rather than inventing levels.
        """
        instruments = [f"NFO:{sid}" for sid in security_ids if sid]
        if not instruments:
            return {}
        url = "wss://ws-prices.indstocks.com/api/v1/ws/prices"
        try:
            async with websockets.connect(
                url,
                additional_headers={"Authorization": CONFIG.access_token},
                ping_interval=20,
                ping_timeout=10,
                open_timeout=3,
            ) as ws:
                await ws.send(json.dumps({
                    "action": "subscribe",
                    "mode": "quote",
                    "instruments": instruments,
                }))
                loop = asyncio.get_running_loop()
                deadline = loop.time() + max(0.2, timeout_seconds)
                last_payload = {}
                while loop.time() < deadline:
                    remaining = max(0.05, deadline - loop.time())
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    except asyncio.TimeoutError:
                        break
                    try:
                        payload = json.loads(raw) if isinstance(raw, str) else raw
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if not isinstance(payload, dict):
                        continue
                    last_payload = payload
                    if extract_market_depth(payload, str(security_ids[0])):
                        return payload
                return last_payload
        except Exception:
            return {}

    async def contract_lot_size(self, expiry: str, strike: float, option_type: str) -> int:
        params = {"underlying":"NIFTY", "segment":"DERIVATIVE", "instrument_type":"OPTIDX",
                  "expiry":expiry, "option_type":option_type, "strike_from":strike, "strike_to":strike,
                  "page":1, "page_size":10}
        r = await self.http.get("/market/instruments/search", params=params)
        r.raise_for_status()
        instruments = r.json().get("data", {}).get("instruments", [])
        if not instruments:
            raise RuntimeError("Selected option contract was not found in instruments search")
        return int(instruments[0].get("lot_size") or 0)

    async def place_order(self, txn_type: str, security_id: str, qty: int, price: float, remarks: str):
        payload = {"txn_type":txn_type,"exchange":"NSE","segment":"DERIVATIVE","product":"INTRADAY",
                   "order_type":"LIMIT","limit_price":round(price,2),"validity":"DAY","security_id":security_id,
                   "qty":qty,"algo_id":"99999","is_amo":False,"remarks":remarks[:100]}
        r = await self.http.post("/order", json=payload)
        r.raise_for_status()
        return r.json()

    async def cancel_order(self, order_id: str):
        r = await self.http.post("/order/cancel", json={"order_id":order_id,"segment":"DERIVATIVE"})
        r.raise_for_status()
        return r.json()

    async def order_book(self):
        r = await self.http.get("/order-book")
        r.raise_for_status()
        return r.json().get("data", [])

    async def stream(self, instruments: list[str]):
        url = "wss://ws-prices.indstocks.com/api/v1/ws/prices"
        async with websockets.connect(url, additional_headers={"Authorization":CONFIG.access_token}, ping_interval=20, ping_timeout=10) as ws:
            await ws.send(json.dumps({"action":"subscribe","mode":"quote","instruments":instruments}))
            async for raw in ws:
                yield json.loads(raw)


def _as_levels(value) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("depth", "levels", "items", "rows", "data"):
            child = value.get(key)
            if isinstance(child, list):
                return [item for item in child if isinstance(item, dict)]
    return []


def _pair_bid_ask_levels(buys, sells) -> dict:
    buys = _as_levels(buys)
    sells = _as_levels(sells)
    if not buys or not sells:
        return {}
    depth = []
    for i in range(min(5, len(buys), len(sells))):
        if isinstance(buys[i], dict) and isinstance(sells[i], dict):
            depth.append({"buy": buys[i], "sell": sells[i]})
    return {"market_depth": {"depth": depth}} if depth else {}


def _extract_market_depth_object(value, _seen=None) -> dict:
    """Find documented/common depth shapes without inventing missing levels."""
    if not isinstance(value, dict):
        return {}
    if _seen is None:
        _seen = set()
    marker = id(value)
    if marker in _seen:
        return {}
    _seen.add(marker)

    # Some INDstocks responses wrap the documented depth object one level
    # deeper, e.g. market_depth -> NFO_<security_id> -> depth. Check for a
    # direct depth/levels list before descending further so provider wrappers
    # are normalized without fabricating or weakening the 5-level gate.
    direct_levels = _as_levels(value.get("depth")) or _as_levels(value.get("levels"))
    if direct_levels:
        return {"market_depth": {"depth": direct_levels[:5]}}

    md = value.get("market_depth")
    if isinstance(md, dict):
        levels = _as_levels(md.get("depth")) or _as_levels(md.get("levels"))
        if levels:
            # INDstocks may expose the five levels as raw rows rather than
            # already-normalized buy/sell objects. Preserve them verbatim; the
            # microstructure layer will normalize the row fields.
            return {"market_depth": {"depth": levels[:5]}}
        paired = _pair_bid_ask_levels(md.get("buy") or md.get("bids") or md.get("bid"),
                                      md.get("sell") or md.get("asks") or md.get("ask"))
        if paired:
            return paired
        aggregate = md.get("aggregate")
        if isinstance(aggregate, dict):
            bid = aggregate.get("buy") or aggregate.get("bid") or aggregate.get("bids")
            ask = aggregate.get("sell") or aggregate.get("ask") or aggregate.get("asks")
            paired = _pair_bid_ask_levels(bid, ask)
            if paired:
                return paired

    paired = _pair_bid_ask_levels(value.get("buy") or value.get("bids") or value.get("bid"),
                                  value.get("sell") or value.get("asks") or value.get("ask"))
    if paired:
        return paired

    for child in value.values():
        if isinstance(child, dict):
            found = _extract_market_depth_object(child, _seen)
            if found:
                return found
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    found = _extract_market_depth_object(item, _seen)
                    if found:
                        return found
    return {}


def extract_market_depth(data: dict, security_id: str) -> dict:
    """Normalize INDstocks depth wrappers without inventing depth."""
    if not isinstance(data, dict) or not security_id:
        return {}
    sid = str(security_id)
    keys = [f"NFO_{sid}", f"NFO:{sid}", f"NFO-{sid}", f"NSE_{sid}", f"NSE:{sid}", f"NSE-{sid}", sid]
    roots = [data]
    if isinstance(data.get("data"), (dict, list)):
        roots.append(data["data"])

    for root in roots:
        if isinstance(root, dict):
            for key in keys:
                value = root.get(key)
                if isinstance(value, dict):
                    found = _extract_market_depth_object(value)
                    if found:
                        return found

    for root in roots:
        items = root if isinstance(root, list) else None
        if isinstance(root, dict):
            for container_key in ("results", "quotes", "instruments", "items", "data"):
                candidate = root.get(container_key)
                if isinstance(candidate, list):
                    items = candidate
                    break
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_sid = str(item.get("security_id") or item.get("securityId") or
                               item.get("scrip_code") or item.get("scripCode") or
                               item.get("instrument_token") or item.get("instrumentToken") or
                               item.get("token") or "")
                if item_sid == sid:
                    found = _extract_market_depth_object(item)
                    if found:
                        return found

    return _extract_market_depth_object(data)


def _depth_shape(value, path="root", out=None, level=0) -> list[str]:
    """Return a bounded, value-free description of a provider payload shape."""
    if out is None:
        out = []
    if level > 4 or len(out) >= 40:
        return out
    if isinstance(value, dict):
        for key, child in list(value.items())[:20]:
            child_path = f"{path}.{key}"
            if isinstance(child, dict):
                out.append(f"{child_path}=object")
                _depth_shape(child, child_path, out, level + 1)
            elif isinstance(child, list):
                out.append(f"{child_path}=list[{len(child)}]")
                for i, item in enumerate(child[:5]):
                    if isinstance(item, dict):
                        item_path = f"{child_path}[{i}]"
                        out.append(f"{item_path}=object")
                        _depth_shape(item, item_path, out, level + 1)
            else:
                out.append(f"{child_path}={type(child).__name__}")
    elif isinstance(value, list):
        out.append(f"{path}=list[{len(value)}]")
    return out


def summarize_market_depth_payload(data: dict, security_id: str) -> str:
    sid = str(security_id)
    if not isinstance(data, dict):
        return f"response_type={type(data).__name__}"

    status = data.get("status")
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    keys = list(root.keys())[:8] if isinstance(root, dict) else []
    matched = [k for k in keys if str(k) in {
        f"NFO_{sid}", f"NFO:{sid}", f"NSE_{sid}", f"NSE:{sid}", sid
    }]

    depth = extract_market_depth(data, sid)
    levels = depth.get("market_depth", {}).get("depth", []) if depth else []
    level_count = len(levels) if isinstance(levels, list) else 0
    shape = _depth_shape(root)
    # Shape logging is deliberately value-free: no prices, quantities, token,
    # or complete provider payload is written to the terminal.
    shape_text = ",".join(shape[:20])
    return (
        f"status={status!r} keys={keys!r} matched={matched!r} "
        f"depth_found={bool(depth)} depth_levels={level_count} shape=[{shape_text}]"
    )


def _num(raw: dict, *names: str) -> float:
    for name in names:
        if raw.get(name) is not None:
            try: return float(raw[name])
            except (TypeError, ValueError): pass
    return 0.0


def load_chain_into_state(state: MarketState, data: dict, timestamp: datetime | None = None):
    spot = _num(data, "underlying_ltp")
    state.expiry = data.get("expiry")
    timestamp = timestamp or datetime.now(IST)
    state.set_spot(spot, timestamp)
    for strike_text, legs in data.get("strikes", {}).items():
        strike = float(strike_text)
        for option_type, raw in (("CE", legs.get("ce")), ("PE", legs.get("pe"))):
            if not raw: continue
            q = OptionQuote(
                strike, option_type, str(raw.get("security_id","")), str(raw.get("trading_symbol","")),
                _num(raw,"last_price"), _num(raw,"top_bid_price","bid_price"), _num(raw,"top_ask_price","ask_price"),
                _num(raw,"volume"), _num(raw,"oi"), _num(raw,"previous_oi"), _num(raw,"iv"),
                _num(raw.get("greeks", {}) if isinstance(raw.get("greeks"), dict) else raw,"delta"),
                _num(raw.get("greeks", {}) if isinstance(raw.get("greeks"), dict) else raw,"gamma"),
                _num(raw.get("greeks", {}) if isinstance(raw.get("greeks"), dict) else raw,"theta"),
                _num(raw.get("greeks", {}) if isinstance(raw.get("greeks"), dict) else raw,"vega"),
                int(_num(raw,"lot_size")) if _num(raw,"lot_size") > 0 else 1)
            state.options[state.key(strike, option_type)] = q
