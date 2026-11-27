import json
from pathlib import Path

from app import paper_journal


def test_paper_trade_journal_records_campaign_and_simulated_fill(tmp_path, monkeypatch):
    monkeypatch.setattr(paper_journal, "PAPER_TRADE_ROOT", tmp_path)
    paper_journal.record_paper_trade_event(
        "SECURITY-1:2026-11-30T09:45:00+05:30",
        "paper_entry_filled",
        {"side": "BUY", "fill_price": 125.5, "quantity": 65, "stop_price": 110, "target_price": 155},
    )
    rows = [json.loads(line) for line in (tmp_path / "2026-11-27.jsonl").read_text().splitlines()]
    assert rows[0]["event"] == "paper_entry_filled"
    assert rows[0]["simulated"] is True
    assert rows[0]["broker_order_submitted"] is False
    assert rows[0]["details"]["quantity"] == 65
    assert rows[0]["campaign_id"]
