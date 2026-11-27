import asyncio
from types import SimpleNamespace

import pytest

from app import trader


def test_campaign_refuses_non_paper_mode_before_startup(monkeypatch):
    monkeypatch.setattr(
        trader,
        "CONFIG",
        SimpleNamespace(mode="LIVE", live_enabled=lambda: False),
    )
    with pytest.raises(RuntimeError, match="PAPER-only"):
        asyncio.run(trader.run())
