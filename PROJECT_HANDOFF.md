# QuantNifty Project Handoff

## Scope and safety
- Repository: `Sabari2811/TechGeek`
- Working branch: `fix/execution-safety-audit`
- Strategy rules and the five-level live microstructure requirement must not be weakened without evidence.
- Real-money order routing must remain disabled during development and validation.
- Do not modify `data/instruments/fno.csv`.
- No live market connection or API token is required for unit tests.

## Current work
### Execution reconciliation and partial fills
- Updated `app/execution.py` to correlate order-book records by broker order ID only, validate quantities, avoid treating a cancellation request as proof of terminal state, and re-check the order book after cancellation.
- Entry is blocked if an in-memory position already exists.
- Confirmed partial entry fills are represented using the actual traded quantity returned by the reconciled terminal order.
- Exit fills are accumulated. If an exit fills only part of the position, the remaining quantity stays open and the trade is not added to the closed-trade ledger yet.
- Updated `app/models.py` to track initial quantity and cumulative exit fills/proceeds, calculate aggregate realised P&L, and record weighted-average exit price for a fully closed position.
- Updated `app/trader.py` to handle a partial exit without treating it as a completed trade or training the learner on a partial result.
- Added `calculate_stop_target` in `app/risk.py`; the stop and target are now derived from the executable entry ask, keeping position sizing and reward/risk calculations on the same price basis. Invalid/non-finite inputs are rejected.
- Added `tests/test_risk_levels.py` to cover stop/target calculation and invalid inputs.
- Added `tests/test_execution_partial_fills.py` for partial-exit accounting and duplicate-entry rejection. Tests use simulated broker responses and do not place orders.
- Hardened `app/microstructure.py`: zero/negative-size levels no longer count as liquidity, and locked/crossed best bid/ask snapshots are rejected. The five-level live requirement remains unchanged; regression tests were added.
- Added `app/kill_switch.py`, a persistent fail-closed entry kill switch. The missing file means OFF; corrupt/unreadable state means ON. `ExecutionEngine.enter` enforces it before any broker call, the terminal monitor displays status, and unresolved order state trips it. Operator controls: `python -m app.kill_switch --on --reason "reason"`, `python -m app.kill_switch --off --reason "reviewed"`, or `python -m app.kill_switch --status`.
- Added separate `.quantnifty/audit/YYYY-MM-DD.jsonl` capture for signal rejections, microstructure payloads/gate outcomes, and confirmed entry/exit fills. It is separate from chain replay files so chain loaders do not confuse audit events for market snapshots. Added tests for JSON-safe audit capture.
- Fixed replay blocking attribution: EV blocks are now counted only when a candidate actually reached the minimum-EV gate; other no-candidate outcomes are tracked separately. Added regression tests.

## Validation status
- Branch head must be checked before further edits; current recent commit is `57a175e7817fc21e88ef2dbc4a57912d87b50142` before any subsequent documentation updates.
- GitHub Actions run 39652726221 passed for commit `52f00b51297403628a092d5cd09b049607f8a055` on Python 3.11, 3.12, and 3.14, including kill-switch and audit tests.
- Replay attribution changes and their tests were added afterward; latest CI must be confirmed for the current head before merge.
- Automated tests have not been executed in the user's Windows-local runtime.
- Automated tests have **not been executed in the user's Windows-local runtime** in this work session.
- No deployment or production validation has been performed.
- No API token was requested or used.
- These changes must not be described as production-ready until automated tests and review are complete.

## Known remaining risks / pending items
1. **Unresolved order state:** a broker order with no returned ID or an unconfirmed terminal state trips the persistent entry kill switch. This prevents new entries but does not itself discover or flatten an unknown broker-side position. Manual broker reconciliation is still mandatory; durable order journal/recovery is still required before live routing.
2. **Stale square-off quotes:** stop/target monitoring blocks price-triggered exits when the dedicated live quote call fails, but session square-off still has fallback paths using chain bid/current price. Define and test a fail-safe square-off workflow without pretending stale prices are executable.
3. **Market-data timestamps:** provider/source timestamps are not yet validated end-to-end. Local receive time must not be mistaken for provider event time.
4. **Contract lot-size matching:** the endpoint is queried with expiry/strike/type filters, but returned rows are not yet independently matched against exact contract identity/security ID. Provider schema needs fixture/response confirmation.
5. **Replay correctness:** `backtest/replay.py` is signal-level, not a full execution simulation. It does not model realistic bid/ask fills, partial fills, stop/target/session exits, fees/slippage, or exact counterfactual trade outcomes. Audit events now capture more evidence but do not replace depth history or full replay.
6. **Learning / walk-forward validation:** verify outcome idempotency and use chronological out-of-sample evaluation with no look-ahead leakage.
7. **Operational health:** health endpoint still reports process availability only; market-feed freshness and trader-task health need separate indicators.
8. **Execution durability:** position and order state are still in memory; restart recovery for open broker positions is intentionally not guessed. A durable order journal/reconciliation procedure remains required.
9. **Final validation:** rerun latest CI, review full PR diff, and run the suite in the user's Windows environment if needed. No deployment or production validation has been performed.

## Required next workflow
1. Inspect current branch head and diff.
2. Verify CI for the latest branch head, not only the earlier commit.
3. Add regression coverage for unresolved broker states, partial entry fills, and recovery; kill switch now trips on key unknown-order paths.
4. Add exact contract identity checks and provider timestamp/freshness validation once the response schema is confirmed.
5. Build deterministic replay with explicit fill/slippage/fee assumptions and counterfactual candidate attribution; do not present chain-only replay as execution P&L.
6. Improve operational health reporting and learning idempotency/walk-forward validation.
7. Run full CI and review the complete diff before merging.
8. Keep live order routing disabled throughout.
