import asyncio

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
