from datetime import datetime
from pathlib import Path

from app.raw_data import record_option_chain, load_option_chain_records


def test_raw_option_chain_round_trip(tmp_path, monkeypatch):
    import app.raw_data as raw

    monkeypatch.setattr(raw, "RAW_ROOT", tmp_path)
    path = record_option_chain(
        {"underlying_ltp": 23300, "expiry": "2026-09-22", "strikes": {}},
        expiry="2026-09-22",
        timestamp=datetime(2026, 9, 18, 10, 0),
    )
    rows = load_option_chain_records(path)
    assert len(rows) == 1
    assert rows[0]["data"]["underlying_ltp"] == 23300
    assert "Authorization" not in rows[0]
