import asyncio
from types import SimpleNamespace

from app.market import IndstocksClient, _extract_live_quote


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def get(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return FakeResponse(self.payload)

    async def aclose(self):
        return None


def test_live_quote_rejects_non_finite_and_non_positive_prices():
    for value in (0, -1, "nan", "inf", "not-a-number"):
        payload = {"status": "success", "data": {"NFO_42": {"live_price": value}}}
        assert _extract_live_quote(payload, "42") == {}


def test_live_quote_rejects_crossed_or_locked_bid_ask():
    crossed = {"status": "success", "data": {"NFO_42": {
        "live_price": 100, "top_bid_price": 100.1, "top_ask_price": 100.1
    }}}
    assert _extract_live_quote(crossed, "42") == {}


def test_live_quote_accepts_sane_prices():
    payload = {"status": "success", "data": {"NFO_42": {
        "live_price": "100", "top_bid_price": "99.9", "top_ask_price": "100.1"
    }}}
    assert _extract_live_quote(payload, "42") == {
        "ltp": 100.0, "bid": 99.9, "ask": 100.1
    }


def test_contract_lot_size_requires_exact_identity_and_unique_match():
    payload = {"data": {"instruments": [
        {"expiry": "2026-10-29", "strike": 25000, "option_type": "CE", "lot_size": 65, "security_id": "111"},
        {"expiry": "2026-11-05", "strike": 25000, "option_type": "CE", "lot_size": 65, "security_id": "222"},
    ]}}

    async def scenario():
        client = IndstocksClient()
        client.http = FakeHttp(payload)
        assert await client.contract_lot_size("2026-10-29", 25000, "CE") == 65
        await client.close()

    asyncio.run(scenario())


def test_contract_lot_size_rejects_missing_identity_fields():
    payload = {"data": {"instruments": [{"lot_size": 65, "security_id": "111"}]}}

    async def scenario():
        client = IndstocksClient()
        client.http = FakeHttp(payload)
        try:
            await client.contract_lot_size("2026-10-29", 25000, "CE")
        except RuntimeError as exc:
            assert "uniquely verify exact option contract" in str(exc)
        else:
            raise AssertionError("incomplete contract identity must be rejected")
        await client.close()

    asyncio.run(scenario())


def test_contract_lot_size_rejects_ambiguous_matches():
    row = {"expiry": "2026-10-29", "strike": 25000, "option_type": "CE", "lot_size": 65}
    payload = {"data": {"instruments": [row, dict(row)]}}

    async def scenario():
        client = IndstocksClient()
        client.http = FakeHttp(payload)
        try:
            await client.contract_lot_size("2026-10-29", 25000, "CE")
        except RuntimeError as exc:
            assert "matches=2" in str(exc)
        else:
            raise AssertionError("ambiguous contract identity must be rejected")
        await client.close()

    asyncio.run(scenario())


def test_intraday_derivative_positions_uses_documented_read_only_endpoint():
    payload = {"status": "success", "data": [
        {"security_id": "123", "net_qty": -65, "segment": "DERIVATIVE", "product": "INTRADAY"}
    ]}

    async def scenario():
        client = IndstocksClient()
        client.http = FakeHttp(payload)
        positions = await client.intraday_derivative_positions()
        assert positions[0]["net_qty"] == -65
        assert client.http.calls == [(
            "/portfolio/positions",
            {"params": {"segment": "derivative", "product": "intraday"}},
        )]
        await client.close()

    asyncio.run(scenario())


def test_intraday_derivative_positions_rejects_bad_schema():
    payload = {"status": "success", "data": [{"security_id": "123"}]}

    async def scenario():
        client = IndstocksClient()
        client.http = FakeHttp(payload)
        try:
            await client.intraday_derivative_positions()
        except RuntimeError as exc:
            assert "security_id/net_qty" in str(exc)
        else:
            raise AssertionError("positions missing net_qty must be rejected")
        await client.close()

    asyncio.run(scenario())


def test_live_quote_records_response_latency_and_freshness_basis(monkeypatch):
    import app.market as market_module
    monkeypatch.setattr(
        market_module,
        "CONFIG",
        SimpleNamespace(base_url="https://example.invalid", access_token="unused", stale_seconds=2.0),
    )
    payload = {"status": "success", "data": {"NFO_42": {
        "live_price": 100, "top_bid_price": 99.9, "top_ask_price": 100.1
    }}}

    async def scenario():
        client = IndstocksClient()
        client.http = FakeHttp(payload)
        quote = await client.live_quote("42")
        assert quote["response_latency_seconds"] >= 0
        assert quote["freshness_basis"] == "request_round_trip_time_only"
        assert quote["source"] == "full_quote"
        await client.close()

    asyncio.run(scenario())


def test_live_quote_rejects_response_exceeding_stale_threshold(monkeypatch):
    import app.market as market_module
    monkeypatch.setattr(
        market_module,
        "CONFIG",
        SimpleNamespace(base_url="https://example.invalid", access_token="unused", stale_seconds=0.001),
    )
    payload = {"status": "success", "data": {"NFO_42": {
        "live_price": 100, "top_bid_price": 99.9, "top_ask_price": 100.1
    }}}

    class SlowHttp(FakeHttp):
        async def get(self, path, **kwargs):
            await asyncio.sleep(0.01)
            return await super().get(path, **kwargs)

    async def scenario():
        client = IndstocksClient()
        client.http = SlowHttp(payload)
        try:
            await client.live_quote("42")
        except RuntimeError as exc:
            assert "exceeded stale threshold" in str(exc)
        else:
            raise AssertionError("slow quote response must be rejected")
        await client.close()

    asyncio.run(scenario())


def test_order_trades_uses_documented_get_body_and_validates_fills():
    payload = {"status": "success", "data": [
        {"fill_id": 1, "quantity": 4, "price": 105.0, "trade_date": "2026-10-22T10:00:00+05:30"},
        {"fill_id": 2, "quantity": 6, "price": 106.0, "trade_date": "2026-10-22T10:00:01+05:30"},
    ]}

    async def scenario():
        client = IndstocksClient()
        client.http = FakeHttp(payload)
        fills = await client.order_trades("ORD-123", "DERIVATIVE")
        assert len(fills) == 2
        assert client.http.calls == [(
            "/order/trades",
            {"json": {"order_id": "ORD-123", "segment": "DERIVATIVE"}},
        )]
        await client.close()

    asyncio.run(scenario())


def test_order_trades_rejects_non_positive_fill_values():
    payload = {"status": "success", "data": [{"quantity": 0, "price": 10}]}

    async def scenario():
        client = IndstocksClient()
        client.http = FakeHttp(payload)
        try:
            await client.order_trades("ORD-123")
        except RuntimeError as exc:
            assert "non-positive" in str(exc)
        else:
            raise AssertionError("invalid fill quantity must be rejected")
        await client.close()

    asyncio.run(scenario())
