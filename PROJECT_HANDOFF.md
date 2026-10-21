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
- Validation: GitHub Actions run 39657557383 passed compile and the full test suite on Python 3.11, 3.12, and 3.14 for head `71544bb1c9264c3f7aa727e63072a568ec3e3256`. No local test suite has been run from the user's Windows environment. PR #3 was merged into main; follow-up recovery limitations are tracked below.


## Execution replay instrumentation — 2026-10-22

- Branch: `fix/execution-replay`, based on current `main`.
- `app/trader.py` now writes `signal_accepted_for_execution` audit events with contract identity, entry/stop/target, size, EV, and explicit microstructure confirmation/depth-level count after all existing entry gates pass and before execution is attempted.
- While a position is open and a dedicated live quote succeeds, the trader records a `position_quote` audit event containing LTP, bid/ask, stop/target, quantity, source, and position open time. Failed/stale quote events are not falsely written as fresh quote observations.
- Added `backtest/execution_replay.py`: groups recorded position quotes by security ID/open time, detects the first observed LTP stop/target threshold, estimates exit gross P&L using the captured bid, and marks positions without a trigger as open-at-end mark-to-market. CLI writes JSON under `.quantnifty/reports/`.
- Important: this is explicitly **diagnostic estimate only**, not broker-fill reconstruction or validated strategy backtest. It cannot reconstruct partial fills, depth, fees, slippage, queue priority, order latency, or broker-confirmed exits. P&L estimates are not realized P&L.
- Added `tests/test_execution_replay.py` for stop detection, open-at-end mark-to-market labelling, malformed inputs, and report disclaimer.
- Existing raw option-chain history remains insufficient to retroactively reproduce live five-level depth confirmation; no historical trades should be classified as strategy-valid unless matching depth/audit evidence exists.
- No live token, market API, or order submission used. Live routing remains disabled. `data/instruments/fno.csv` and the five-level gate are unchanged.
- CI pending for this branch head. Do not merge before all Python matrix jobs pass and the replay limitations are reviewed.


## Confirmed-fill reconciliation follow-up — 2026-10-22

- Follow-up branch: `fix/confirmed-fill-reconciliation`, based on merged main commit `c205c82c64ab289948bfe64c1032abfc777e269f`.
- Added stable position identity (`position_opened_at`) and stop/target metadata to `entry_filled` and `exit_fill` audit events.
- Added `reconcile_recorded_fills()` to the diagnostic replay. It uses recorded entry/exit fill prices and quantities rather than treating a quote-trigger as proof of an exit. Partial exits remain unresolved; gross P&L is computed only for the quantity with a recorded exit fill.
- Distinguishes paper-mode simulated fills from recorded live fill events. Even LIVE event reconciliation does not query the broker and must be compared with broker order book/positions before accounting or restart recovery is considered complete.
- Added tests for partial live exit, complete multi-fill live exit, and paper-mode classification.
- This work does not recover positions from a restart, query broker truth, or change the microstructure gate. No live connection/order used; live routing remains disabled; `data/instruments/fno.csv` remains unchanged.
- PR #6 merged to main as commit `594ea1f6d13fa51ddcacd6ab36565936638145aa`; all Python 3.11/3.12/3.14 matrix jobs passed on the final PR head and post-merge main CI run `39662361715` passed.


### PR #6 CI issue and fix — 2026-10-22

- First PR #6 CI run failed with 3 failures in `tests/test_execution_replay.py`; 91 tests passed. The added fixtures joined JSON objects with the literal characters `\\n` rather than actual newline separators, so the JSONL loader correctly ignored the combined invalid line.
- Fixed all three fixture writers to join with actual newline characters in commit `458b1d70853ad36f375487330efa56c958419d11`.
- The corrected final PR head passed all three Python 3.11/3.12/3.14 CI jobs in run `39662099853`; the post-merge main workflow is tracked separately.


## Market-data integrity ported to current main — 2026-10-22

- Original PR #4 could not merge because its handoff changes conflicted with later main updates. A clean port branch `fix/market-data-integrity-v2` was created from current main and the code/tests/workflow changes were reapplied without overwriting current execution-replay changes in `app/trader.py`.
- Includes fail-closed quote validation, exact contract identity and lot-size checks, stale-price square-off guard, regression tests, and CI action/runner maintenance.
- Provider event-time schema is still unverified; receive time is not provider event freshness. No live API/token/orders used. Five-level gate and `data/instruments/fno.csv` unchanged.
- PR #7 merged to main as commit `986881bb1a94d9eb24e622088c229590b630ccac` after its Python 3.11/3.12/3.14 CI run `39662819234` passed. Post-merge main CI run `39663019084` was queued when this handoff update began; verify it before claiming final green status.


