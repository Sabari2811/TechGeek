import pytest

from app.strike_selection import select_strategy_option_chain


def make_chain(spot=25000):
    strikes = {}
    for strike in range(24750, 25251, 50):
        strikes[str(strike)] = {
            "ce": {"security_id": f"CE-{strike}", "trading_symbol": f"NIFTY-{strike}-CE"},
            "pe": {"security_id": f"PE-{strike}", "trading_symbol": f"NIFTY-{strike}-PE"},
        }
    return {"underlying_ltp": spot, "expiry": "2026-12-01", "strikes": strikes}


def test_selects_exact_asymmetric_sixteen_contract_universe():
    selected, summary = select_strategy_option_chain(make_chain())
    assert summary["atm_strike"] == 25000
    assert summary["ce_strikes"] == [24750, 24800, 24850, 24900, 24950, 25000, 25050, 25100]
    assert summary["pe_strikes"] == [24900, 24950, 25000, 25050, 25100, 25150, 25200, 25250]
    assert summary["total_contracts"] == 16
    assert sum("ce" in legs for legs in selected["strikes"].values()) == 8
    assert sum("pe" in legs for legs in selected["strikes"].values()) == 8
    assert "pe" not in selected["strikes"]["24750"]
    assert "ce" not in selected["strikes"]["25250"]


def test_nearest_atm_uses_listed_ladder_and_lower_tie_break():
    _, summary = select_strategy_option_chain(make_chain(spot=25025))
    assert summary["atm_strike"] == 25000


def test_fails_closed_when_provider_returns_too_few_strikes():
    chain = make_chain()
    chain["strikes"] = dict(list(chain["strikes"].items())[:8])
    with pytest.raises(ValueError, match="incomplete strike ladder"):
        select_strategy_option_chain(chain)


def test_fails_closed_when_a_selected_option_leg_is_missing():
    chain = make_chain()
    chain["strikes"]["24950"]["ce"] = None
    with pytest.raises(ValueError, match="selected option legs missing"):
        select_strategy_option_chain(chain)
