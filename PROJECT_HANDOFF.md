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
- Added regression tests for the endpoint schema, query parameters, non-zero position flags, clean scoped snapshots, and invalid quantities. PR #10 merged as `a448c974f4a165410b113b20eded28049ba44977`; all Python 3.11/3.12/3.14 jobs passed on the PR head in run `39663789162`.
- No live token was used. Five-level gate and `data/instruments/fno.csv` unchanged.


## Startup read-only reconciliation visibility — 2026-10-22

- When the local order journal has unresolved entries and an access token is configured, startup now attempts the same read-only order-book + derivative-intraday-position report before exiting in a safety hold.
- The startup path prints the report and summary only; it never submits/cancels orders, auto-reconciles journal entries, clears the kill switch, or resumes trading. If either snapshot fails, startup remains blocked and says manual reconciliation is required.
- If no access token is configured, startup still blocks and reports that the broker snapshot was not attempted.
- Added tests for both-snapshot retrieval and fail-closed propagation of a positions endpoint failure.
- PR #10 merged as `a448c974f4a165410b113b20eded28049ba44977`; all Python 3.11/3.12/3.14 jobs passed on its PR head, and post-merge main CI run `39663868581` passed.
- Live routing remains disabled. The report only covers derivative intraday positions; this is not a guarantee about all products/segments or future account state. Five-level gate and `data/instruments/fno.csv` unchanged.


## Startup reconciliation follow-up — 2026-10-22

- PR #11 merged to main as `cf58ba58c06029c50348d8bb733b6f546f02310c` after Python 3.11/3.12/3.14 CI passed on the final PR head in run `39663987345`.
- When unresolved journal entries exist and a local token is configured, startup now attempts the read-only order-book + derivative intraday-position report, prints it, and still exits in a safety hold. If any snapshot fails, it stays blocked. No token means no snapshot attempt and still blocks.
- No automatic journal reconciliation, kill-switch clearing, order submit/cancel, or trading resumption. The report only covers DERIVATIVE/INTRADAY and is a point-in-time view.
- Next work: improve quote-event timestamp validation against documented fields and harden order/trade fill reconciliation. Do not enable live routing. Five-level gate and `data/instruments/fno.csv` remain unchanged.


## Quote response latency guard — 2026-10-22

- Official INDstocks full-quote documentation shows `live_price` and market depth but does not document a provider event timestamp for REST full quotes: https://api-docs.indstocks.com/MarketQuote/
- Added measured request/response latency to `live_quote()`; responses taking longer than `CONFIG.stale_seconds` are rejected after retry rather than treated as fresh.
- Position monitoring records latency and `freshness_basis=request_round_trip_time_only`. This is a transport-latency guard, not proof of exchange-event age; do not describe it as provider timestamp validation.
- Added tests for latency metadata and stale-threshold rejection. PR #13 merged as `bc183d4909a5fc3548270ee10ac72a760b95e412`; all Python 3.11/3.12/3.14 jobs passed on its exact head in run `39664281748`.
- No live token used. Live routing remains disabled; five-level gate and `data/instruments/fno.csv` unchanged.


## Latest merged quote-latency guard — 2026-10-22

- PR #13 merged to main as `bc183d4909a5fc3548270ee10ac72a760b95e412`; its final-head Python 3.11/3.12/3.14 matrix passed (run `39664281748`). Draft duplicate PR #12 is closed as superseded.
- Latest quote guard rejects slow REST full-quote responses based on round-trip latency only. Official provider docs do not specify an event timestamp for this REST response; provider event-time freshness remains unresolved.
- Continue only with documented provider endpoints, offline tests and read-only reconciliation. No live token used. Live order routing remains disabled; five-level microstructure gate and `data/instruments/fno.csv` unchanged.


## Read-only per-order fill reconciliation — 2026-10-22

- Official INDstocks order docs specify `GET /order/trades` with JSON body `order_id` and `segment`, returning individual `quantity`, `price`, and `trade_date` fields: https://api-docs.indstocks.com/normal_orders/
- Added strict `IndstocksClient.order_trades()` validation for response envelope, fill list, positive integer quantities, and finite positive prices.
- Extended the read-only report to retrieve fill details for unresolved journaled order IDs, compute total fill quantity and weighted average price, and compare fill quantity against the order-book traded quantity. Mismatches require review; this does not auto-resolve journal state or prove position flatness.
- Added tests for GET body shape, fill schema, multi-fill totals, and mismatch detection. PR #15 merged as `30e630a7c2a3b02d967f7fd75b31af47a47aa103`; all Python 3.11/3.12/3.14 jobs passed on its exact head in run `39664690399`.
- No live token used. Live routing remains disabled; five-level gate and `data/instruments/fno.csv` unchanged.


