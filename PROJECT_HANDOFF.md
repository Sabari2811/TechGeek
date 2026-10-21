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


## CI failure analysis and correction — 2026-10-21

- PR #3 initially failed in `Compile Python sources`; the exact error was `app/execution.py:121`, an unterminated f-string in the terminal no-fill reconciliation branch.
- Fixed the syntax error in commit `cc3065123e39938598d7ceb5c2b1cdeb160f168a`.
- Review identified a more important journal policy edge: a filled order must not be considered reconciled merely because its order is terminal. Updated `unresolved_orders` so filled/partially filled order events remain unresolved until an explicit operator `reconciled` event is recorded. Added `mark_reconciled` with a mandatory reason and tests.
- Added fail-closed handling when broker order-book lookup fails during reconciliation: it records the error, trips the entry kill switch, and raises instead of assuming the order state.
- Added offline regression tests for filled-order reconciliation and broker order-book outage.
- Latest commits: `71e843d7639c113069024ad14804a20f72766314` (explicit reconciliation), `b10698a7b6c729d8192ed3f6b857f18e238396dc` (tests), `7440fa8b2e0f09f456058681306bb95dcb52aff9` (order-book failures), `d3cdca4f27fa973c21037480c46ca5db0409c6f0` (failure regression test).
- Validation: GitHub Actions run 39657557383 passed compile and the full test suite on Python 3.11, 3.12, and 3.14 for head `71544bb1c9264c3f7aa727e63072a568ec3e3256`. No local test suite has been run from the user's Windows environment. Keep PR #3 in draft pending code review and remaining recovery work.


## Follow-up branch: market-data integrity and CI maintenance

- Base: merged `main` at `4dcb174b4cee1260a7a33579b6aed6c0ef34c1f6`.
- Branch: `fix/market-data-integrity`.
- `app/market.py`: live quote extraction rejects non-finite/non-positive LTP, invalid negative/non-finite bid/ask, and locked/crossed bid/ask. Successful full-quote responses include a UTC receive timestamp; this is response-receive time, **not proof of provider event freshness**.
- `contract_lot_size` no longer blindly trusts the first instruments-search row. It requires exactly one row whose expiry, strike and option type match the requested contract and whose lot size is a positive integer. If provider identity fields are absent or ambiguous, it fails closed. The provider's real response schema still needs confirmation with a genuine response sample (no token requested).
- Added `tests/test_market_data_integrity.py` for malformed quote prices, crossed/locked markets, exact contract matching, missing identity fields, and ambiguous results.
- `.github/workflows/tests.yml`: updated checkout/setup-python actions to Node 24 compatible versions and pinned the runner to Ubuntu 24.04 to avoid the reported Node 20 and ubuntu-latest migration warnings. CI must verify the action versions and Python matrix.
- This branch does not modify `data/instruments/fno.csv`, weaken the five-level gate, use a live API token, or enable real order routing.
- Square-off safety: `app/trader.py` no longer falls back to stale option-chain bid or LTP for session square-off. It requires a fresh positive bid; otherwise it trips the entry kill switch, records an audit event, and leaves the position open for operator reconciliation. Added unit tests for this rule. This intentionally prefers not to submit an ungrounded sell price; it does not guarantee the position can be closed when the feed is unavailable.
- Remaining known issues: source/provider timestamp freshness still needs provider schema evidence; open-position reconstruction after restart remains manual; replay is not yet a realistic fill/P&L simulator.
- Validation: GitHub Actions must pass for the current head after square-off safety changes. Do not merge while checks are pending or failing.
