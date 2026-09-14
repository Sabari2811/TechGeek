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
        """Return usable provider depth, falling back to full quotes when needed."""
        codes = [f"NFO_{sid}" for sid in security_ids if sid]
        if not codes:
            return {}
        params = {"scrip-codes": ",".join(codes)}

        r = await self.http.get("/market/quotes/mkt", params=params)
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != "success":
            raise RuntimeError(payload)
        if extract_market_depth(payload, str(security_ids[0])):
            return payload

        # INDstocks full quotes can also contain market_depth. Use it only when
        # the dedicated depth endpoint succeeds but has no usable depth object.
        full = await self.market_quote_fallback(security_ids)
        if extract_market_depth(full, str(security_ids[0])):
            return full
        return payload

    async def market_quote_fallback(self, security_ids: list[str]) -> dict:
        """Try full quote endpoint, which may also expose market_depth."""
        codes = [f"NFO_{sid}" for sid in security_ids if sid]
        if not codes:
            return {}
        r = await self.http.get("/market/quotes/full", params={"scrip-codes": ",".join(codes)})
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != "success":
            raise RuntimeError(payload)
        return payload

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
        payload = {"txn_type":txn_type, "exchange":"NSE", "segment":"DERIVATIVE", "product":"INTRADAY",
                   "order_type":"LIMIT", "limit_price":round(price,2), "validity":"DAY", "security_id":security_id,
                   "qty":qty, "algo_id":"99999", "is_amo":False, "remarks":remarks[:100]}
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


def _extract_market_depth_object(value) -> dict:
    if not isinstance(value, dict):
        return {}
    if isinstance(value.get("market_depth"), dict) and isinstance(value["market_depth"].get("depth"), list):
        return value
    for key in ("data", "result", "quote", "quotes", "instrument", "item"):
        child = value.get(key)
        if isinstance(child, dict):
            found = _extract_market_depth_object(child)
            if found:
                return found
        elif isinstance(child, list):
            for item in child:
                found = _extract_market_depth_object(item)
                if found:
                    return found
    return {}


def extract_market_depth(data: dict, security_id: str) -> dict:
    """Normalize raw INDstocks market-depth payloads while preserving single-security data."""
    if not isinstance(data, dict) or not security_id:
        return {}
    sid = str(security_id)
    keys = [f"NFO_{sid}", f"NFO:{sid}", f"NFO-{sid}", f"NSE_{sid}", f"NSE:{sid}", f"NSE-{sid}", sid]

    for root in (data, data.get("data")):
        if not isinstance(root, dict):
            continue
        for key in keys:
            value = root.get(key)
            if isinstance(value, dict):
                found = _extract_market_depth_object(value)
                if found:
                    return found

    for root in (data, data.get("data")):
        if not isinstance(root, dict):
            continue
        for container_key in ("results", "quotes", "instruments", "items"):
            items = root.get(container_key)
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_sid = str(item.get("security_id") or item.get("securityId") or item.get("scrip_code") or item.get("scripCode") or item.get("instrument_token") or item.get("instrumentToken") or "")
                    if item_sid == sid:
                        found = _extract_market_depth_object(item)
                        if found:
                            return found

    return _extract_market_depth_object(data)


def summarize_market_depth_payload(data: dict, security_id: str) -> str:
    """Return a short safe diagnostic summary without exposing sensitive headers/tokens."""
    sid = str(security_id)
    if not isinstance(data, dict):
        return f"response_type={type(data).__name__}"
    status = data.get("status")
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    keys = list(root.keys())[:8] if isinstance(root, dict) else []
    matched = [k for k in keys if str(k) in {f"NFO_{sid}", f"NFO:{sid}", f"NSE_{sid}", f"NSE:{sid}", sid}]
    has_depth = bool(extract_market_depth(data, sid))
    return f"status={status!r} keys={keys!r} matched={matched!r} depth_found={has_depth}"


def _num(raw: dict, *names: str) -> float:
    for name in names:
        if raw.get(name) is not None:
            try: return float(raw[name])
            except (TypeError, ValueError): pass
    return 0.0


def load_chain_into_state(state: MarketState, data: dict):
    state.spot = _num(data, "underlying_ltp")
    state.expiry = data.get("expiry")
    state.timestamp = datetime.now(IST)
    if state.spot > 0:
        state.spot_history.append(state.spot)
        if len(state.spot_history) > 600: state.spot_history.pop(0)
    for strike_text, legs in data.get("strikes", {}).items():
        strike = float(strike_text)
        for option_type, raw in (("CE", legs.get("ce")), ("PE", legs.get("pe"))):
            if not raw: continue
            q = OptionQuote(
                strike, option_type, str(raw.get("security_id","")), str(raw.get("trading_symbol","")),
                _num(raw,"last_price"), _num(raw,"top_bid_price","bid_price"), _num(raw,"top_ask_price","ask_price"),
                _num(raw,"volume"), _num(raw,"oi"), _num(raw,"previous_oi"), _num(raw,"iv"),
                _num(raw,"delta"), _num(raw,"gamma"), _num(raw,"theta"), _num(raw,"vega"),
                int(_num(raw,"lot_size")) if _num(raw,"lot_size") > 0 else 1)
            state.options[state.key(strike, option_type)] = q