## Latest fill-reconciliation update — 2026-10-22

- PR #15 merged to main as `30e630a7c2a3b02d967f7fd75b31af47a47aa103` after all Python 3.11/3.12/3.14 jobs passed on its final head (run `39664690399`). Draft duplicate PR #14 is closed as superseded.
- Read-only reconciliation now checks order-book status, documented derivative-intraday position snapshot, and per-order trade fills for unresolved journaled order IDs. It compares fill quantity against the order book and flags mismatches for manual review.
- It still does not auto-clear the kill switch or mark journal records reconciled. Startup stays blocked until operator verification. The position snapshot only covers DERIVATIVE/INTRADAY; review all relevant segments/products and current broker state before manually clearing.
- Live routing remains disabled. No live token or broker account was used during development. Five-level gate and `data/instruments/fno.csv` unchanged.


## Local startup reconciliation fix — 2026-10-22

- Fixed `order_trades()` to use `httpx.AsyncClient.request("GET", ...)` with the documented JSON body; `AsyncClient.get()` rejects the `json` argument and caused a TypeError during startup reconciliation.
- Added a regression assertion that the fill endpoint is invoked using GET while preserving its JSON payload and fill-schema validation.
- Startup remains fail-closed: this fix does not clear the kill switch or reconcile orders automatically. Verify broker orders, fills, and positions before operator reconciliation.


## Per-order fill lookup failure handling — 2026-10-22

- Read-only broker reconciliation now continues to report the order book and derivative intraday positions if an individual per-order fill lookup fails.
- Failed fill lookups are listed under `trade_fetch_errors`, `reconciliation_complete` is false, and `manual_review_required` is true. This is diagnostic only and never clears unresolved journal records or the kill switch.


## One-lot sizing cap — 2026-11-02

- Added `MAX_LOTS_PER_TRADE` with a default of `1`. QuantNifty now rounds the risk-approved quantity down to a valid contract lot and caps it at one lot by default.
- If the risk budget cannot support a full lot, the candidate is skipped; the cap never forces a larger risk size. Contract lot-size lookup, five-level microstructure confirmation, daily limits, duplicate protection, kill switch, and reconciliation are unchanged.
- No live order routing was enabled. No local app restart or runtime validation was performed by the repository change itself; verify CI and restart locally in PAPER mode after reviewing broker state.

## Startup monitor-only safety hold — 2026-11-25

- PR #28 adds a persistent monitor-only loop when startup detects unresolved order-journal entries.
- The app keeps polling read-only market data at `CONFIG.poll_seconds` during market hours, evaluates the mathematical strategy, and displays candidate details without calling `ExecutionEngine.enter`.
- Outside market hours, the monitor-only terminal refreshes at the configured polling interval rather than exiting or waiting 30 seconds.
- The terminal displays `MONITOR ONLY — ORDER EXECUTION DISABLED` and the startup safety-hold reason on each refresh.
- The startup broker reconciliation remains read-only and runs once. No order submit/cancel/modify, journal reconciliation, position mutation, or kill-switch clearing is performed by monitor-only mode.
- Candidates found in this mode are audited as `signal_accepted_for_monitoring`, not `signal_accepted_for_execution`.
- Added `tests/test_terminal_safety_hold.py` to verify the persistent safety banner.
- GitHub Actions run 45610128536 passed on Python 3.11, 3.12, and 3.14 for head `99ec5018a39b49669fa86192f35fc4ef5b79581c`.
- PR #28 is open and ready for review; it has not been merged. Local Windows runtime validation is still required.
- Keep the kill switch ON until the 10 unresolved journal records are independently verified and manually reconciled. PAPER-only; live routing remains disabled.

---

## 2026-11-25 — Position recovery and quote-integrity milestones

**Current main code commit before this handoff update:** `b99739b66a6c271e071b80fe94fb7dbf4ea40738`

### Merged milestones

