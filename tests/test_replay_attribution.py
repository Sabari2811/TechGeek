from app.models import SignalAudit
from backtest import replay


def _run_with_audit(monkeypatch, audit):
    monkeypatch.setattr(replay, "load_option_chain_records", lambda path: [
        {"timestamp": "2026-10-21T10:00:00+05:30", "data": {"strikes": {}}}
    ])
    def load_state(state, data, timestamp=None):
        state.options["dummy"] = object()
    monkeypatch.setattr(replay, "load_chain_into_state", load_state)
    monkeypatch.setattr(replay.QuantEngine, "best_signal", lambda *args, **kwargs: (kwargs["audit"].__dict__.update(audit.__dict__) or None))
    return replay.replay_file("unused.jsonl")


def test_replay_does_not_label_no_candidate_as_ev_block(monkeypatch):
    audit = SignalAudit()
    audit.phase = "MARKET_PHASE"
    audit.eligible_before_min_ev = 0
    result = _run_with_audit(monkeypatch, audit)
    assert result.blocked_by_phase == 1
    assert result.blocked_by_ev == 0
    assert result.blocked_by_no_candidate == 1


def test_replay_counts_ev_block_only_when_candidate_reached_ev_gate(monkeypatch):
    audit = SignalAudit()
    audit.phase = "BREAKOUT"
    audit.eligible_before_min_ev = 2
    audit.final_candidates = 0
    result = _run_with_audit(monkeypatch, audit)
    assert result.blocked_by_phase == 0
    assert result.blocked_by_ev == 1
    assert result.blocked_by_no_candidate == 0
