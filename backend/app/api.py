"""HTTP routes. Thin: validate, call a service, map its errors to statuses."""

from __future__ import annotations

from importlib.metadata import version
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app import config
from app.engine import Workspace, workspace_for
from app.jobs import queue
from app.services import backtests, catalog, funds, mandates, settings
from app.services.names import InvalidName, clean_universe

router = APIRouter(prefix="/api")

NOT_FOUND = (mandates.MandateNotFound, backtests.BacktestNotFound, funds.FundNotFound)
CONFLICT = (mandates.MandateExists, funds.FundExists)
BAD_REQUEST = (InvalidName, mandates.MandateError, backtests.BacktestError, funds.FundError,
               settings.SettingsError)


def ws() -> Workspace:
    return workspace_for()


def http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NOT_FOUND):
        return HTTPException(404, str(exc))
    if isinstance(exc, CONFLICT):
        return HTTPException(409, str(exc))
    if isinstance(exc, BAD_REQUEST):
        return HTTPException(422 if isinstance(exc, (InvalidName, mandates.MandateError)) else 400, str(exc))
    raise exc


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (*NOT_FOUND, *CONFLICT, *BAD_REQUEST) as exc:
        raise http_error(exc) from exc


# ---- status & settings ------------------------------------------------------

@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": config.APP_VERSION, "aihf_version": version("aihf"),
            "mode": config.get_mode()}


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return settings.view()


class SettingsUpdate(BaseModel):
    mode: str | None = None
    model: str | None = None


@router.put("/settings")
def put_settings(body: SettingsUpdate) -> dict[str, Any]:
    return call(settings.update, body.mode, body.model)


class Credential(BaseModel):
    env_var: str
    value: str = Field(min_length=1, max_length=500)


@router.put("/settings/credentials")
def put_credential(body: Credential) -> dict[str, Any]:
    return call(settings.save_credential, body.env_var, body.value)


@router.get("/catalog")
def get_catalog() -> dict[str, Any]:
    return catalog.catalog()


# ---- mandates ---------------------------------------------------------------

@router.get("/mandates")
def list_mandates() -> list[dict[str, Any]]:
    return mandates.list_mandates(ws())


@router.get("/mandates/{name}")
def get_mandate(name: str) -> dict[str, Any]:
    return call(mandates.load, ws(), name).model_dump(mode="json")


@router.post("/mandates", status_code=201)
def create_mandate(body: dict[str, Any]) -> dict[str, Any]:
    return call(mandates.create, ws(), body).model_dump(mode="json")


@router.delete("/mandates/{name}", status_code=204)
def delete_mandate(name: str) -> Response:
    call(mandates.delete, ws(), name)
    return Response(status_code=204)


# ---- backtests --------------------------------------------------------------

class BacktestRequest(BaseModel):
    mandate: str
    universe: list[str]
    start: str | None = None
    end: str | None = None


@router.post("/backtests", status_code=202)
def start_backtest(body: BacktestRequest) -> dict[str, Any]:
    workspace = ws()
    spec = call(mandates.load, workspace, body.mandate)
    universe = call(clean_universe, body.universe)
    start, end = call(backtests.resolve_window, body.start, body.end)
    job = queue.submit(
        "backtest", f"{spec.name} · {', '.join(universe)} · {start} → {end}",
        lambda job: backtests.run(workspace, spec, universe, start, end, job),
    )
    return {"job_id": job.id}


@router.get("/backtests")
def list_backtests() -> list[dict[str, Any]]:
    return backtests.list_results(ws())


@router.get("/backtests/{backtest_id}")
def get_backtest(backtest_id: str) -> dict[str, Any]:
    return call(backtests.report, ws(), backtest_id)


@router.get("/backtests/{backtest_id}/sessions/{session}")
def get_backtest_session(backtest_id: str, session: str) -> dict[str, Any]:
    return call(backtests.session, ws(), backtest_id, session)


@router.delete("/backtests/{backtest_id}", status_code=204)
def delete_backtest(backtest_id: str) -> Response:
    call(backtests.delete, ws(), backtest_id)
    return Response(status_code=204)


# ---- paper funds ------------------------------------------------------------

class FundCreate(BaseModel):
    name: str
    mandate: str
    universe: list[str]


@router.get("/funds")
def list_funds() -> list[dict[str, Any]]:
    return funds.list_funds(ws())


@router.post("/funds", status_code=201)
def create_fund(body: FundCreate) -> dict[str, Any]:
    workspace = ws()
    spec = call(mandates.load, workspace, body.mandate)
    universe = call(clean_universe, body.universe)
    return call(funds.create, workspace, body.name, spec, universe)


@router.get("/funds/{name}")
def get_fund(name: str) -> dict[str, Any]:
    return call(funds.detail, ws(), name)


@router.get("/funds/{name}/preview")
def preview_fund(name: str) -> dict[str, Any]:
    return call(funds.preview, ws(), name)


class TickRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=funds.MAX_TICKS)
    session: str | None = None


@router.post("/funds/{name}/tick", status_code=202)
def tick_fund(name: str, body: TickRequest) -> dict[str, Any]:
    workspace = ws()
    call(funds.detail, workspace, name)  # 404 before queueing
    job = queue.submit(
        "tick", f"{name} · {body.count}세션",
        lambda job: funds.run_ticks(workspace, name, body.count, body.session, job),
    )
    return {"job_id": job.id}


class HaltRequest(BaseModel):
    reason: str = Field(max_length=300)


@router.post("/funds/{name}/halt")
def halt_fund(name: str, body: HaltRequest) -> dict[str, Any]:
    return call(funds.halt, ws(), name, body.reason)


@router.post("/funds/{name}/resume")
def resume_fund(name: str) -> dict[str, Any]:
    return call(funds.resume, ws(), name)


@router.get("/funds/{name}/sessions/{session}")
def get_fund_session(name: str, session: str) -> dict[str, Any]:
    return call(funds.session, ws(), name, session)


@router.get("/funds/{name}/scorecard")
def get_fund_scorecard(name: str) -> dict[str, Any]:
    return call(funds.scorecard, ws(), name)


# ---- jobs -------------------------------------------------------------------

@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다. 서버가 재시작되었을 수 있습니다.")
    return job.view()
