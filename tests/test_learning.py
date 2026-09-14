from datetime import date

from app.learning import IncrementalLearner
from app.models import TradeSignal


def signal(probability=0.7):
    return TradeSignal(
        action="BUY", option_type="CE", strike=25000, security_id="1", symbol="NIFTY",
        entry=100, stop=90, target=118, quantity=75, probability=probability,
        fair_value=110, expected_value=8, net_expected_value=7,
        reason="test", score=70,
        score_components={"valuation": 20, "probability": 15, "volatility": 10},
    )


def test_learning_persists_and_records(tmp_path):
    learner = IncrementalLearner(str(tmp_path / "state.json"))
    learner.record(signal(), 100)
    assert learner.state.pending == [learner.state.pending[0]]
    assert learner.summary()["pending"] == 1

    restored = IncrementalLearner(str(tmp_path / "state.json"))
    assert restored.summary()["pending"] == 1


def test_learning_updates_only_after_day_changes(tmp_path):
    learner = IncrementalLearner(str(tmp_path / "state.json"))
    learner.record(signal(), 100)
    assert not learner.learn_if_new_day(date.today().isoformat())
    assert learner.summary()["outcomes"] == 0

    assert learner.learn_if_new_day("2099-01-01")
    summary = learner.summary()
    assert summary["outcomes"] == 1
    assert summary["wins"] == 1
    assert 0.5 <= min(summary["weights"].values()) <= 1.5


def test_probability_calibration_is_bounded(tmp_path):
    learner = IncrementalLearner(str(tmp_path / "state.json"))
    learner.state.probability_bias = 0.05
    assert learner.probability(0.90) == 0.90
    learner.state.probability_bias = -0.05
    assert learner.probability(0.10) == 0.10