- **PR #29:** Added `PROJECT_HANDOFF_CONTINUATION_2026-11-25.md` and replaced the JWT-shaped value in `.env.example` with a harmless placeholder. The old credential remains in Git history; account owner must rotate/revoke it.
- **PR #30:** Added separate PAPER open-position persistence at `.quantnifty/open_position.json`, IST date and data-integrity validation, restoration with stale quote state, persistence after entry/partial exit, cleanup after full close, and startup monitor-only safety holds for persistence failures.
- **PR #31:** Added local option-chain receive timestamps, stale quote rejection, complete option-window replacement, exact security-ID contract checks for lot size, five-level chain/depth quote consistency, ask-based EV, structured candidate-evaluation audit records, per-fill gross P&L fields, and token redaction.

### Safety preserved

- PAPER-only development; real-money routing remains disabled.
- PR #28 startup monitor-only mode remains intact.
- Daily remaining-loss budget check remains in the candidate path.
- Five-level microstructure confirmation remains mandatory.
- Persistent kill switch and order journal remain fail-closed.
- The one-lot default remains unchanged.
- `.env.example` contains only a placeholder, not the old token.

### PR status

- PR #30 merged; PR #24 closed as superseded.
- PR #31 merged; PR #23 closed as superseded.
- PR #25 closed as superseded by the separate-file design in #30.
- No open PRs were present at the time of this update.

### CI

- PR #30 final head: Python 3.11, 3.12 and 3.14 passed (run 45617884487).
- PR #31 final head: Python 3.11, 3.12 and 3.14 passed (run 45618417820).
- Main post-merge run for code commit `b99739b66a6c271e071b80fe94fb7dbf4ea40738`: run 45618535657; check its final status before further code changes.

### Remaining work

1. Windows-local PAPER restart validation with isolated test state.
2. Inspect actual local open-position state, kill switch, order journal and broker evidence before any manual reconciliation.
3. Investigate the 2026-11-02 22750 CE trade/exit discrepancy using local raw data, audit, journal and broker evidence.
4. Verify provider exchange-event timestamp semantics; current option freshness is based on local receive time, and REST quote latency is round-trip time only.
5. Build deterministic execution backtesting with historical bid/ask/depth, fees, slippage, latency and partial-fill assumptions.
6. Validate learner idempotency and chronological walk-forward calibration.
7. Improve operational health and feed/persistence/audit monitoring.
8. Rotate the INDstocks credential that was previously committed in Git history; consider history cleanup only after rotation.

**Next-session workflow:** inspect current GitHub state → validate PAPER restart locally → investigate the 2 November trade → verify provider timestamp documentation → improve backtesting/learning/operations. Never enable live trading or infer broker flatness.

---

## 2026-11-25 — Learner and daily-report milestones

