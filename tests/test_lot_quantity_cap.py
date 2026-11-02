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
