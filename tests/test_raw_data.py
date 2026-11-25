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



def test_raw_market_and_audit_payloads_redact_credentials_and_tokens():
    from app.raw_data import _json_safe

    safe = _json_safe({
        "Authorization": "Bearer top-secret-token",
        "nested": {
            "access_token": "private-token",
            "security_id": "53792",
            "url": "https://example.test/chain?token=abc123&expiry=2026-11-03",
        },
    })

    assert safe["Authorization"] == "[REDACTED]"
    assert safe["nested"]["access_token"] == "[REDACTED]"
    assert safe["nested"]["security_id"] == "53792"
    assert "abc123" not in safe["nested"]["url"]
    assert "token=[REDACTED]" in safe["nested"]["url"]