**Main code commit before this documentation update:** `68eb85b50e436bcc84dacbf9fd4238688bb8c4f8` (PR #32); latest merged code commit: `f9d55270358122463810ca3af5301b904a7b9a5c` (PR #33).

### PR #32 — learner correctness

- Completed trade learning records now use a stable identity composed of the option security ID and original position-open timestamp.
- Repeated calls for the same completed trade are ignored, including after a process restart.
- Learner updates are applied only to outcomes whose trading date is strictly earlier than the current date. Same-day and future-dated outcomes remain pending.
- Processed IDs are persisted in a bounded list. Existing probability calibration and feature-weight limits remain unchanged.
- CI passed Python 3.11, 3.12 and 3.14 (run 45618984970).

### PR #33 — daily audit coverage

- Daily reports include execution and monitor-only acceptances, candidate-blocked events, candidate evaluation batch/count totals, and chain/depth quote consistency checks/mismatches.
- Explicit warnings are added when chain/depth consistency checks fail.
- Existing summary keys were retained for backward compatibility.
- CI passed Python 3.11, 3.12 and 3.14 (run 45619450707).

### INDstocks timestamp documentation review

Official documentation reviewed:
- API Conventions: https://api-docs.indstocks.com/conventions/
- Market Quotes: https://api-docs.indstocks.com/MarketQuote/
- WebSocket Streaming: https://api-docs.indstocks.com/Websockets/

The conventions page states that API timestamps use IST and Unix epoch milliseconds unless specified otherwise. The WebSocket LTP example contains a timestamp field. However, the REST option-chain and full-quote response schemas do not list a quote timestamp, and the WebSocket quote-mode response schema is not specified on the documentation page. Therefore PR #31 correctly uses local option-chain receive time; REST full-quote request round-trip latency must not be represented as exchange-event time. Do not change freshness semantics until INDstocks confirms the relevant option quote timestamp field and meaning.

### Remaining pending work

1. Windows-local PAPER restart validation with isolated test state.
2. Inspect actual local open-position state, kill switch, order journal and broker evidence before any manual reconciliation.
3. Investigate the 2026-11-02 22750 CE trade/exit discrepancy using local raw data, audit, journal and broker evidence.
4. Rotate the INDstocks credential that was previously committed in Git history; consider history cleanup only after rotation.
5. Build deterministic execution backtesting using historical bid/ask/depth, slippage, fees, latency and partial-fill assumptions. This requires suitable historical market data and explicit fill assumptions.
6. Validate chronological walk-forward calibration with no look-ahead leakage; learner idempotency and prior-day-only training are now implemented in PR #32.
7. Improve operational health beyond process liveness, including feed freshness, audit write health, persistence health and safety-hold visibility.

No live order routing was enabled or used during these changes.

---

## 2026-11-26 — Private PAPER research archive (PR #35)

- Merged PR #35 (merge commit `caa3f7901bc453fa6cdf57c6cfd42c3fcf01dee6`): added GitHub batch sync for local PAPER research evidence.
- Destination repository: `Sabari2811/Mathematical-Trading-Research` (verified private).
- The app captures raw option-chain snapshots, decision/execution audit events and daily report summaries under local `.quantnifty/`; configured sync uploads newly appended bytes every 300 seconds and uploads the post-market report.
- Upload verifies destination privacy on every run, redacts credential-like fields, enforces a 20 MiB archive cap and advances local byte cursors only after GitHub confirms upload.
- Explicitly supplied empty cursor state is honored; regression test added.
- The sync refuses non-PAPER mode or enabled live routing. It does not submit, cancel or reconcile broker orders. It excludes `.env`, local order journal, open-position state and kill-switch state. Existing kill-switch, monitor-only and reconciliation safeguards remain unchanged.
- Setup is documented in `docs/PRIVATE_PAPER_RESEARCH_ARCHIVE.md`. Local `.env` must contain `GH_RESEARCH_REPOSITORY=Sabari2811/Mathematical-Trading-Research`, `GH_RESEARCH_TOKEN` (fine-grained token scoped to this repo with Contents read/write), and `GH_RESEARCH_SYNC_INTERVAL_SECONDS=300`.
- GitHub Actions final head run 45808856184 passed on Python 3.11, 3.12 and 3.14.
- Not yet validated: Windows-local startup, actual token authentication, or first upload. Do not claim data is already in the private repository until a successful local upload is confirmed.
- Keep the GitHub token only in local `.env`; never paste it into chat or commit it. Rotate any credential accidentally exposed outside its intended secret store.
- Next: validate locally in PAPER mode, confirm the first batch appears in the private repository, inspect ZIP contents, then verify subsequent batches advance without duplication. Never enable live routing.


## 2026-11-27 — Research archive backfill and bounded batching (PR pending)

- Added automatic discovery of local raw, audit and report trading dates with pending bytes, oldest-date-first. Fully uploaded files are skipped using durable byte cursors.
- Added bounded JSONL batches (2 MiB source bytes per batch, complete-record boundaries) and a maximum of five successful uploads per sync invocation. Each successful upload advances its cursor only after GitHub confirms the Contents API write.
- Kept the 20 MiB compressed ZIP guard. Non-JSONL reports larger than the source-batch limit fail closed without advancing cursors; oversized individual JSONL records remain subject to the compressed ZIP cap.
- Updated the five-minute and post-market paths to call the pending-date uploader, so stopping the app pauses collection/sync and restarting PAPER mode resumes backfill.
- Added tests for cursor-aware date discovery, complete-line chunking and safe refusal of oversized report files.
- Existing PAPER-only guard, private-repository verification, credential redaction, local-only state, order journal exclusion, kill-switch and live-routing restrictions are unchanged.
- Validation still pending on the exact PR head: GitHub Actions matrix and local Windows test run. Do not claim historical September data has been uploaded until the backfill actually progresses; this implementation processes at most five chunks per invocation.
- Operational note: use Ctrl+C once for normal stop. Do not force-close the process while it may be writing local capture files.
