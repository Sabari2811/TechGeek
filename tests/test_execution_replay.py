import json

from backtest.execution_replay import replay_position_quotes, write_report


def _event(timestamp, event_type, payload):
    return {"timestamp": timestamp, "event_type": event_type, "payload": payload}


def test_replay_uses_bid_proxy_and_detects_first_stop_trigger(tmp_path):
    audit = tmp_path / "audit.jsonl"
    common = {
        "security_id": "42", "symbol": "NIFTY26OCT25000CE",
        "opened_at": "2026-10-22T10:00:00+05:30",
        "quantity": 65, "entry_price": 100, "stop_price": 90, "target_price": 118,
    }
    rows = [
        _event("2026-10-22T10:00:01+05:30", "position_quote",
               {**common, "ltp": 99, "bid": 98.5}),
        _event("2026-10-22T10:00:02+05:30", "position_quote",
               {**common, "ltp": 89, "bid": 88.5}),
        _event("2026-10-22T10:00:03+05:30", "position_quote",
               {**common, "ltp": 80, "bid": 79.5}),
    ]
    audit.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    results = replay_position_quotes(audit)
    assert len(results) == 1
    assert results[0].exit_reason == "STOP_TRIGGER_OBSERVED"
    assert results[0].exit_price == 88.5
    assert results[0].gross_pnl == -747.5
    assert results[0].pnl_is_realized is False
    assert results[0].quote_count == 3


def test_replay_marks_open_position_to_market_not_realized(tmp_path):
    audit = tmp_path / "audit.jsonl"
    payload = {
        "security_id": "42", "symbol": "OPT", "opened_at": "open-time",
        "quantity": 10, "entry_price": 100, "stop_price": 90, "target_price": 120,
        "ltp": 105, "bid": 104.5,
    }
    audit.write_text(json.dumps(_event("2026-10-22T10:00:00+05:30", "position_quote", payload)))
    result = replay_position_quotes(audit)[0]
    assert result.exit_reason == "OPEN_AT_END_OF_CAPTURE"
    assert result.exit_price == 104.5
    assert result.gross_pnl == 45
    assert result.pnl_is_realized is False


def test_replay_ignores_non_position_events_and_malformed_lines(tmp_path):
    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        "{broken\n" +
        json.dumps(_event("2026-10-22T10:00:00+05:30", "signal_rejected", {"x": 1})) +
        "\n" + json.dumps(_event("2026-10-22T10:00:01+05:30", "position_quote", {
            "security_id": "42", "opened_at": "open", "quantity": 1,
            "entry_price": 100, "stop_price": 90, "target_price": 120,
            "ltp": "nan", "bid": 99,
        })),
        encoding="utf-8",
    )
    results = replay_position_quotes(audit)
    assert len(results) == 1
    assert results[0].quote_count == 0
    assert results[0].data_warnings


def test_report_is_explicitly_diagnostic(tmp_path):
    audit = tmp_path / "audit.jsonl"
    output = tmp_path / "report.json"
    audit.write_text("")
    report = write_report(audit, output)
    assert report["report_type"] == "diagnostic_position_quote_replay"
    assert "Diagnostic estimate only" in report["summary"]["warning"]
    assert json.loads(output.read_text())["summary"]["positions_observed"] == 0



def test_reconcile_recorded_partial_exit_fills_without_claiming_realized_pnl(tmp_path):
    from backtest.execution_replay import reconcile_recorded_fills

    audit = tmp_path / "audit.jsonl"
    identity = {"security_id": "42", "symbol": "OPT", "position_opened_at": "opened-1"}
    rows = [
        _event("2026-10-22T10:00:00+05:30", "entry_filled", {
            **identity, "entry_price": 100, "filled_quantity": 10,
            "mode": "LIVE", "stop_price": 90, "target_price": 120,
        }),
        _event("2026-10-22T10:01:00+05:30", "exit_fill", {
            **identity, "fill_price": 110, "filled_quantity": 4,
            "cumulative_exit_quantity": 4, "reason": "TARGET", "mode": "LIVE",
        }),
    ]
    audit.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    result = reconcile_recorded_fills(audit)
    assert len(result) == 1
    assert result[0]["exit_filled_quantity"] == 4
    assert result[0]["remaining_quantity"] == 6
    assert result[0]["fully_exited_in_recorded_events"] is False
    assert result[0]["pnl_is_realized_in_recorded_events"] is False
    assert result[0]["recorded_gross_pnl"] == 40
    assert result[0]["classification"] == "LIVE_POSITION_NOT_FULLY_RECONCILED"


def test_reconcile_recorded_complete_live_exit_uses_fill_prices(tmp_path):
    from backtest.execution_replay import reconcile_recorded_fills

    audit = tmp_path / "audit.jsonl"
    identity = {"security_id": "42", "symbol": "OPT", "position_opened_at": "opened-2"}
    rows = [
        _event("2026-10-22T10:00:00+05:30", "entry_filled", {
            **identity, "entry_price": 100, "filled_quantity": 10, "mode": "LIVE",
        }),
        _event("2026-10-22T10:01:00+05:30", "exit_fill", {
            **identity, "fill_price": 105, "filled_quantity": 4, "reason": "TARGET",
        }),
        _event("2026-10-22T10:02:00+05:30", "exit_fill", {
            **identity, "fill_price": 106, "filled_quantity": 6, "reason": "TARGET",
        }),
    ]
    audit.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    result = reconcile_recorded_fills(audit)[0]
    assert result["fully_exited_in_recorded_events"] is True
    assert result["remaining_quantity"] == 0
    assert result["average_exit_price"] == 105.6
    assert result["recorded_gross_pnl"] == 56
    assert result["pnl_is_realized_in_recorded_events"] is True
    assert result["classification"] == "RECORDED_LIVE_FILL_EVENTS"


def test_reconcile_labels_paper_events_as_simulated(tmp_path):
    from backtest.execution_replay import reconcile_recorded_fills

    audit = tmp_path / "audit.jsonl"
    identity = {"security_id": "42", "symbol": "OPT", "position_opened_at": "opened-3"}
    rows = [
        _event("2026-10-22T10:00:00+05:30", "entry_filled", {
            **identity, "entry_price": 100, "filled_quantity": 1, "mode": "PAPER",
        }),
        _event("2026-10-22T10:01:00+05:30", "exit_fill", {
            **identity, "fill_price": 101, "filled_quantity": 1, "reason": "TARGET",
            "mode": "PAPER",
        }),
    ]
    audit.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    result = reconcile_recorded_fills(audit)[0]
    assert result["classification"] == "PAPER_SIMULATED_FILL"
