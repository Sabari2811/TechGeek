import json
import os
from typing import Any

from openai import AsyncOpenAI

ASTRA_MODEL = "gpt-6-astra"
ASTRA_REASONING = os.getenv("ASTRA_REASONING", "high")

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["BUY_CALL", "BUY_PUT", "WAIT", "EXIT_ALL"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "setup": {"type": "string"},
        "reason": {"type": "string"},
        "invalidations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "confidence", "setup", "reason", "invalidations"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are the ASTRA 6 decision engine for an intraday NIFTY options paper-trading system.

You make the FINAL TRADE DECISION from the supplied market evidence. Do not invent missing data.
The strategy is price-action first; EMA9, EMA21 and VWAP are confirmation/context only.
15M NIFTY SPOT is the directional decision timeframe. 5M and 1M option-premium candles are execution evidence.
Previous-session support/resistance and current price structure are important.

Hard rules that you MUST respect:
- Trade only 09:30 to 15:15 IST.
- At or after 15:10 IST return EXIT_ALL; never open a new trade then.
- No overnight positions, no carry-forward, no BTST.
- A neutral/unclear 15M NIFTY structure means WAIT.
- 5M/1M option evidence cannot override a neutral 15M spot bias.
- Do not manufacture a trade merely because indicators align.
- Prefer WAIT when price action is ambiguous, extended, conflicting, illiquid, or missing.

This is paper trading only. Return one structured decision.
"""


class AstraDecisionError(RuntimeError):
    pass


def _client() -> AsyncOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AstraDecisionError("OPENAI_API_KEY is not configured; ASTRA 6 cannot make the trade decision.")
    return AsyncOpenAI(api_key=api_key)


def _compact_records(df, n=12) -> list[dict[str, Any]]:
    if df is None or len(df) == 0:
        return []
    rows = []
    for idx, row in df.tail(n).iterrows():
        item = {"time": str(idx)}
        for key in ["open", "high", "low", "close", "volume", "ema9", "ema21", "vwap", "prev_support", "prev_resistance"]:
            if key in row.index:
                value = row[key]
                item[key] = None if value != value else float(value)
        rows.append(item)
    return rows


def _payload(market: str, now_ts: str, bias: dict, execution_5m: dict, execution_1m: dict, spot15, opt5, opt1) -> str:
    data = {
        "market": market,
        "timestamp": now_ts,
        "rules": {
            "trade_start": "09:30 IST",
            "trade_cutoff": "15:15 IST",
            "force_exit": "15:10 IST",
            "carry_forward": False,
            "btst": False,
        },
        "15m_nifty_spot": {"bias_engine_context": bias, "candles": _compact_records(spot15)},
        "5m_option_context": {"technical_context": execution_5m, "candles": _compact_records(opt5)},
        "1m_option_context": {"technical_context": execution_1m, "candles": _compact_records(opt1)},
    }
    return json.dumps(data, separators=(",", ":"))


async def decide(*, market: str, now_ts: str, bias: dict, execution_5m: dict, execution_1m: dict, spot15, opt5, opt1) -> dict:
    client = _client()
    response = await client.responses.create(
        model=ASTRA_MODEL,
        reasoning={"effort": ASTRA_REASONING},
        input=[
            {"role": "developer", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": _payload(market, now_ts, bias, execution_5m, execution_1m, spot15, opt5, opt1)}]},
        ],
        text={"format": {"type": "json_schema", "name": "trade_decision", "strict": True, "schema": DECISION_SCHEMA}},
    )
    try:
        result = json.loads(response.output_text)
    except Exception as exc:
        raise AstraDecisionError(f"ASTRA returned an invalid structured decision: {exc}") from exc
    result["model"] = ASTRA_MODEL
    result["reasoning_effort"] = ASTRA_REASONING
    return result
