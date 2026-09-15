import asyncio
import json
import pytest

import app.market as market_module
from app.market import IndstocksClient, extract_market_depth


def sample_depth():
    return {
        "NFO_47273": {
            "market_depth": {
                "depth": [
                    {"buy": {"quantity": "100", "price": "10.0"},
                     "sell": {"quantity": "120", "price": "10.1"}}
                ]
            }
        }
    }


def test_extract_depth_nfo_key():
    result = extract_market_depth(sample_depth(), "47273")
    assert result.get("market_depth", {}).get("depth")


def test_extract_depth_raw_provider_wrapper():
    raw = {"status": "success", "data": sample_depth()}
    result = extract_market_depth(raw, "47273")
    assert result.get("market_depth", {}).get("depth")


def test_extract_depth_direct_payload():
    direct = sample_depth()["NFO_47273"]
    result = extract_market_depth(direct, "47273")
    assert result == direct


def test_extract_depth_nested_nse_key():
    nested = {"NSE_47273": {"quote": sample_depth()["NFO_47273"]}}
    result = extract_market_depth(nested, "47273")
    assert result.get("market_depth", {}).get("depth")


def test_extract_depth_list_wrapper():
    listed = {"data": [{"securityId": "47273", "result": sample_depth()["NFO_47273"]}]}
    result = extract_market_depth(listed, "47273")
    assert result.get("market_depth", {}).get("depth")


def test_extract_depth_bid_ask_array_fallback():
    raw = {"data": {"NFO_47273": {"bids": [{"quantity": 100, "price": 10}],
                                   "asks": [{"quantity": 120, "price": 10.1}]}}}
    result = extract_market_depth(raw, "47273")
    assert result["market_depth"]["depth"][0]["buy"]["quantity"] == 100
    assert result["market_depth"]["depth"][0]["sell"]["quantity"] == 120


def test_extract_depth_missing_returns_empty():
    assert extract_market_depth({"NFO_1": {}}, "47273") == {}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self, mkt_payload, full_payload):
        self.mkt_payload = mkt_payload
        self.full_payload = full_payload
        self.paths = []

    async def get(self, path, **kwargs):
        self.paths.append(path)
        if path == "/market/quotes/mkt":
            return FakeResponse(self.mkt_payload)
        if path == "/market/quotes/full":
            return FakeResponse(self.full_payload)
        raise AssertionError(path)


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, message):
        self.sent.append(json.loads(message))

    async def recv(self):
        if self.messages:
            return self.messages.pop(0)
        await asyncio.sleep(60)


class FakeWebSocketConnect:
    def __init__(self, websocket):
        self.websocket = websocket

    def __call__(self, *args, **kwargs):
        return self.websocket


def test_websocket_quote_snapshot_extracts_depth(monkeypatch):
    ws = FakeWebSocket([
        json.dumps({
            "mode": "quote",
            "instrument": "47273",
            "data": {
                "bids": [{"quantity": 100, "price": 10.0}],
                "asks": [{"quantity": 120, "price": 10.1}],
            },
        })
    ])
    monkeypatch.setattr(market_module.websockets, "connect", FakeWebSocketConnect(ws))

    async def scenario():
        client = IndstocksClient()
        result = await client.websocket_quote_snapshot(["47273"])
        assert extract_market_depth(result, "47273")
        assert ws.sent == [{
            "action": "subscribe",
            "mode": "quote",
            "instruments": ["NFO:47273"],
        }]
        await client.close()

    asyncio.run(scenario())


def test_market_depth_uses_websocket_after_rest_depth_missing(monkeypatch):
    ws_payload = {
        "mode": "quote",
        "instrument": "47273",
        "data": {
            "bids": [{"quantity": 100, "price": 10.0}],
            "asks": [{"quantity": 120, "price": 10.1}],
        },
    }
    monkeypatch.setattr(
        IndstocksClient,
        "websocket_quote_snapshot",
        lambda self, security_ids: asyncio.sleep(0, result=ws_payload),
    )

    async def scenario():
        mkt = {"status": "success", "data": {"NFO_47273": {"ltp": 10.0}}}
        full = {"status": "success", "data": {"NFO_47273": {"ltp": 10.1}}}
        client = IndstocksClient()
        client.http = FakeHttp(mkt, full)
        result = await client.market_depth(["47273"])
        assert extract_market_depth(result, "47273")
        assert client.http.paths == ["/market/quotes/mkt", "/market/quotes/full"]
        await client.close()

    asyncio.run(scenario())


def test_market_depth_uses_full_quote_fallback_when_mkt_has_no_depth():
    async def scenario():
        mkt = {"status": "success", "data": {"NFO_47273": {"ltp": 10.0}}}
        full = {"status": "success", "data": sample_depth()}
        client = IndstocksClient()
        client.http = FakeHttp(mkt, full)
        result = await client.market_depth(["47273"])
        assert extract_market_depth(result, "47273")
        assert client.http.paths == ["/market/quotes/mkt", "/market/quotes/full"]
        await client.close()
    asyncio.run(scenario())


def test_market_depth_does_not_fallback_when_mkt_has_depth():
    async def scenario():
        mkt = {"status": "success", "data": sample_depth()}
        full = {"status": "success", "data": {}}
        client = IndstocksClient()
        client.http = FakeHttp(mkt, full)
        result = await client.market_depth(["47273"])
        assert extract_market_depth(result, "47273")
        assert client.http.paths == ["/market/quotes/mkt"]
        await client.close()
    asyncio.run(scenario())


def test_market_depth_returns_full_response_even_without_depth(monkeypatch):
    async def no_ws(self, security_ids):
        return {}

    monkeypatch.setattr(IndstocksClient, "websocket_quote_snapshot", no_ws)

    async def scenario():
        mkt = {"status": "success", "data": {"NFO_47273": {"ltp": 10.0}}}
        full = {"status": "success", "data": {"NFO_47273": {"ltp": 10.1}}}
        client = IndstocksClient()
        client.http = FakeHttp(mkt, full)
        result = await client.market_depth(["47273"])
        assert result == full
        assert extract_market_depth(result, "47273") == {}
        await client.close()
    asyncio.run(scenario())


def test_market_depth_rejects_provider_error():
    async def scenario():
        mkt = {"status": "error", "message": "unavailable"}
        full = {"status": "success", "data": sample_depth()}
        client = IndstocksClient()
        client.http = FakeHttp(mkt, full)
        with pytest.raises(RuntimeError):
            await client.market_depth(["47273"])
        await client.close()
    asyncio.run(scenario())
