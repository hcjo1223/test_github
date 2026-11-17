"""Mandates: saved fund definitions (YAML, the engine's own format)."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from hedge_fund.fund import FundSpec, discover_funds, load_spec, save_spec

from app.engine import Workspace
from app.services import backtests
from app.services.names import InvalidName, safe_name
from app.services.views import spec_summary


class MandateError(ValueError):
    pass


class MandateExists(MandateError):
    pass


class MandateNotFound(LookupError):
    pass


def list_mandates(ws: Workspace) -> list[dict[str, Any]]:
    scores = backtests.latest_by_fund(ws)
    rows = []
    for saved in discover_funds(ws.mandates):
        if saved.spec is None:
            rows.append({"file": saved.path.stem, "name": saved.path.stem, "error": saved.error})
            continue
        rows.append({
            "file": saved.path.stem, **spec_summary(saved.spec), "error": None,
            "last_backtest": scores.get(saved.spec.name),
        })
    return rows


def load(ws: Workspace, name: str) -> FundSpec:
    """Find a mandate by its name, falling back to its file name."""
    safe_name(name, "맨데이트 이름")
    path = ws.mandates / f"{name}.yaml"
    if path.is_file():
        try:
            return load_spec(path)
        except ValueError as exc:
            raise MandateError(str(exc)) from exc
    for saved in discover_funds(ws.mandates):
        if saved.spec is not None and saved.spec.name == name:
            return saved.spec
    raise MandateNotFound(f"맨데이트 {name!r}를 찾을 수 없습니다.")


def create(ws: Workspace, payload: dict[str, Any]) -> FundSpec:
    try:
        spec = FundSpec.model_validate({"schema_version": 2, **payload})
    except ValidationError as exc:
        errors = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise MandateError(errors) from exc
    except ValueError as exc:  # unknown analyst and the like
        raise MandateError(str(exc)) from exc
    try:
        safe_name(spec.name, "맨데이트 이름")
    except InvalidName as exc:
        raise MandateError(str(exc)) from exc
    if spec.is_intraday:
        raise MandateError("웹에서는 daily / weekly / monthly 주기만 지원합니다.")
    if any(saved.spec is not None and saved.spec.name == spec.name for saved in discover_funds(ws.mandates)):
        raise MandateExists(f"맨데이트 {spec.name!r}가 이미 있습니다.")
    try:
        save_spec(spec, ws.mandates)
    except FileExistsError:
        raise MandateExists(f"맨데이트 {spec.name!r}가 이미 있습니다.") from None
    return spec


def delete(ws: Workspace, name: str) -> None:
    safe_name(name, "맨데이트 이름")
    path = ws.mandates / f"{name}.yaml"
    if not path.is_file():
        match = next(
            (saved.path for saved in discover_funds(ws.mandates)
             if saved.spec is not None and saved.spec.name == name), None,
        )
        if match is None:
            raise MandateNotFound(f"맨데이트 {name!r}를 찾을 수 없습니다.")
        path = match
    path.unlink()
