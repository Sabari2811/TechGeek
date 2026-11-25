# QuantNifty — Complete Project Handoff

**Prepared:** 2026-11-25  
**Repository:** https://github.com/Sabari2811/TechGeek  
**Default/integration branch:** `main`  
**Verified main commit at handoff preparation:** `6ae8431210c5c4ec495b5e07bca85aecec907d5e`  
**Latest merged PR:** #28 — Keep QuantNifty monitoring during startup safety hold

> This file is the continuation brief for a fresh ChatGPT conversation. Read this file first, then refresh GitHub state before editing anything. The repository is the source of truth; this handoff records the state observed on 2026-11-25 and may become stale after new commits.

---

## 1. Project purpose

QuantNifty is a Python-based, terminal-first NIFTY options research and PAPER-trading application. It consumes INDstocks market data, builds a market state, evaluates options with a mathematical valuation/probability/expected-value engine, requires market microstructure confirmation, applies risk controls, and records decisions and execution evidence.

The project has three central goals:

1. **Decision quality:** identify selective mathematical opportunities rather than generate frequent indicator-driven trades.
2. **Execution reliability:** handle orders, partial fills, exits, risk limits, restart states and broker reconciliation safely.
3. **Evidence and learning:** capture enough raw data and structured audit events to investigate decisions and improve the strategy without confusing estimates with actual fills.

The user previously chose to remove EMA/VWAP as mechanical entry dependencies. Keep the strategy's mathematical approach. Do not add indicators or change entry logic without first identifying the reason, evidence and regression tests.

## 2. Non-negotiable safety and engineering constraints

- Development, tests and validation must remain PAPER/offline by default.
- **Do not enable real-money order routing.** The current code has a deliberate two-key live guard: mode must be LIVE and `ENABLE_LIVE_TRADING=YES`. Do not change this; for this project keep live routing disabled.
- Do not use a live broker token or place/cancel/modify real orders during development.
- Keep the five-level market-depth/microstructure confirmation requirement intact. Do not lower the required depth levels or bypass confirmation to make tests pass.
- Do not modify `data/instruments/fno.csv`.
- Never commit API tokens, credentials, local `.env`, broker data or local `.quantnifty/` artifacts.
- A missing/failed/stale/ambiguous broker or market-data response must fail closed where it affects execution.
- Never infer broker flatness from an empty local position, an order-book result alone, or an incomplete position snapshot.
- Do not auto-clear the persistent kill switch or auto-mark unresolved journal records reconciled.
- Do not represent quote-triggered replay estimates as broker-confirmed realized P&L.
- Keep tests isolated from the user's actual local kill switch, order journal, audit logs and session state.
- Preserve the full audit trail and distinguish local receive time / REST round-trip latency from verified exchange-event time.
- Use IST (`Asia/Kolkata`) consistently for trading dates and session logic.

### Security alert — action required

During the repository review on 2026-11-25, the current `.env.example` on `main` was found to contain a JWT-shaped value in `INDSTOCKS_ACCESS_TOKEN`, rather than a placeholder. **Do not copy, print, reuse or put that value in this handoff. Treat the credential as exposed.** Replace the sample with a harmless placeholder and revoke/rotate the corresponding INDstocks token through the provider/account. Removing it from the current file does not remove it from Git history; consider history cleanup after rotation. This security cleanup should be handled before treating the repository as safe to share.

## 3. Current repository state

