# PulseTrade — NIFTY Intraday Price Action Bot

Simple, clean intraday trading application for NIFTY.

## Core rules
- **Decision timeframe:** NIFTY SPOT 15-minute candles.
- **Execution timeframes:** 5-minute and 1-minute candles on the selected option strike/premium.
- **Indicators:** 9 EMA, 21 EMA and VWAP are confirmation tools, not standalone signals.
- **Structure:** previous-session support/resistance.
- **Price action:** engulfing candles, pin bars, breakouts/breakdowns, EMA pullback/reclaim/rejection.
- **Trading window:** 09:30–15:15 IST only.
- **Square-off:** positions are force-closed before 15:15 (default guard begins 15:10).
- **No carry forward. No BTST.** Every position must be flat by the end of the session.
- **Default mode:** paper trading. Live broker order routing should remain disabled until the strategy passes replay/backtest and paper-trading gates.

## Multi-timeframe flow

`NIFTY SPOT 15M → directional bias → OPTION 5M setup → OPTION 1M trigger → risk guard → paper order`

A 5M/1M signal cannot override a neutral 15M spot bias.

## Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## CSV format

`time,open,high,low,close,volume`

The uploaded series is resampled into 15M, 5M and 1M views. For production broker integration, timestamps should be validated as India Standard Time (IST), and option-contract selection/order routing should be implemented behind a broker adapter.
