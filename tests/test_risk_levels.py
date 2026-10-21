import math

import pytest

from app.risk import calculate_stop_target


def test_stop_and_target_are_based_on_executable_entry():
    entry = 205.0
    spot = 24500.0

    stop, target = calculate_stop_target(entry, spot)

    assert stop < entry < target
    assert stop == pytest.approx(max(entry * 0.75, entry - spot * 0.001))
    assert target - entry == pytest.approx((entry - stop) * 1.8)


@pytest.mark.parametrize(
    ("entry", "spot", "reward_risk"),
    [
        (0, 24500, 1.8),
        (-1, 24500, 1.8),
        (200, 0, 1.8),
        (200, 24500, 0),
        (math.nan, 24500, 1.8),
        (200, math.inf, 1.8),
    ],
)
def test_invalid_risk_level_inputs_are_rejected(entry, spot, reward_risk):
    with pytest.raises(ValueError):
        calculate_stop_target(entry, spot, reward_risk)
