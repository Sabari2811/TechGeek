import pytest

from app.risk import cap_quantity_to_lots


@pytest.mark.parametrize(
    ("raw_quantity", "lot_size", "max_lots", "expected"),
    [
        (500, 65, 1, 65),
        (130, 65, 1, 65),
        (64, 65, 1, 0),
        (0, 65, 1, 0),
        (260, 65, 2, 130),
    ],
)
def test_quantity_is_rounded_down_and_capped(raw_quantity, lot_size, max_lots, expected):
    assert cap_quantity_to_lots(raw_quantity, lot_size, max_lots) == expected


@pytest.mark.parametrize(
    ("raw_quantity", "lot_size", "max_lots"),
    [(-1, 65, 1), (100, 0, 1), (100, 65, 0), (1.5, 65, 1)],
)
def test_invalid_lot_cap_inputs_are_rejected(raw_quantity, lot_size, max_lots):
    with pytest.raises(ValueError):
        cap_quantity_to_lots(raw_quantity, lot_size, max_lots)


from app.risk import daily_risk_check


def test_daily_risk_guard_blocks_trade_that_exceeds_remaining_loss_budget():
    allowed, planned, remaining = daily_risk_check(468.30, 445.00515, 65, -18681.0, 20000.0)
    assert planned == pytest.approx(1514.164)
    assert remaining == pytest.approx(1319.0)
    assert allowed is False


def test_daily_risk_guard_allows_trade_within_remaining_loss_budget():
    allowed, planned, remaining = daily_risk_check(468.30, 445.00515, 50, -10000.0, 20000.0)
    assert planned == pytest.approx(1164.7575)
    assert remaining == pytest.approx(10000.0)
    assert allowed is True


@pytest.mark.parametrize(
    ("entry", "stop", "quantity", "realized", "limit"),
    [(0, 1, 1, 0, 20000), (10, 10, 1, 0, 20000),
     (10, 9, 0, 0, 20000), (10, 9, 1, 0, 0)],
)
def test_daily_risk_guard_rejects_invalid_inputs(entry, stop, quantity, realized, limit):
    with pytest.raises(ValueError):
        daily_risk_check(entry, stop, quantity, realized, limit)
