"""Assemble the engine's inputs for a mode: a data client and staffed funds.

This is the one place demo and live differ. Everything downstream
(`backtest_fund`, `tick`, `score`) is called identically in both.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Iterator

from hedge_fund.data import CachedDataClient, DataClient, FDClient, has_data_credential
from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.fund import Fund, FundSpec
from hedge_fund.llm import PromptCache, provider_for
from hedge_fund.signals import ALPHA_MODEL_REGISTRY, LLMAgent
from hedge_fund.tui.keys import missing_key

from app import config
from app.engine.demo import DEMO_MODEL, DemoDataClient, DemoLLM
from app.engine.free.client import FreeDataClient, valid_contact
from app.engine.workspace import Workspace

# A new demo fund starts this far in the past, so its sessions can be
# stepped through at once instead of one per real day.
DEMO_BACKDATE_DAYS = 90


class LiveNotReady(RuntimeError):
    """Live mode is missing a credential the requested run needs."""


def uses_llm(spec: FundSpec) -> bool:
    return any(
        issubclass(ALPHA_MODEL_REGISTRY[model.name], LLMAgent)
        for strategy in spec.strategies for model in strategy.models
    )


@dataclass(frozen=True)
class Runtime:
    workspace: Workspace

    @property
    def mode(self) -> config.Mode:
        return self.workspace.mode

    @property
    def demo_llm(self) -> bool:
        """Whether the investor agents are the rule-based stand-in. Always in
        demo mode; in free mode only while the selected model has no key, so
        free data can be used with no paid service at all."""
        if self.mode == "demo":
            return True
        return self.mode == "free" and missing_key(provider_for(config.get_model()) or "Anthropic") is not None

    @property
    def llm_model(self) -> str:
        return DEMO_MODEL if self.demo_llm else config.get_model()

    def check_ready(self, spec: FundSpec) -> None:
        """Raise LiveNotReady, naming what is missing, before any work starts."""
        if self.mode == "demo":
            return
        if self.mode == "free":
            if not valid_contact(config.get_contact()):
                raise LiveNotReady("무료 데이터 모드에는 SEC가 요구하는 연락처(이메일)가 필요합니다. 설정에서 입력하세요.")
            return
        if not has_data_credential():
            raise LiveNotReady("FINANCIAL_DATASETS_API_KEY가 없습니다. 설정에서 등록하거나 데모 모드로 전환하세요.")
        if uses_llm(spec):
            missing = missing_key(provider_for(config.get_model()) or "Anthropic")
            if missing:
                raise LiveNotReady(
                    f"선택한 모델({config.get_model()})에 필요한 {missing}가 없습니다. 설정에서 등록하세요."
                )

    @contextmanager
    def data(self) -> Iterator[DataClient]:
        """The data client for an engine run. Every run happens inside this
        block, so it also pins HEDGE_FUND_LLM_MODEL: the engine stamps that
        variable on each SessionRecord, and a demo record must say it was
        reasoned by the demo heuristic, not by the model picked for live."""
        previous = os.environ.get("HEDGE_FUND_LLM_MODEL")
        os.environ["HEDGE_FUND_LLM_MODEL"] = self.llm_model
        try:
            if self.mode == "demo":
                yield DemoDataClient()
            elif self.mode == "free":
                yield FreeDataClient(config.get_contact(), self.workspace.cache / "free")
            else:
                with FDClient() as raw:
                    yield CachedDataClient(raw)
        finally:
            if previous is None:
                os.environ.pop("HEDGE_FUND_LLM_MODEL", None)
            else:
                os.environ["HEDGE_FUND_LLM_MODEL"] = previous

    def backtest_fund(self, spec: FundSpec) -> Fund:
        """Staff a fund for a backtest. Live backtests blind the agents'
        prompts, as the aihf CLI does: the LLM may remember what a named
        company did over the window."""
        if self.demo_llm:
            return self._demo_fund(spec)
        return Fund(spec, blind=True)

    def paper_fund(self, spec: FundSpec) -> Fund:
        if self.demo_llm:
            return self._demo_fund(spec)
        return Fund(spec)

    def first_session_clock(self) -> Callable[[], datetime] | None:
        """The clock a fund's first tick runs on. None means the real one."""
        if self.mode != "demo":
            return None
        return lambda: datetime.now(NEW_YORK) - timedelta(days=DEMO_BACKDATE_DAYS)

    def _demo_fund(self, spec: FundSpec) -> Fund:
        cache = PromptCache(self.workspace.cache / "llm")
        staff = {}
        for strategy in spec.strategies:
            models = []
            for model in strategy.models:
                cls = ALPHA_MODEL_REGISTRY[model.name]
                if issubclass(cls, LLMAgent):
                    models.append(cls(llm=DemoLLM(), cache=cache, **model.params))
                else:
                    models.append(cls(**model.params))
            staff[strategy.name] = models
        return Fund(spec, models=staff)


def runtime_for(workspace: Workspace) -> Runtime:
    return Runtime(workspace)
