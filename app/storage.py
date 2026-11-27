"""Campaign-scoped local storage paths.

A new campaign gets isolated journals, raw data, audit, reports, learner state,
sync cursors and PAPER kill-switch state. Existing .quantnifty data is never
moved or deleted; it remains available as legacy evidence.
"""
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_ROOT = Path(os.getenv("QUANTNIFTY_DATA_ROOT", ".quantnifty")).expanduser()
CAMPAIGN_ID = os.getenv("QUANTNIFTY_CAMPAIGN_ID", "legacy").strip() or "legacy"
if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", CAMPAIGN_ID):
    raise ValueError("QUANTNIFTY_CAMPAIGN_ID must contain only letters, digits, dot, underscore or hyphen")
LEGACY_DATA_ROOT = Path(".quantnifty")
