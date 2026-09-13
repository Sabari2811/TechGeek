import asyncio
from .config import CONFIG
from .models import MarketState
from .market import IndstocksClient, load_chain_into_state
from .math_engine import QuantEngine
from .risk import RiskManager
from .execution import ExecutionEngine
from .terminal import Terminal

async def next_expiry(client: IndstocksClient) -> str:
    r = await client.http.get("/market/instruments/expiries", params={"underlying":"NIFTY", "segment":"DERIVATIVE"})
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
    risk = RiskManager()
    execution = ExecutionEngine(client)
    expiry = None
    try:
        while True:
            if not CONFIG.session_active():
                Terminal.waiting(state.spot, "Outside market session. Run during 09:15–15:35 IST.")
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
                        Terminal.closed(closed)
                        await asyncio.sleep(1)
                        continue
                    if q.ltp >= p.signal.target:
                        closed = await execution.exit(q.bid or q.ltp, "TARGET")
                        risk.record_trade(closed.realized_pnl)
                        Terminal.closed(closed)
                        await asyncio.sleep(1)
                        continue
                if not CONFIG.entries_allowed():
                    price = q.bid if q and q.bid > 0 else (q.ltp if q else p.current_price)
                    closed = await execution.exit(price, "SESSION SQUARE-OFF")
                    risk.record_trade(closed.realized_pnl)
                    Terminal.closed(closed)
                    await asyncio.sleep(1)
                    continue
                Terminal.active(p)
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            allowed, reason = risk.check_market(state)
            if not allowed:
                Terminal.waiting(state.spot, f"NO TRADE YET — {reason}")
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            signal = QuantEngine.best_signal(state, CONFIG.min_net_ev)
            if not signal:
                Terminal.waiting(state.spot)
                await asyncio.sleep(CONFIG.poll_seconds)
                continue
            q = state.get_option(signal.strike, signal.option_type)
            if not q or q.ask <= 0 or q.spread_pct > CONFIG.max_spread_pct:
                Terminal.waiting(state.spot, "Candidate rejected by liquidity guard")
                await asyncio.sleep(CONFIG.poll_seconds)
                continue

            signal.entry = q.ask
            signal.stop = max(q.ltp * 0.75, q.ltp - state.spot * 0.001)
            signal.target = q.ltp + (q.ltp - signal.stop) * 1.8
            lot_size = await client.contract_lot_size(expiry, signal.strike, signal.option_type)
            if lot_size <= 0:
                Terminal.waiting(state.spot, "Candidate rejected: lot size unavailable")
                await asyncio.sleep(CONFIG.poll_seconds)
                continue
            raw_qty = risk.size(signal)
            qty = (raw_qty // lot_size) * lot_size
            if qty <= 0:
                Terminal.waiting(state.spot, "Candidate rejected: position size is below one lot")
                await asyncio.sleep(CONFIG.poll_seconds)
                continue
            try:
                p = await execution.enter(signal, qty)
                risk.state.trades_today += 1
                Terminal.active(p)
            except Exception as exc:
                Terminal.waiting(state.spot, f"Execution blocked: {exc}")
            await asyncio.sleep(CONFIG.poll_seconds)
    except KeyboardInterrupt:
        print("\nQUANTNIFTY stopped by user.")
    finally:
        await client.close()
