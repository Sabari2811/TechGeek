# PulseTrade — NIFTY Intraday Price Action Bot

Simple, clean intraday NIFTY options trading application with **GPT-6 Astra as the final trade-decision engine**.

## Decision architecture

`NIFTY SPOT 15M → price-action/structure context → OPTION 5M setup → OPTION 1M trigger → GPT-6 Astra FINAL DECISION → hard risk guard → paper order`

The deterministic strategy computes evidence. **GPT-6 Astra (`gpt-6-astra`) makes the final BUY_CALL / BUY_PUT / WAIT / EXIT_ALL decision.** The AI cannot override the hard session/risk rules.

## Core rules
- **Decision timeframe:** NIFTY SPOT 15-minute candles.
- **Execution timeframes:** 5-minute and 1-minute candles on the selected option strike/premium.
- **Price action first:** market structure, support/resistance, breakouts/retests/rejections and candle confirmation are primary evidence.
- **Indicators:** 9 EMA, 21 EMA and VWAP are confirmation/context, not standalone signals.
- **Trading window:** 09:30–15:15 IST only.
- **Force square-off:** from 15:10 IST; no new trades in the square-off window.
- **No carry forward. No BTST.** Every position must be flat before the session ends.
- **AI decision:** GPT-6 Astra is the source of the trade decision.
- **Default mode:** paper trading. Live broker routing is intentionally disabled.

## Virtual environment — required

Do not install project dependencies globally. Use the project virtual environment for local development, tests and execution.

### Linux/macOS
```bash
./scripts/setup_venv.sh
source .venv/bin/activate
python -m pytest
python -m uvicorn app.main:app --reload
```

### Windows PowerShell
```powershell
.\scripts\setup_venv.ps1
.\.venv\Scripts\Activate.ps1
python -m pytest
python -m uvicorn app.main:app --reload
```

Create `.env` from `.env.example` and set `OPENAI_API_KEY`. The API integration uses the OpenAI Responses API with `model="gpt-6-astra"` and structured JSON output.

Open `http://127.0.0.1:8000`.

## Safety boundary

ASTRA can decide the trade direction, but it cannot bypass the hard session guard. Before 09:30, after 15:15, or during the 15:10 square-off window, the application blocks new entries or exits as required.

This project does **not** contain live broker order routing yet. Before enabling live execution, add a broker adapter, option-chain/strike selection, order-status reconciliation, persistent paper ledger, replay/backtesting, slippage/fees, max-loss limits and a kill switch.
