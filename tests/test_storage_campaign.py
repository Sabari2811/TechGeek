import importlib

import pytest

from app import storage


def test_campaign_storage_uses_configured_isolated_root(monkeypatch):
    monkeypatch.setenv("QUANTNIFTY_DATA_ROOT", ".quantnifty/campaigns/2026-11-30-paper")
    monkeypatch.setenv("QUANTNIFTY_CAMPAIGN_ID", "2026-11-30-paper")
    loaded = importlib.reload(storage)
    assert loaded.DATA_ROOT.as_posix() == ".quantnifty/campaigns/2026-11-30-paper"
    assert loaded.CAMPAIGN_ID == "2026-11-30-paper"
    assert loaded.LEGACY_DATA_ROOT.as_posix() == ".quantnifty"


@pytest.mark.parametrize("campaign_id", ["../escape", "bad/name", "contains spaces", ""])
def test_campaign_id_rejects_unsafe_values(monkeypatch, campaign_id):
    monkeypatch.setenv("QUANTNIFTY_CAMPAIGN_ID", campaign_id)
    with pytest.raises(ValueError, match="QUANTNIFTY_CAMPAIGN_ID"):
        importlib.reload(storage)
