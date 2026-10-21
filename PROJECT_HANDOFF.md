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

## Validation status
- Repository source edits were committed on the working branch; the branch head must be checked before further edits.
- GitHub Actions run 39651877542 passed compile and test steps on Python 3.11, 3.12, and 3.14 for the earlier execution-reconciliation commit.
- Additional stop/target changes and tests were pushed after that run; their latest CI run must still be checked.
- Automated tests have **not been executed in the user's Windows-local runtime** in this work session.
- No deployment or production validation has been performed.
- No API token was requested or used.
- These changes must not be described as production-ready until automated tests and review are complete.

## Known remaining risks / pending items
1. **Unresolved order state:** if cancellation fails or the broker never reports a terminal state, the order may have fills that cannot be fully reconciled by this process. A durable broker-order reconciliation and entry-block/kill-switch policy is still required before any live routing.
2. **Stop/target consistency:** entry uses ask price while stop/target are currently calculated from LTP. Derive risk levels consistently from executable entry and add tests.
3. **Stale square-off quotes:** define and test safe behaviour when session square-off arrives without a fresh bid/ask quote.
4. **Raw data capture:** option-chain snapshots are recorded, but the complete depth payload, decision-by-decision gate outcomes, and execution events are not yet captured in a unified replayable audit stream.
5. **Market-data validation:** verify timestamp freshness, contract identity, numeric sanity, and meaningful (positive-quantity) five-level depth.
6. **Contract lot-size matching:** validate the exact instrument/expiry/strike/type and returned security ID before accepting a lot size.
7. **Replay correctness:** implement realistic bid/ask fills, partial fills, stop/target/session exits, fees/slippage, and exact rejection-reason attribution. Current replay is signal-level rather than a full execution simulation.
8. **Risk and kill switch:** test limits across restarts, partial fills, duplicate signals, and unresolved order state. Confirm persistent kill-switch enforcement before any live use.
9. **Learning / walk-forward validation:** verify outcome idempotency and use chronological out-of-sample evaluation with no look-ahead leakage.
10. **Operational health:** make health reporting distinguish process availability from market-feed freshness and trader-task health.
11. **Project documentation:** continue updating this handoff after each change with commit SHA, test/CI results, deployment status, issues, and next task.

## Required next workflow
1. Inspect current branch head and diff.
2. Verify CI for the latest branch head, not only the earlier commit.
3. Add regression tests for unresolved order states and entry partial fills; decide a safe durable reconciliation/kill-switch policy before live routing.
4. Improve depth/raw capture and data validation.
5. Improve historical replay and post-market P&L reconciliation.
6. Run full CI and review the complete diff before merging.
7. Keep live order routing disabled throughout.