## Current repository state — 2026-10-22

- PR #7 is merged to `main`; it ports the market-data integrity, exact contract matching, quote sanity, and stale-price square-off guard changes onto the latest base.
- PR #4 is closed as superseded by PR #7 to avoid keeping a conflicting duplicate open.
- Live routing remains disabled. The provider's event-time schema is not verified, so the recorded quote receive time is not proof of market-event freshness.
- Important remaining safety limitation: startup deliberately blocks on unresolved order journal entries, but open broker positions are not automatically reconstructed or flattened. No broker positions endpoint has been verified in this repo; do not invent one. Next work should add a read-only reconciliation report only against documented/verified broker responses, and keep manual position confirmation required.


## Read-only broker order reconciliation report — 2026-10-22

- Added `read_only_broker_order_reconciliation()` to compare unresolved local journal order IDs with a caller-supplied broker order-book snapshot from the existing client method.
- Report is strictly read-only: no submit/cancel calls, no journal auto-reconciliation, and no kill-switch clearing. Missing/ambiguous order IDs and corrupt/unreadable journals fail closed for manual review.
- An order-book match is not proof the account is flat. Broker positions are not queried because a verified provider positions endpoint/schema is not established in this repository. Manual position confirmation remains mandatory.
- Added tests for partial-fill matching, missing/ambiguous order IDs, corrupt journal, and input validation. PR #8 merged to main as `cb9c3dd9383ff1153950b1c74187812d46d3e031` after all Python 3.11/3.12/3.14 jobs passed in run `39663185063`.
- No live token/API connection/orders used; live routing remains disabled; the five-level microstructure gate and `data/instruments/fno.csv` are unchanged.


## Latest verification — 2026-10-22

- PR #8 merged to main after Python 3.11, 3.12 and 3.14 CI passed: run `39663185063`.
- Read-only order-book reconciliation reports local journal/order-book matches but intentionally does not reconcile the account's position inventory or clear the kill switch.
- The latest merged code still needs post-merge CI validation; check the newest main run before further merge actions.
- Remaining work is not safe to call complete: provider event timestamp schema and account positions API schema are unverified. Do not invent either endpoint or enable live routing. Restart recovery must remain fail-closed until verified broker order AND position reconciliation is available.


## Operator CLI for read-only broker order report — 2026-10-22

- Added `python -m app.order_journal --report-broker-order-book` to fetch the existing documented order-book endpoint and print the read-only reconciliation report.
- This command performs only an HTTP GET through the existing `order_book()` client method. It does not submit/cancel orders, mutate the journal, or clear the kill switch. It requires the user's local `INDSTOCKS_ACCESS_TOKEN`; no token was requested or used during implementation.
- `--reconcile` now requires an explicit non-empty `--reason` and its help text reminds the operator to verify both orders and positions. This manual action remains separate from the report.
- Broker position inventory remains unverified because the provider position endpoint/schema is not confirmed in this repository. The report explicitly says positions were not checked.
- CI pending for branch `feat/read-only-order-reconciliation-cli`. Live routing remains disabled; five-level gate and `data/instruments/fno.csv` unchanged.


## Read-only broker position reconciliation — 2026-10-22

- Verified the INDstocks documented `GET /portfolio/positions?segment=derivative&product=intraday` endpoint and response fields `security_id`, `net_qty`, `symbol`, `segment`, `product`, `drv_instrument`, `drv_expiry_date`, `drv_option_type`, and `drv_strike_price`. Reference: https://api-docs.indstocks.com/portfolio_funds/
- Added `IndstocksClient.intraday_derivative_positions()` with strict success-envelope, list, required-field, and finite-net-quantity validation.
- Extended the report CLI to fetch both the order book and derivative intraday position snapshot. Non-zero positions are listed as requiring operator review; malformed snapshots block the report. The report is explicitly scoped to derivative intraday positions and is a point-in-time snapshot.
- The CLI remains read-only. It does not submit/cancel orders, mutate journal state, or clear the kill switch. A zero-position snapshot alone is not proof against stale responses, subsequent fills, or positions in other segments/products.
- Added regression tests for the endpoint schema, query parameters, non-zero position flags, clean scoped snapshots, and invalid quantities. CI pending on `feat/read-only-position-reconciliation`.
- No live token was used. Five-level gate and `data/instruments/fno.csv` unchanged.
