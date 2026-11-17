"""Where the web app keeps its state, and the two settings it owns.

Everything else (mandates, ledgers, results, API keys) is stored in the aihf
engine's own formats. The web layer only adds `web-settings.json`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from hedge_fund import paths
from hedge_fund.data import has_data_credential
from hedge_fund.llm import DEFAULT_MODEL

Mode = Literal["demo", "free", "live"]
APP_VERSION = "0.1.0"
SETTINGS_FILE = "web-settings.json"


def home() -> Path:
    """Root of all state. `AIHF_WEB_HOME` overrides the engine's ~/.hedge-fund."""
    override = os.environ.get("AIHF_WEB_HOME")
    return Path(override) if override else paths.USER_DIR


def _read() -> dict:
    try:
        data = json.loads((home() / SETTINGS_FILE).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data: dict) -> None:
    home().mkdir(parents=True, exist_ok=True)
    paths.write_atomic(home() / SETTINGS_FILE, json.dumps(data, indent=2))


def get_mode() -> Mode:
    """The saved mode; without one, live only when a data key exists."""
    saved = _read().get("mode")
    if saved in ("demo", "free", "live"):
        return saved
    return "live" if has_data_credential() else "demo"


def set_mode(mode: Mode) -> None:
    _write({**_read(), "mode": mode})


def get_model() -> str:
    return _read().get("model") or os.environ.get("HEDGE_FUND_LLM_MODEL") or DEFAULT_MODEL


def set_model(model: str) -> None:
    _write({**_read(), "model": model})
    os.environ["HEDGE_FUND_LLM_MODEL"] = model


def get_contact() -> str:
    """The contact SEC EDGAR requires of automated clients (free mode)."""
    return _read().get("contact") or os.environ.get("AIHF_WEB_CONTACT", "")


def set_contact(contact: str) -> None:
    _write({**_read(), "contact": contact})
