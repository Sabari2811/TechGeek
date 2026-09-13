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

    async def place_order(self, txn_type: str, security_id: str, qty: int, price: float, remarks: str):
        payload = {"txn_type":txn_type, "exchange":"NSE", "segment":"DERIVATIVE", "product":"INTRADAY",
                   "order_type":"LIMIT", "limit_price":round(price,2), "validity":"DAY", "security_id":security_id,
                   "qty":qty, "algo_id":"99999", "is_amo":False, "remarks":remarks[:100]}
        r = await self.http.post("/order", json=payload)
        r.raise_for_status()
        return r.json()

    async def order_book(self):
        r = await self.http.get("/order-book")
        r.raise_for_status()
        return r.json().get("data", [])

    async def stream(self, instruments: list[str]):
        url = "wss://ws-prices.indstocks.com/api/v1/ws/prices"
        async with websockets.connect(url, additional_headers={"Authorization": CONFIG.access_token}, ping_interval=20, ping_timeout=10) as ws:
            await ws.send(json.dumps({"action":"subscribe","mode":"quote","instruments":instruments}))
            async for raw in ws:
                yield json.loads(raw)

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
                _num(raw,"delta"), _num(raw,"gamma"), _num(raw,"theta"), _num(raw,"vega"))
            state.options[state.key(strike, option_type)] = q