- Main branch: `main`
- Main commit: `6ae8431210c5c4ec495b5e07bca85aecec907d5e`
- Latest main commit message: `Keep QuantNifty monitoring during startup safety hold`
- Latest main commit date: 2026-11-25 12:04:56 UTC
- Latest merged PR: [#28](https://github.com/Sabari2811/TechGeek/pull/28)
- Latest main CI run inspected: [45610362317](https://github.com/Sabari2811/TechGeek/actions/runs/45610362317) — Python 3.11, 3.12 and 3.14 all passed.
- At the time of review: 22 PRs merged, 3 open PRs (#23, #24, #25), and 3 closed as superseded/unmerged (#4, #12, #14).
- The open branches were each 16 commits behind main at the time of the compare check; refresh before action.

Repository links:
- [Repository](https://github.com/Sabari2811/TechGeek)
- [README](https://github.com/Sabari2811/TechGeek/blob/main/README.md)
- [Existing chronological handoff](https://github.com/Sabari2811/TechGeek/blob/main/PROJECT_HANDOFF.md)
- [Pull requests](https://github.com/Sabari2811/TechGeek/pulls)
- [Actions](https://github.com/Sabari2811/TechGeek/actions)

## 4. Architecture and important modules

| Module | Responsibility |
|---|---|
| `app/config.py` | Environment configuration, IST and market-session policy |
| `app/models.py` | Market, option, signal, position and trade data models |
| `app/market.py` | INDstocks HTTP/WebSocket integration, option chain, full quotes, depth, lot size and read-only broker endpoints |
| `app/math_engine.py` | Realized volatility, option valuation, Greeks, probability, regime/phase, scoring, EV and candidate selection |
| `app/microstructure.py` | Five-level depth normalization and liquidity/imbalance/absorption confirmation |
| `app/risk.py` | Stop/target, quantity sizing, lot cap, daily risk checks and risk state |
| `app/execution.py` | PAPER/broker execution abstraction, order reconciliation, partial fills and exits |
| `app/kill_switch.py` | Persistent fail-closed entry kill switch and operator CLI |
| `app/order_journal.py` | Durable order-intent journal, unresolved-state detection and read-only broker reconciliation |
| `app/session_state.py` | Local daily spot history and closed-trade session persistence |
| `app/trader.py` | Main market loop, candidate pipeline, risk gates, position monitoring and terminal updates |
| `app/learning.py` | Persistent bounded incremental learner |
| `app/raw_data.py` | Raw option-chain snapshots and structured JSONL audit events |
| `app/daily_reports.py` | Local daily trade intelligence JSON/Markdown reports |
| `app/terminal.py` | Single-screen terminal, trade state and persistent safety banner |
| `app/main.py` | CLI/API entry points, health and daily report endpoint |
| `backtest/replay.py` | Historical option-chain signal/rejection replay using live mathematical engine |
| `backtest/execution_replay.py` | Diagnostic position-quote replay and recorded-fill reconciliation |
| `backtest/engine.py` | Basic CSV backtest scaffold; not yet a complete execution backtester |

### Main decision/execution flow

1. INDstocks option-chain snapshot is fetched.
2. Raw chain is recorded locally and normalized into market state.
3. Market state is warmed up; spot history supports realized-volatility and market-phase calculations.
4. Mathematical engine evaluates eligible option candidates using valuation, probability, volatility, Greeks, expected value and score.
5. Candidate passes option liquidity/spread and configured freshness checks.
6. Five-level depth/microstructure confirmation is required.
7. Quote-source consistency and remaining daily risk checks are applied where implemented.
8. Contract lot size and quantity are resolved; quantity is rounded down to valid lots and capped.
9. Candidate is audited before execution.
10. Execution engine handles entry/exit fills; persistent kill switch and order journal protect unknown states.
11. Open positions are monitored using dedicated live quotes; stale/failed quote paths must not be treated as current executable prices.
12. Closed trades, audit events and raw data support post-market reports/replay.

## 5. Current configuration defaults from `app/config.py`

These are code defaults only; the user's local `.env` may override them.

| Setting | Default |
|---|---:|
| Trading mode | PAPER |
| Risk capital | ₹20,00,000 |
| Risk per trade | 0.5% |
| Maximum daily loss | ₹20,000 |
| Maximum trades/day | 3 |
| Maximum lots/trade | 1 |
| Minimum net EV | ₹10 |
| Maximum spread | 4% |
| Stale threshold | 3 seconds |
| Option-chain strike count | 10 |
| Poll interval | 2 seconds |
| Risk-free rate | 6% |
| Dividend yield | 1% |
| Session start | 09:30 IST |
| New-entry cutoff | 15:15 IST, also restricted by square-off time |
| Square-off time | 15:10 IST |
| Session end | 15:15 IST |

The configured `entries_allowed()` requires start time reached, before the new-entry cutoff, and before square-off time. Session remains active through the configured end time.

## 6. Pull-request history

### Merged PRs (22)

| PR | Summary |
|---|---|
| [#1](https://github.com/Sabari2811/TechGeek/pull/1) | Consistent IST dates for learning outcomes |
| [#2](https://github.com/Sabari2811/TechGeek/pull/2) | Execution safety, partial fills, persistent kill switch and audit capture |
| [#3](https://github.com/Sabari2811/TechGeek/pull/3) | Durable broker order-intent journaling |
| [#5](https://github.com/Sabari2811/TechGeek/pull/5) | Diagnostic execution replay instrumentation |
| [#6](https://github.com/Sabari2811/TechGeek/pull/6) | Recorded-fill reconciliation in replay |
| [#7](https://github.com/Sabari2811/TechGeek/pull/7) | Ported market-data integrity fixes onto latest main; exact contract checks and stale-price protections |
| [#8](https://github.com/Sabari2811/TechGeek/pull/8) | Read-only broker order reconciliation report |
| [#9](https://github.com/Sabari2811/TechGeek/pull/9) | CLI for read-only broker reconciliation |
| [#10](https://github.com/Sabari2811/TechGeek/pull/10) | Read-only derivative intraday position reconciliation |
| [#11](https://github.com/Sabari2811/TechGeek/pull/11) | Startup visibility for read-only reconciliation while safety-held |
| [#13](https://github.com/Sabari2811/TechGeek/pull/13) | Reject slow REST quote responses using measured request/response latency |
| [#15](https://github.com/Sabari2811/TechGeek/pull/15) | Read-only individual broker trade-fill reconciliation |
| [#16](https://github.com/Sabari2811/TechGeek/pull/16) | Fix HTTPX GET request with JSON body for trade lookup |
| [#17](https://github.com/Sabari2811/TechGeek/pull/17) | Isolate tests from persistent local kill-switch state |
| [#18](https://github.com/Sabari2811/TechGeek/pull/18) | Preserve reconciliation report when individual fill lookup fails |
| [#19](https://github.com/Sabari2811/TechGeek/pull/19) | Isolate partial-fill tests from real order journal |
| [#20](https://github.com/Sabari2811/TechGeek/pull/20) | Cap entries at one lot by default |
| [#21](https://github.com/Sabari2811/TechGeek/pull/21) | Label estimated exits and improve trade forensic audit |
| [#22](https://github.com/Sabari2811/TechGeek/pull/22) | Block entries exceeding remaining daily loss budget |
| [#26](https://github.com/Sabari2811/TechGeek/pull/26) | Automatic local daily trade intelligence reports |
| [#27](https://github.com/Sabari2811/TechGeek/pull/27) | Isolate audit output in simulated execution tests |
| [#28](https://github.com/Sabari2811/TechGeek/pull/28) | Persistent monitor-only market analysis during startup safety hold |

### Closed as superseded/unmerged (3)

- [#4](https://github.com/Sabari2811/TechGeek/pull/4): superseded by #7, which ported market-data fixes onto a newer main.
- [#12](https://github.com/Sabari2811/TechGeek/pull/12): duplicate/superseded by #13 quote-latency guard.
- [#14](https://github.com/Sabari2811/TechGeek/pull/14): duplicate/superseded by #15 fill reconciliation.

Do not reimplement these superseded PRs as separate features.

## 7. Open PRs and review findings (state observed 2026-11-25)

### PR #23 — Block stale option quotes and audit every evaluated candidate

- Branch: `fix/option-quote-freshness-audit-20261102`
- Head at review: `33aaaa3108815125ea97588fc9eea5bb78bf4a2f`
- 24 commits; 12 files; +559 / -32.
- Compare to main at review: 24 commits ahead, 16 behind; diverged.
- GitHub reported merge conflict / dirty merge state.
- CI run [41422440826](https://github.com/Sabari2811/TechGeek/actions/runs/41422440826) passed Python 3.11/3.12/3.14 on that PR head.

Main changes:
- Replace option map with each complete option-chain snapshot so removed strikes do not persist.
- Attach local receive timestamps to quotes and reject stale/missing candidates.
- Compare option-chain bid/ask with selected contract depth bid/ask using configurable tolerance (reviewed code uses 0.5%).
- Verify exact contract identity/security ID during lot-size lookup.
- Add structured audit for evaluated candidates and rejection stages.
- Use executable ask rather than LTP as candidate entry basis for EV/stop sizing.
- Record gross P&L per exit fill and clarify charges/net P&L are not estimated.
- Redact sensitive/token-like keys from recorded data.

Review caveats:
- Local receive timestamp is not provider exchange-event time.
- Existing REST full-quote latency guard is round-trip latency only, not exchange-event freshness.
- Rebase/port onto current main and resolve conflicts before merge.
- Inspect full integrated diff; PR #23 touches `app/trader.py`, `app/execution.py`, market/math/model/config and tests, so it must be integrated carefully with position recovery.
- Retest quote fallback, candidate audit completeness, source consistency, stale/missing quote handling, partial fills and risk.

### PR #24 — Persist open PAPER positions and recover safely after restart

- Branch: `fix/p0-paper-position-persistence`
- Head at review: `fd0bbe3b7a711ea907b3a97b636f431760024d05`
- Draft; 5 commits; 5 files; +275 / -17.
- Compare to main at review: 5 commits ahead, 16 behind; diverged.
- GitHub reported merge conflict / dirty state.
- CI run [43725048292](https://github.com/Sabari2811/TechGeek/actions/runs/43725048292) passed Python 3.11/3.12/3.14 on that PR head.

Main changes:
- Separate `.quantnifty/open_position.json` persistence.
- Persist entry and partial-exit state.
- Restore open PAPER position on restart.
- Treat restored quote as stale and require fresh quote before price-triggered exit logic.
- Clear persistence only after full closure.
- Fail closed and activate kill switch on corrupt/unreadable recovery state.
- Add round-trip, partial-exit, corrupt-state, prior-day and clearing tests.

Review/design points:
- This is the preferred starting point over #25 because open position is a distinct state object rather than a field inside the spot-history/closed-trade session file.
- Review all save/clear call sites, atomic write semantics, schema/version validation, date boundaries and crash windows.
- Ensure the persistence contract is explicit for PAPER mode and does not accidentally persist or restore live positions as PAPER positions.
- Ensure startup recovery and broker order-journal reconciliation do not contradict one another. A restored local PAPER position is not broker proof.
- Rebase/port onto current main, then run the full test suite and simulate process restart with a temporary state directory.
- Keep this PR draft until integrated design and validation are complete.

### PR #25 — Persist and recover open PAPER positions safely

- Branch: `fix/paper-position-recovery`
- Head at review: `0ee80b6fd2c3886bf4db52b81981544573030e66`
- 5 commits; 3 files; +170 / -7.
- Compare to main at review: 5 commits ahead, 16 behind; diverged.
- Alternative implementation using `.quantnifty/session_state.json`.

Review finding:
- In the current PR #25 implementation, an ordinary option-chain polling path calls `save_today(..., None)`; explicit `None` clears the persisted open position. This can erase an open position during ordinary polling.
- Some exit paths also have inconsistent clear/preserve semantics.
- Therefore **do not merge PR #25 as-is**.
- Treat #25 as an alternative/superseded implementation. Once #24 is integrated and tested, close #25 as superseded with a clear explanation. Do not merge both implementations.

## 8. Other important completed behaviour

### Execution and risk
- Broker order responses are reconciled rather than assumed to be fills.
- Partial entry fills use actual reconciled traded quantity.
- Partial exits retain the remaining open quantity; do not train the learner or book a trade as fully closed prematurely.
- Stop/target calculation is based on executable entry price and validates finite positive inputs.
- Duplicate entry while a position exists is blocked.
- Quantity is rounded down to valid contract lots and capped at one lot by default.
- Planned stop risk is checked against remaining daily loss budget.
- Kill switch is persistent and fail-closed: missing file means OFF; corrupt/unreadable state means ON.
- Unknown/unresolved order intent blocks new entries.
- The journal requires explicit operator reconciliation; terminal broker status alone does not prove account flatness.

### Broker reconciliation
- Read-only checks include order book, derivative intraday positions and per-order trade fills.
- Position endpoint coverage is specifically DERIVATIVE/INTRADAY and is point-in-time. It does not prove all products/segments or future account state.
- Failed individual fill lookup remains visible and marks reconciliation incomplete/manual review required.
- Startup must not automatically reconcile journal events, clear kill switch, submit/cancel/modify orders or resume execution.

### Startup monitor-only mode (PR #28)
- When startup finds unresolved journal entries, QuantNifty remains in a persistent monitor-only loop.
- It continues read-only market-data polling and mathematical candidate analysis.
- It displays `MONITOR ONLY — ORDER EXECUTION DISABLED` plus the safety-hold reason.
- Candidates are recorded as `signal_accepted_for_monitoring`, not `signal_accepted_for_execution`.
- It does not call `ExecutionEngine.enter`, mutate broker positions, submit/cancel/modify orders, reconcile journal entries or clear kill switch.
- Startup broker reconciliation is read-only and runs once.
- PR #28 merged to main as `6ae8431210c5c4ec495b5e07bca85aecec907d5e`; run [45610128536](https://github.com/Sabari2811/TechGeek/actions/runs/45610128536) passed all three Python versions on the PR head.

### Reports and replay
- Raw option-chain snapshots: `.quantnifty/raw/YYYY-MM-DD.jsonl`.
- Audit events: `.quantnifty/audit/YYYY-MM-DD.jsonl`.
- Daily reports: `.quantnifty/reports/YYYY-MM-DD/daily_report.json` and `analysis.md`.
- Daily report is local-only and redacts token-like keys.
- Signal replay uses captured option-chain snapshots and the mathematical engine.
- Execution replay uses captured position quote events and is diagnostic only.
- Recorded fill reconciliation uses recorded fills, not quote triggers, for recorded gross P&L.

## 9. Known limitations and pending work

### P0 — Must resolve before considering reliable PAPER restart operation

1. Integrate and validate durable open PAPER position recovery (preferred basis: PR #24).
2. Verify startup behaviour with an open persisted position, corrupt file, stale recovered quote, partial exit and full closure.
3. Verify the kill switch and unresolved order journal remain fail-closed after restart.
4. Independently inspect local broker orders, trades and positions before any manual reconciliation. The previous handoff recorded 10 unresolved journal records; this count is a historical note, **not a freshly verified current count**. Recheck local files and broker state before relying on it.
5. Keep live order routing disabled.

### P1 — Market-data integrity and forensic audit

6. Integrate PR #23 after position-recovery integration; resolve all conflicts and review the complete combined diff.
7. Ensure every evaluated candidate has auditable data and explicit rejection/acceptance stage.
8. Ensure option-chain and depth quotes refer to the same exact contract and source values are consistent.
9. Preserve clear freshness semantics: local receive timestamp, REST round-trip latency and provider exchange-event timestamp are different things. Provider event timestamp remains unresolved unless official docs/schema prove otherwise.
10. Ensure stale/missing quote paths cannot create false entry or exit decisions.

### P2 — Research quality and operational improvements

11. Investigate the 2026-11-02 trade(s), including the reported unmatched 22750 CE entry / stop execution concern, using local audit, raw chain, order journal, session ledger and broker evidence. Do not assume a trade or fill from incomplete data.
12. Improve deterministic execution backtesting with historical bid/ask/depth, slippage, fees, latency and partial-fill assumptions. Clearly label assumptions and simulated results.
13. Validate learner outcome idempotency and chronological walk-forward calibration with no look-ahead leakage.
14. Improve operational health beyond process liveness: trader task health, feed freshness, last successful quote and safety-hold status.
15. Validate Windows-local PAPER startup/restart and deployment only after safe offline tests pass.
16. Update this handoff after every meaningful change.

### Security
17. Replace the JWT-shaped value found in `.env.example` with a placeholder and have the owner revoke/rotate the exposed INDstocks credential. Assess Git history cleanup after rotation. Never reproduce the value in commits, PRs, logs or handoff files.

## 10. Recommended integration order

1. Refresh main and all PR heads/statuses; confirm no one has updated the branches since this handoff.
2. Create a new integration branch from current `main`; do not force-push or blindly merge stale PR branches.
3. Port/rebase PR #24 position-persistence changes first. Resolve conflicts against current main.
4. Review all persistence call sites and add lifecycle tests: entry -> restart -> fresh quote -> partial exit -> restart -> full exit -> clear; corrupt state; previous-day state; write failure; duplicate/repeated saves.
5. Run compile and full pytest suite locally/offline, then push and require Python 3.11/3.12/3.14 CI.
6. Once #24 is stable, port PR #23 onto that integrated branch. Resolve conflicts and verify quote freshness, source consistency, candidate audit, EV basis and interaction with persisted positions.
7. Run the full test matrix again. Review the integrated diff for any weakening of five-level gate, risk limits, kill switch, order journal or live-routing guard.
8. Close PR #25 as superseded only after the preferred implementation is merged or otherwise safely integrated.
9. Create/update PRs with clear evidence and update `PROJECT_HANDOFF.md` and this continuation handoff.
10. Keep the app PAPER-only. No live orders, no live token use in tests and no automatic broker reconciliation.

## 11. Definition of done for today's pending PR work

Do not call the pending PR work complete merely because CI is green. Completion requires:

- Both feature sets (#24 position recovery and #23 quote freshness/audit) integrated without losing existing main functionality.
- Tests for the full lifecycle and relevant failure cases.
- Python 3.11, 3.12 and 3.14 CI green on the final integrated head.
- Full diff reviewed for safety invariants.
- No secrets in current tracked files; exposed token rotated by account owner.
- #25 closed as superseded after #24 is established.
- Updated handoff reflects exact final commits, PR status, CI run IDs and remaining limitations.
- No real-money execution enabled or performed.

Some work may be achievable today, but broker-account verification, credential rotation, Windows-local validation and any provider documentation/account actions require the user. Do not claim those are done without evidence.

## 12. Instructions for the next ChatGPT session

Start by:
1. Reading this file completely.
2. Fetching current `main` commit, open PR list, PR head SHAs, compare status and latest CI.
3. Inspecting current `app/execution.py`, `app/session_state.py`, `app/trader.py`, `app/kill_switch.py`, `app/order_journal.py`, `app/market.py`, and the tests before changing code.
4. Checking whether the security issue in `.env.example` has been remediated and the credential rotated; do not expose the token.
5. Continuing with the integration order above.

Use this workflow for every engineering task:

**inspect → identify gaps → implement → test → commit → deploy only when explicitly appropriate → validate → update handoff.**

The user wants a collaborative, evidence-driven workflow. Explain changes and test outcomes clearly. Do not claim that code has been deployed, locally validated, or broker-verified unless that action actually happened.
