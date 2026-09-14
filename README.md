# QuantNifty — Mathematical NIFTY Options Engine

Lightweight, terminal-first NIFTY options trading engine for local execution on a laptop during the NSE session.

## Final architecture

`INDstocks → market state → deterministic mathematical scoring → execution-quality confirmation → risk/anomaly gate → order reconciliation → single-screen terminal`

The live hot path does **not** use EMA, VWAP, moving-average signals, a browser, database, or LLM. The terminal is only an operator display. The system starts in **PAPER** mode and must be validated before live order routing is enabled.

The design deliberately avoids turning every metric into a mandatory gate. Mathematical variables contribute evidence to a composite score; only core safety conditions such as minimum net EV, execution quality, risk limits, anomaly protection and session rules can block an otherwise valid candidate.

The INDstocks API provides a live NIFTY option-chain endpoint with LTP, OI, volume, top-of-book bid/ask and IV. Five-level market depth is used as a secondary execution-quality confirmation layer. Broker Greeks may be absent for a contract; when absent, QuantNifty calculates model Greeks locally from spot, strike, IV and time-to-expiry.

## Quantitative core

- log-return / realized-volatility statistics
- implied volatility
- IV / realized-volatility relationship
- probability model
- option fair-value research proxy
- expected payoff / expected value / net EV
- soft mathematical evidence score
- OI and volume participation
- model option Greeks: Delta, Gamma, Theta and Vega
- bid/ask spread and liquidity
- five-level order-book imbalance
- liquidity depletion / sweep proxy
- absorption detection
- price-follow-through confirmation
- position sizing
- daily loss and trade-count limits
- anomaly/circuit-breaker guard
- target / stop / session square-off
- broker order reconciliation

The score is intentionally **not** a 20-gate checklist. For example, OI activity, volatility evidence and Greeks can strengthen or weaken a candidate without independently vetoing it. This is intended to prevent over-filtering and preserve a practical 1–3 trade/day operating profile.

Microstructure is **not** a standalone BUY/SELL trigger. A sweep is treated as confirmation only; strong absorption, thin liquidity, or severe opposing pressure can reject an otherwise attractive mathematical candidate. Hidden orders and every market participant's fills are not observable from this public feed, so the engine reports observed book behaviour rather than claiming to identify institutions or manipulation.

Advanced components remain separated for later validation: calibrated option pricing, volatility surface/skew, regime detection, Bayesian updating, Monte Carlo, tail risk, risk of ruin, fractional Kelly, trade-print classification, and walk-forward validation.

## Execution safety

Live orders are correlated with an internal remark/tag. An accepted order is **not** treated as a position immediately. The engine polls the broker order book for actual traded quantity, supports partial fills, and cancels an order that remains working after the reconciliation window. Exit orders use `SELL` for the long option position. This prevents a delayed fill from creating an untracked position.

## Terminal behaviour

The terminal is a **single live screen**. Market updates overwrite the current screen instead of appending a scrolling log.

It intentionally shows only:

1. **Signal** — option, entry, stop, target, quantity, probability, net EV and score.
2. **Live trade monitor** — entry, current price, live P&L, stop, target and status.
3. **Checklist** — the mathematical evidence and safety criteria currently supporting the candidate.

Example:

```text
╔══════════════════════════════════════════════════════╗
║              QUANTNIFTY | PAPER                     ║
╠══════════════════════════════════════════════════════╣
║ TIME     10:42:18 IST     NIFTY     25,184.35       ║
╚══════════════════════════════════════════════════════╝

SIGNAL
  🟢 BUY NIFTY 25200 CE
  Entry ₹187.40   SL ₹175.20   Target ₹208.50
  Qty 75   Probability 67.2%   Net EV ₹14.82   Score 84.1

LIVE TRADE
  Entry       ₹187.40
  Current     ₹192.80
  Live P&L    ₹405.00 (+2.88%)
  Stop        ₹175.20
  Target      ₹208.50
  Status      🟢 ACTIVE

CHECKLIST
  ✓ Mathematical valuation       PASS
  ✓ Probability evidence         PASS
  ✓ IV / RV data                 PASS
  ✓ OI activity                  PASS
  ✓ Volume activity              PASS
  ✓ Greeks available             PASS
  ✓ Positive net EV              PASS
  ✓ Spread within limit          PASS
  ✓ Liquidity / spread           PASS
  ✓ Microstructure confirmation  PASS
  ✓ Risk / session               PASS
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
- no EMA/VWAP or moving-average entry logic
- no new entries outside the configured 09:30–15:10 IST entry window
- session ends at 15:15 IST
- maximum trades per day
- maximum daily loss
- abnormal spot-move block
- minimum net EV
- option spread/liquidity block
- five-level microstructure confirmation
- broker-reported lot-size validation
- position-level stop and target
- forced session square-off from 15:10 IST
- pending/partial-fill reconciliation
- paper mode by default

A stop price is not a guaranteed maximum loss during gaps or illiquidity. This is a risk-control system, not a guarantee against market loss.

## Important

This software is an engineering/research system, not a promise of profitability. The current fair-value component is a conservative research baseline, not a calibrated production option-pricing model. Model Greeks are estimates and should not be treated as broker/exchange Greeks. Microstructure signals are inference from public market-depth snapshots, not proof of institutional activity. Every quantitative rule must be validated out of sample with realistic fees and slippage before live use.