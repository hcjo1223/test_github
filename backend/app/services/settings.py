"""Mode, model and API keys."""

from __future__ import annotations

import os
from typing import Any

from hedge_fund.data import has_data_credential
from hedge_fund.data.client import API_KEY_ENV
from hedge_fund.llm import PROVIDER_ENV_VARS, load_api_models, provider_for
from hedge_fund.tui import keys

from app import config
from app.engine.free.client import valid_contact

# The only variables the API will write. Anything else is refused.
CREDENTIALS: dict[str, str] = {
    API_KEY_ENV: "Financial Datasets (시세·재무 데이터)",
    **{env: f"{provider} (LLM)" for provider, env in PROVIDER_ENV_VARS.items()},
}


class SettingsError(ValueError):
    pass


def startup() -> None:
    """Load saved keys and the selected model into the environment."""
    keys.apply_credentials()
    os.environ.setdefault("HEDGE_FUND_LLM_MODEL", config.get_model())


def llm_key_missing() -> str | None:
    """The env var the selected model needs, when it is not set."""
    return keys.missing_key(provider_for(config.get_model()) or "Anthropic")


def view() -> dict[str, Any]:
    blockers = [] if has_data_credential() else [f"{API_KEY_ENV}가 없습니다."]
    missing = llm_key_missing()
    contact = config.get_contact()
    return {
        "mode": config.get_mode(),
        "model": config.get_model(),
        "live_ready": not blockers,
        "live_blockers": blockers,
        "free_ready": valid_contact(contact),
        "free_blockers": [] if valid_contact(contact) else ["SEC가 요구하는 연락처(이메일)를 입력하세요."],
        "contact": contact or None,
        "free_uses_demo_llm": llm_key_missing() is not None,
        "llm_warning": f"선택한 모델에 필요한 {missing}가 없습니다. LLM 에이전트가 포함된 실행은 거부됩니다." if missing else None,
        "credentials": [
            {
                "env_var": env, "label": label, "set": bool(os.environ.get(env)),
                "masked": keys.masked(os.environ[env]) if os.environ.get(env) else None,
            }
            for env, label in CREDENTIALS.items()
        ],
    }


def update(mode: str | None, model: str | None, contact: str | None = None) -> dict[str, Any]:
    if contact is not None:
        contact = contact.strip()
        if contact and not valid_contact(contact):
            raise SettingsError("연락처에 이메일 주소가 들어 있어야 합니다. 예: 이름 name@example.com")
        config.set_contact(contact)
    if model is not None:
        known = {model_id for _, model_id, _ in load_api_models()}
        if model not in known:
            raise SettingsError(f"알 수 없는 모델: {model}")
        config.set_model(model)
    if mode is not None:
        if mode not in ("demo", "free", "live"):
            raise SettingsError("mode는 demo, free, live 중 하나여야 합니다.")
        if mode == "free" and not valid_contact(config.get_contact()):
            raise SettingsError("free 모드에는 SEC가 요구하는 연락처(이메일)가 필요합니다. 먼저 연락처를 입력하세요.")
        if mode == "live" and not has_data_credential():
            raise SettingsError(f"live 모드에는 {API_KEY_ENV}가 필요합니다. 먼저 키를 등록하세요.")
        config.set_mode(mode)
    return view()


def save_credential(env_var: str, value: str) -> dict[str, Any]:
    if env_var not in CREDENTIALS:
        raise SettingsError(f"등록할 수 없는 변수: {env_var}")
    value = value.strip()
    if not value or any(ch in value for ch in "\r\n"):
        raise SettingsError("키 값이 비어 있거나 줄바꿈을 포함합니다.")
    keys.save_credential(env_var, value)
    return view()
