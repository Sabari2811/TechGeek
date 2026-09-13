# QuantNifty — Mathematical NIFTY Options Engine

Lightweight, terminal-first NIFTY options trading engine for local execution on a laptop during the NSE session.

## Architecture

`INDstocks → market state → deterministic quantitative engine → microstructure confirmation → risk/anomaly gate → execution/reconciliation → terminal`

The live hot path does not depend on a browser, database, dashboard, or LLM. The terminal is only an operator display. The system starts in **PAPER** mode and must be validated before any live order routing is enabled.

The INDstocks API provides a live NIFTY option-chain endpoint with LTP, OI, volume, top-of-book bid/ask, IV and Greeks. It also provides five-level market depth through the market-depth quote endpoint and WebSocket streams for market data and order updates. The implementation uses the option-chain REST endpoint for stable snapshots and five-level depth as a secondary microstructure confirmation layer.

## Quantitative core

- realized volatility
- implied volatility
- probability model
- option fair-value research proxy
- expected payoff / expected value
- liquidity and spread checks
- five-level order-book imbalance
- liquidity depletion / sweep proxy
- absorption detection
- price-follow-through confirmation
- position sizing
- daily loss and trade-count limits
- anomaly/circuit-breaker guard
- target / stop / session square-off
- broker order reconciliation

Microstructure is **not** a standalone BUY/SELL trigger. A sweep is treated as confirmation only; strong absorption, thin liquidity, or severe opposing pressure can reject an otherwise attractive mathematical candidate. Hidden orders and every market participant's fills are not observable from this public feed, so the engine deliberately reports observed book behaviour rather than claiming to identify institutions or manipulation.

Advanced components remain separated for later validation: calibrated option pricing, volatility surface/skew, regime detection, Bayesian updating, Monte Carlo, tail risk, risk of ruin, fractional Kelly, trade-print classification, and walk-forward validation.

## Execution safety

Live orders are correlated with an internal remark/tag. An accepted order is **not** treated as a position immediately. The engine polls the broker order book for actual traded quantity, supports partial fills, and cancels an order that remains working after the reconciliation window. Exit orders use `SELL` for the long option position. This prevents a delayed fill from creating an untracked position.

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

Put the INDstocks access token in `.env`.

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

Use `LIVE` only after paper trading, backtesting and execution-safety validation. Live routing uses the INDstocks order API with derivative/intraday validation and broker reconciliation.

## Safety

- no secrets committed to Git
- no new entries outside the configured session entry window
- maximum trades per day
- maximum daily loss
- abnormal spot-move block
- option spread/liquidity block
- five-level microstructure confirmation
- broker-reported lot-size validation
- position-level stop and target
- session square-off
- pending/partial-fill reconciliation
- paper mode by default

A stop price is not a guaranteed maximum loss during gaps or illiquidity. This is a risk-control system, not a guarantee against market loss.

## Important

This software is an engineering/research system, not a promise of profitability. The current fair-value component is a conservative research baseline, not a calibrated production option-pricing model. Microstructure signals are inference from public market-depth snapshots, not proof of institutional activity. Every quantitative rule must be validated out of sample with realistic fees and slippage before live use.
