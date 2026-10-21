import json

from app import order_journal


def test_order_intent_is_unresolved_until_terminal_event(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    order_journal.record_order_event("entry-abc", "intent", {"requested_quantity": 50})
    unresolved = order_journal.unresolved_orders()
    assert "entry-abc" in unresolved

    order_journal.record_order_event("entry-abc", "broker_order_id_received", {"order_id": "123"})
    assert "entry-abc" in order_journal.unresolved_orders()

    order_journal.record_order_event("entry-abc", "terminal_partial_fill", {
        "order_id": "123", "traded_quantity": 25
    })
    # A terminal order with a fill can still represent an open position.
    assert "entry-abc" in order_journal.unresolved_orders()
    order_journal.mark_reconciled("entry-abc", "checked broker order book and positions")
    assert order_journal.unresolved_orders() == {}


def test_corrupt_order_journal_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    (tmp_path / "2026-10-22.jsonl").write_text("{bad-json\n", encoding="utf-8")
    unresolved = order_journal.unresolved_orders()
    assert "__journal_corrupt__" in unresolved


def test_unreadable_journal_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    (tmp_path / "2026-10-22.jsonl").mkdir()
    unresolved = order_journal.unresolved_orders()
    assert "__journal_unreadable__" in unresolved



def test_filled_order_requires_explicit_operator_reconciliation(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    order_journal.record_order_event("entry-filled", "intent", {"requested_quantity": 50})
    order_journal.record_order_event("entry-filled", "broker_order_id_received", {"order_id": "456"})
    order_journal.record_order_event("entry-filled", "terminal_filled", {
        "order_id": "456", "traded_quantity": 50, "traded_price": 101.5
    })
    assert "entry-filled" in order_journal.unresolved_orders()

    order_journal.mark_reconciled("entry-filled", "Checked broker order book and positions")
    assert "entry-filled" not in order_journal.unresolved_orders()


def test_reconciliation_requires_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    import pytest
    with pytest.raises(ValueError, match="reason is required"):
        order_journal.mark_reconciled("unknown-ref", "")



def test_read_only_broker_reconciliation_matches_order_without_clearing_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    order_journal.record_order_event("entry-1", "intent", {"requested_quantity": 10})
    order_journal.record_order_event("entry-1", "broker_order_id_received", {"order_id": "123"})
    order_journal.record_order_event("entry-1", "terminal_partial_fill", {
        "order_id": "123", "traded_quantity": 4
    })

    report = order_journal.read_only_broker_order_reconciliation([
        {"id": "123", "status": "CANCELLED", "traded_qty": 4}
    ])
    assert report["read_only"] is True
    assert report["broker_positions_checked"] is False
    assert report["orders"][0]["status"] == "MATCHED_ORDER_ONLY_MANUAL_POSITION_CHECK_REQUIRED"
    assert report["orders"][0]["broker_traded_quantity"] == 4
    assert "entry-1" in order_journal.unresolved_orders()


def test_read_only_broker_reconciliation_flags_missing_or_ambiguous_order_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    order_journal.record_order_event("entry-1", "intent", {"requested_quantity": 10})
    order_journal.record_order_event("entry-1", "broker_order_id_received", {"order_id": "123"})

    missing = order_journal.read_only_broker_order_reconciliation([])
    assert missing["orders"][0]["reason"] == "broker_order_missing_or_ambiguous"

    ambiguous = order_journal.read_only_broker_order_reconciliation([
        {"id": "123", "status": "FILLED", "traded_qty": 10},
        {"id": "123", "status": "FILLED", "traded_qty": 10},
    ])
    assert ambiguous["orders"][0]["broker_match_count"] == 2


def test_read_only_broker_reconciliation_fails_closed_on_corrupt_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    (tmp_path / "2026-10-22.jsonl").write_text("{broken\\n", encoding="utf-8")
    report = order_journal.read_only_broker_order_reconciliation([])
    assert report["status"] == "BLOCKED"
    assert report["reason"] == "journal_corrupt"


def test_read_only_broker_reconciliation_requires_list():
    import pytest
    with pytest.raises(TypeError, match="broker_orders must be a list"):
        order_journal.read_only_broker_order_reconciliation({})


def test_read_only_reconciliation_flags_nonzero_broker_positions(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    report = order_journal.read_only_broker_order_reconciliation(
        [],
        broker_positions=[{
            "security_id": "123",
            "symbol": "NIFTY",
            "segment": "DERIVATIVE",
            "product": "INTRADAY",
            "net_qty": -65,
            "drv_instrument": "OPTIDX",
            "drv_expiry_date": "10/29/2026 14:00",
            "drv_option_type": "PE",
            "drv_strike_price": 25000,
        }],
    )
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["broker_positions_checked"] is True
    assert report["open_positions"][0]["net_qty"] == -65
    assert report["open_positions"][0]["status"] == "OPEN_POSITION_REQUIRES_OPERATOR_REVIEW"


def test_read_only_reconciliation_clean_snapshot_is_scoped_and_read_only(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    report = order_journal.read_only_broker_order_reconciliation([], broker_positions=[])
    assert report["status"] == "NO_UNRESOLVED_JOURNAL_ORDERS_AND_NO_OPEN_DERIVATIVE_INTRADAY_POSITIONS"
    assert report["position_scope"] == "DERIVATIVE/INTRADAY only"
    assert report["read_only"] is True


def test_read_only_reconciliation_blocks_invalid_position_quantity(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    report = order_journal.read_only_broker_order_reconciliation(
        [], broker_positions=[{"security_id": "123", "net_qty": "nan"}]
    )
    assert report["status"] == "BLOCKED"
    assert report["reason"] == "non_finite_position_net_qty"


def test_fetch_read_only_broker_reconciliation_fetches_both_snapshots():
    class FakeClient:
        def __init__(self):
            self.calls = []

        async def order_book(self):
            self.calls.append("orders")
            return []

        async def intraday_derivative_positions(self):
            self.calls.append("positions")
            return []

    import asyncio
    client = FakeClient()
    report = asyncio.run(order_journal.fetch_read_only_broker_reconciliation(client, root=tmp_path))
    assert client.calls == ["orders", "positions"]
    assert report["broker_positions_checked"] is True
    assert report["open_positions"] == []
    assert report["read_only"] is True


def test_fetch_read_only_broker_reconciliation_propagates_snapshot_failure():
    class FakeClient:
        async def order_book(self):
            return []

        async def intraday_derivative_positions(self):
            raise RuntimeError("position endpoint unavailable")

    import asyncio
    import pytest
    with pytest.raises(RuntimeError, match="position endpoint unavailable"):
        asyncio.run(order_journal.fetch_read_only_broker_reconciliation(FakeClient(), root=tmp_path))



def test_read_only_reconciliation_reports_trade_fill_totals(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    order_journal.record_order_event("entry-1", "intent", {"requested_quantity": 10, "security_id": "NFO1"})
    order_journal.record_order_event("entry-1", "broker_order_id_received", {"order_id": "ORD-1"})
    order_journal.record_order_event("entry-1", "terminal_partial_fill", {
        "order_id": "ORD-1", "traded_quantity": 10
    })
    report = order_journal.read_only_broker_order_reconciliation(
        [{"id": "ORD-1", "status": "SUCCESS", "traded_qty": 10}],
        broker_trades={"ORD-1": [
            {"quantity": 4, "price": 105},
            {"quantity": 6, "price": 106},
        ]},
    )
    item = report["orders"][0]
    assert item["trade_fill_count"] == 2
    assert item["trade_fill_quantity"] == 10
    assert item["trade_fill_average_price"] == 105.6
    assert item["fill_reconciliation"] == "MATCHED_TO_ORDER_BOOK_QUANTITY"


def test_read_only_reconciliation_flags_trade_fill_quantity_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(order_journal, "JOURNAL_ROOT", tmp_path)
    order_journal.record_order_event("entry-1", "intent", {"requested_quantity": 10})
    order_journal.record_order_event("entry-1", "broker_order_id_received", {"order_id": "ORD-1"})
    report = order_journal.read_only_broker_order_reconciliation(
        [{"id": "ORD-1", "status": "SUCCESS", "traded_qty": 10}],
        broker_trades={"ORD-1": [{"quantity": 5, "price": 100}]},
    )
    assert report["orders"][0]["fill_reconciliation"] == "FILL_QUANTITY_MISMATCH_REQUIRES_REVIEW"
