from datetime import datetime
from zoneinfo import ZoneInfo

from app.math_engine import QuantEngine
from app.models import MarketState, OptionQuote, SignalAudit


def test_best_signal_records_every_evaluated_candidate():
    ist = ZoneInfo("Asia/Kolkata")
    observed_at = datetime(2026, 11, 2, 9, 30, tzinfo=ist)
    state = MarketState(spot=23300.0, expiry="2026-11-03")
    state.options = {
        state.key(23000, "CE"): OptionQuote(
            23000, "CE", "1001", "NIFTY-23000-CE",
            0.0, 0.0, 0.0, 1000, 5000, 4900, 18.0,
            observed_at=observed_at,
        ),
        state.key(23600, "PE"): OptionQuote(
            23600, "PE", "1002", "NIFTY-23600-PE",
            0.0, 0.0, 0.0, 1200, 6000, 5900, 19.0,
            observed_at=observed_at,
        ),
    }
    audit = SignalAudit()

    signal = QuantEngine.best_signal(state, min_net_ev=10.0, audit=audit)

    assert signal is None
    assert audit.evaluated == 2
    assert len(audit.candidate_events) == 2
    assert {event["security_id"] for event in audit.candidate_events} == {"1001", "1002"}
    assert all(event["blocking_reason"] for event in audit.candidate_events)
    assert all(event["signal_ready"] is False for event in audit.candidate_events)
    assert all(event["option_quote_timestamp"] == observed_at.isoformat() for event in audit.candidate_events)
