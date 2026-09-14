import asyncio
from datetime import datetime
from .config import CONFIG
from .models import MarketState
from .market import IndstocksClient, load_chain_into_state, extract_market_depth, summarize_market_depth_payload
from .math_engine import QuantEngine
from .microstructure import MicrostructureEngine, MicrostructureState
from .risk import RiskManager
from .execution import ExecutionEngine
from .learning import IncrementalLearner
from .terminal import Terminal


async def next_expiry(client: IndstocksClient) -> str:
    r = await client.http.get("/market/instruments/expiries", params={"underlying": "NIFTY", "segment": "DERIVATIVE"})
    r.raise_for_status()
    data = r.json().get("data", [])
    if not data:
        raise RuntimeError("No upcoming NIFTY expiry returned")
    return data[0]


async def run():
    if not CONFIG.access_token:
        Terminal.waiting(reason="INDSTOCKS_ACCESS_TOKEN is missing. Configure .env first.")
        return

    client = IndstocksClient()
    state = MarketState()
    micro_state = MicrostructureState()
    risk = RiskManager()
    learning = IncrementalLearner()
    execution = ExecutionEngine(client)
    expiry = None
    risk_day = datetime.now(CONFIG.market_time().tzinfo).date()

    try:
        while True:
            today = datetime.now(CONFIG.market_time().tzinfo).date()
            if today != risk_day:
                risk.state.trades_today = 0
                risk.state.realized_pnl = 0.0
                risk.state.halted = False
                risk.state.halt_reason = ""
                risk_day = today
            learning.learn_if_new_day()

            if not CONFIG.session_active():
                Terminal.waiting(state.spot, "Outside market session. Run during 09:30–15:15 IST.")
                await asyncio.sleep(30)
                continue

            try:
                if expiry is None:
                    expiry = await next_expiry(client)
                chain = await client.option_chain(expiry)
                load_chain_into_state(state, chain)
            except Exception as exc:
                Terminal.waiting(state.spot, f"Data feed warning: {exc}")
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            if execution.position:
                p = execution.position
                q = state.get_option(p.signal.strike, p.signal.option_type)
                if q:
                    p.current_price = q.ltp
                    if q.ltp <= p.signal.stop:
                        closed = await execution.exit(q.bid or q.ltp, "STOP LOSS")
                        risk.record_trade(closed.realized_pnl)
                        learning.record(p.signal, closed.realized_pnl)
                        Terminal.closed(closed, state.spot)
                        await asyncio.sleep(1)
                        continue
                    if q.ltp >= p.signal.target:
                        closed = await execution.exit(q.bid or q.ltp, "TARGET")
                        risk.record_trade(closed.realized_pnl)
                        learning.record(p.signal, closed.realized_pnl)
                        Terminal.closed(closed, state.spot)
                        await asyncio.sleep(1)
                        continue

                if not CONFIG.entries_allowed():
                    price = q.bid if q and q.bid > 0 else (q.ltp if q else p.current_price)
                    closed = await execution.exit(price, "SESSION SQUARE-OFF")
                    risk.record_trade(closed.realized_pnl)
                    learning.record(p.signal, closed.realized_pnl)
                    Terminal.closed(closed, state.spot)
                    await asyncio.sleep(1)
                    continue

                Terminal.active(p, state.spot)
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            allowed, reason = risk.check_market(state)
            if not allowed:
                Terminal.waiting(state.spot, f"NO TRADE — {reason}", {"Session / risk": False, "Mathematical edge": False})
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            signal = QuantEngine.best_signal(state, CONFIG.min_net_ev, learner=learning)
            if not signal:
                Terminal.waiting(state.spot, "No candidate meets the minimum mathematical EV.", {"Session / risk": True, "Minimum net EV": False})
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            q = state.get_option(signal.strike, signal.option_type)
            if not q or q.ask <= 0 or q.spread_pct > CONFIG.max_spread_pct:
                checks = dict(signal.checks)
                checks["Liquidity / spread"] = False
                Terminal.waiting(state.spot, "Candidate rejected by execution-quality guard.", checks)
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            depth_diag = ""
            try:
                depth_data = await client.market_depth([q.security_id])
                depth_diag = summarize_market_depth_payload(depth_data, q.security_id)
                raw_depth = extract_market_depth(depth_data, q.security_id)
                micro = MicrostructureEngine.from_depth(q.security_id, raw_depth, micro_state)
                confirmed, micro_reason = MicrostructureEngine.confirmation(micro)
            except Exception as exc:
                confirmed, micro_reason = False, f"depth feed unavailable: {exc}"

            checks = dict(signal.checks)
            checks["Liquidity / spread"] = q.spread_pct <= CONFIG.max_spread_pct
            checks["Microstructure confirmation"] = confirmed
            checks["Risk / session"] = True
            signal.checks = checks

            if not confirmed:
                reason_text = f"Candidate rejected — {micro_reason} (security_id={q.security_id})"
                if micro_reason == "microstructure unavailable" and depth_diag:
                    reason_text += f" | {depth_diag}"
                Terminal.waiting(state.spot, reason_text, checks)
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            signal.entry = q.ask
            signal.stop = max(q.ltp * 0.75, q.ltp - state.spot * 0.001)
            signal.target = q.ltp + (q.ltp - signal.stop) * 1.8
            signal.reason += f" | depth={micro_reason}"

            lot_size = await client.contract_lot_size(expiry, signal.strike, signal.option_type)
            if lot_size <= 0:
                Terminal.waiting(state.spot, "Candidate rejected: lot size unavailable", checks)
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            raw_qty = risk.size(signal)
            qty = (raw_qty // lot_size) * lot_size
            if qty <= 0:
                Terminal.waiting(state.spot, "Candidate rejected: position size is below one lot", checks)
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            try:
                p = await execution.enter(signal, qty)
                Terminal.active(p, state.spot)
            except Exception as exc:
                Terminal.waiting(state.spot, f"Execution blocked: {exc}", checks)

            await asyncio.sleep(CONFIG.poll_seconds)

    except KeyboardInterrupt:
        Terminal.waiting(state.spot, "Stopped by user.")
    finally:
        await client.close()
