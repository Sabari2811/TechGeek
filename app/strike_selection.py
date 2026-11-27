"""Deterministic NIFTY option-chain selection for QuantNifty.

The provider supplies five strikes on each side of ATM (plus ATM). The
strategy intentionally evaluates an asymmetric 8-leg universe per option
type: CE = 5 below + ATM + 2 above; PE = 2 below + ATM + 5 above.
"""
from __future__ import annotations

from copy import deepcopy
import math


STRIKES_EACH_SIDE = 5
CONTRACTS_PER_SIDE = 8
TOTAL_CONTRACTS = 16


def select_strategy_option_chain(chain: dict) -> tuple[dict, dict]:
    """Return a filtered chain containing exactly 8 CE and 8 PE contracts.

    ATM is the nearest listed strike to underlying_ltp; ties resolve to the
    lower strike. Selection is by listed strike ladder, never hard-coded
    strike intervals. Missing legs or an incomplete ladder fail closed.
    """
    if not isinstance(chain, dict):
        raise TypeError("option chain must be an object")
    spot = chain.get("underlying_ltp")
    try:
        spot = float(spot)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("option chain has no valid underlying_ltp") from exc
    if not math.isfinite(spot) or spot <= 0:
        raise ValueError("option chain has no positive finite underlying_ltp")

    source = chain.get("strikes")
    if not isinstance(source, dict) or not source:
        raise ValueError("option chain has no strike ladder")

    ladder = []
    for raw_strike, legs in source.items():
        try:
            strike = float(raw_strike)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(strike) and strike > 0 and isinstance(legs, dict):
            ladder.append((strike, str(raw_strike), legs))
    ladder.sort(key=lambda item: item[0])
    if len(ladder) < (2 * STRIKES_EACH_SIDE + 1):
        raise ValueError(
            f"incomplete strike ladder: need at least {2 * STRIKES_EACH_SIDE + 1} "
            f"strikes, received {len(ladder)}"
        )

    atm_index = min(range(len(ladder)), key=lambda i: (abs(ladder[i][0] - spot), ladder[i][0]))
    below = ladder[:atm_index]
    above = ladder[atm_index + 1:]
    if len(below) < 5 or len(above) < 5:
        raise ValueError("incomplete strike ladder around nearest ATM; need five strikes on both sides")

    atm = ladder[atm_index]
    ce_selected = below[-5:] + [atm] + above[:2]
    pe_selected = below[-2:] + [atm] + above[:5]

    filtered = {}
    for strike, key, legs in ce_selected:
        filtered.setdefault(key, {})["ce"] = deepcopy(legs.get("ce"))
    for strike, key, legs in pe_selected:
        filtered.setdefault(key, {})["pe"] = deepcopy(legs.get("pe"))

    missing_ce = [strike for strike, key, legs in ce_selected if not isinstance(legs.get("ce"), dict)]
    missing_pe = [strike for strike, key, legs in pe_selected if not isinstance(legs.get("pe"), dict)]
    if missing_ce or missing_pe:
        raise ValueError(
            f"selected option legs missing: CE={missing_ce}, PE={missing_pe}"
        )

    selected = dict(chain)
    selected["strikes"] = filtered
    summary = {
        "spot": spot,
        "atm_strike": atm[0],
        "ce_strikes": [item[0] for item in ce_selected],
        "pe_strikes": [item[0] for item in pe_selected],
        "ce_contracts": len(ce_selected),
        "pe_contracts": len(pe_selected),
        "total_contracts": len(ce_selected) + len(pe_selected),
        "provider_strike_count_each_side": STRIKES_EACH_SIDE,
        "selection_rule": "CE: 5 below + ATM + 2 above; PE: 2 below + ATM + 5 above",
    }
    if summary["total_contracts"] != TOTAL_CONTRACTS:
        raise ValueError("internal strike selection count invariant failed")
    return selected, summary
