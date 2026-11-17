"""What a mandate can be built from: analysts, library strategies, models."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from hedge_fund.fund import load_strategy
from hedge_fund.llm import env_var_for, is_supported, load_api_models
from hedge_fund.signals import ALPHA_MODEL_REGISTRY, LLMAgent, get_horizon_days, get_investment_approach
from hedge_fund.tui.shared import (
    BACKTEST_DAYS,
    DEFAULT_CAPITAL,
    DEFAULT_RISK,
    DISPLAY_NAMES,
    SHORT_NAMES,
    STRATEGY_DIR,
    UNIVERSE_PRESETS,
    strategy_description,
    strategy_kind,
)


@lru_cache(maxsize=1)
def _static() -> dict[str, Any]:
    analysts = [
        {
            "name": name,
            "display_name": DISPLAY_NAMES.get(name, name),
            "short_name": SHORT_NAMES.get(name, name),
            "kind": "llm" if issubclass(cls, LLMAgent) else "quant",
            "approach": get_investment_approach(name),
            "horizon_days": get_horizon_days(name),
        }
        for name, cls in ALPHA_MODEL_REGISTRY.items()
    ]
    strategies = []
    for path in sorted(STRATEGY_DIR.glob("*.yaml")):
        strategy = load_strategy(path)
        strategies.append({
            **strategy.model_dump(mode="json"),
            "title": strategy.title,
            "kind": strategy_kind(strategy),
            "description": strategy_description(strategy),
        })
    return {
        "analysts": analysts,
        "strategies": strategies,
        "universe_presets": UNIVERSE_PRESETS,
        "defaults": {
            "risk": DEFAULT_RISK, "capital": DEFAULT_CAPITAL, "backtest_days": BACKTEST_DAYS,
            "rebalance": "weekly", "benchmark": "SPY",
        },
    }


def catalog() -> dict[str, Any]:
    models = [
        {
            "display_name": display, "model": model_id, "provider": provider,
            "supported": is_supported(provider),
            "key_set": bool(os.environ.get(env_var_for(provider) or "")),
        }
        for display, model_id, provider in load_api_models()
    ]
    return {**_static(), "models": models}
