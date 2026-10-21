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
