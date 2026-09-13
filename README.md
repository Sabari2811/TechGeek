# QuantNifty — Mathematical NIFTY Options Engine

Lightweight, terminal-first NIFTY options trading engine for local execution on a laptop during the NSE session.

## Design

`INDstocks API → in-memory market state → deterministic quantitative engine → risk/anomaly gate → execution → terminal`

The live hot path does not depend on a browser, database, dashboard, or LLM. The terminal is only an operator display. The system starts in **PAPER** mode and must be validated before any live order routing is enabled.

INDstocks currently provides a live NIFTY option-chain endpoint with LTP, OI, volume, top-of-book bid/ask, IV and Greeks, plus WebSocket market/order streams. The application uses the option-chain REST endpoint for the first stable implementation and keeps a WebSocket adapter ready for the low-latency path. citeturn1search0turn1search1

## Quantitative core

- realized volatility
- implied volatility
- probability model
- option fair-value proxy
- expected payoff / expected value
- liquidity and spread checks
- position sizing
- daily loss and trade-count limits
- anomaly/circuit-breaker guard
- target / stop / session square-off

Advanced components planned next: calibrated option pricing, volatility surface/skew, regime detection, Bayesian updating, Monte Carlo, tail risk, risk of ruin, fractional Kelly, and walk-forward validation.

## Terminal behaviour

Idle:

```text
QUANTNIFTY | LIVE
NIFTY: 24,587.35
NO TRADE YET
Waiting for mathematical edge...
```

Active position:

```text
QUANTNIFTY | LIVE TRADE
ENTRY: ₹108.50
CURRENT: ₹114.20
STOP LOSS: ₹88.00
TARGET: ₹145.00
LIVE P&L: ₹7,143.00
STATUS: TRADE ACTIVE
```

## Setup — Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Put the INDstocks access token in `.env`. The API uses `Authorization: <access_token>` and the base URL is `https://api.indstocks.com`. citeturn3search7

Run tests:

```powershell
python -m pytest -q
```

Run the terminal engine:

```powershell
python -m app.main
```

## Modes

`TRADING_MODE=PAPER` is the default.

Use `LIVE` only after paper trading, backtesting and execution-safety validation. Live order routing uses INDstocks' `/order` endpoint with derivative/intraday validation and order reconciliation. INDstocks documents order-status and trade-book reconciliation APIs; the application should never assume an accepted order is filled without reconciliation. citeturn2view0

## Safety

- no secrets committed to Git
- no new entries outside the session entry window
- maximum trades per day
- maximum daily loss
- abnormal spot-move block
- option spread/liquidity block
- position-level stop and target
- session square-off
- broker order reconciliation
- paper mode by default

A stop price is not a guaranteed maximum loss during gaps or illiquidity. This is a risk-control system, not a guarantee against market loss.

## Important

This software is an engineering/research system, not a promise of profitability. Every quantitative rule must be validated out of sample with realistic fees and slippage before live use.
