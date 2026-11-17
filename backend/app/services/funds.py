"""Paper funds: deploy a mandate, advance it session by session, read its ledger."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hedge_fund.fund import FundSpec
from hedge_fund.paper import (
    Ledger,
    LedgerError,
    NothingDue,
    deploy,
    list_deployed,
    load_deployed,
    next_session,
    tick,
)
from hedge_fund.pipeline import FundHalted, is_rebalance_session
from hedge_fund.scorecard import score

from app.engine import LiveNotReady, Workspace, runtime_for
from app.jobs import Job, JobError
from app.services import views
from app.services.names import safe_name

MAX_TICKS = 60
EVENTS_SHOWN = 50


class FundError(ValueError):
    pass


class FundExists(FundError):
    pass


class FundNotFound(LookupError):
    pass


def _directory(ws: Workspace, name: str) -> Path:
    safe_name(name, "펀드 이름")
    directory = ws.paper / name
    if not (directory / "fund.yaml").is_file():
        raise FundNotFound(f"페이퍼 펀드 {name!r}를 찾을 수 없습니다.")
    return directory


def _summary(directory: Path) -> dict[str, Any]:
    try:
        deployed = load_deployed(directory)
    except ValueError as exc:
        return {"name": directory.name, "error": str(exc)}
    ledger = Ledger(directory)
    sessions = ledger.sessions()
    latest = ledger.read(sessions[-1]) if sessions else None
    capital = deployed.spec.capital
    return {
        "name": deployed.name,
        "error": None,
        "mandate": deployed.spec.name,
        "universe": deployed.universe,
        "cadence": deployed.spec.cadence_label,
        "intraday": deployed.spec.is_intraday,
        "created": deployed.created,
        "capital": capital,
        "n_sessions": len(sessions),
        "last_session": latest.session if latest else None,
        "nav": latest.nav if latest else capital,
        "return_pct": latest.nav / capital - 1 if latest else 0.0,
        "halted": ledger.halted(),
    }


def list_funds(ws: Workspace) -> list[dict[str, Any]]:
    return [_summary(directory) for directory in list_deployed(ws.paper)]


def create(ws: Workspace, name: str, spec: FundSpec, universe: list[str]) -> dict[str, Any]:
    safe_name(name, "펀드 이름")
    if spec.is_intraday:
        raise FundError("웹에서는 분 단위 펀드를 배치할 수 없습니다.")
    try:
        directory = deploy(name, spec, universe, root=ws.paper)
    except FileExistsError:
        raise FundExists(f"페이퍼 펀드 {name!r}가 이미 있습니다.") from None
    except ValueError as exc:
        raise FundError(str(exc)) from exc
    return _summary(directory)


def detail(ws: Workspace, name: str) -> dict[str, Any]:
    directory = _directory(ws, name)
    deployed = load_deployed(directory)
    ledger = Ledger(directory)
    try:
        records = ledger.records()
    except LedgerError as exc:
        raise FundError(str(exc)) from exc
    capital = deployed.spec.capital
    nav = [record.nav for record in records]
    base = records[0].benchmark_close if records else None
    latest = records[-1] if records else None
    return {
        **_summary(directory),
        "mode": ws.mode,
        "spec": views.spec_summary(deployed.spec),
        "risk": deployed.spec.risk.model_dump(mode="json", exclude_none=True),
        "benchmark": deployed.spec.benchmark,
        "dates": [record.session for record in records],
        "nav_series": nav,
        "benchmark_nav": [capital * record.benchmark_close / base for record in records],
        "drawdown": views.drawdown_curve(nav),
        "sessions": [views.session_summary(record) for record in records],
        "positions": views.positions(latest) if latest else [],
        "cash": latest.cash if latest else capital,
        "pending": views.decision_view(latest.decision) if latest and latest.decision else None,
        "llm_model": latest.llm_model if latest else None,
        "events": list(reversed(ledger.events()[-EVENTS_SHOWN:])),
    }


def preview(ws: Workspace, name: str) -> dict[str, Any]:
    """What running the fund now would do: the session due, and the pending
    decision that session would execute. Reads the benchmark's sessions, so
    in live mode this is a data call."""
    directory = _directory(ws, name)
    deployed = load_deployed(directory)
    spec = deployed.spec
    runtime = runtime_for(ws)
    ledger = Ledger(directory)
    halted = ledger.halted()
    blocked = None
    if spec.is_intraday:
        blocked = "분 단위 펀드는 웹에서 실행할 수 없습니다. `aihf paper run`을 사용하세요."
    elif halted:
        blocked = f"정지됨: {halted}"
    else:
        try:
            runtime.check_ready(spec)
        except LiveNotReady as exc:
            blocked = str(exc)
    if blocked:
        return {"due": None, "reason": blocked, "pending": None, "rebalance": False, "halted": halted}
    try:
        state = ledger.replay(spec.capital)
    except LedgerError as exc:
        raise FundError(str(exc)) from exc
    clock = runtime.first_session_clock() if state.last_session is None else None
    with runtime.data() as data:
        due = next_session(data, spec, state.last_session, now=clock)
    return {
        "due": due,
        "reason": None if due else "아직 실행할 완료 세션이 없습니다. 다음 거래일 종가 이후에 다시 시도하세요.",
        "pending": views.decision_view(state.pending) if state.pending is not None else None,
        "rebalance": bool(due) and is_rebalance_session(due, state.last_session, spec.rebalance),
        "halted": halted,
    }


def run_ticks(ws: Workspace, name: str, count: int, session: str | None, job: Job) -> dict[str, Any]:
    """The job body: advance the fund by up to *count* sessions, in order.
    Stops early, without failing, when nothing more is due."""
    directory = _directory(ws, name)
    deployed = load_deployed(directory)
    spec = deployed.spec
    runtime = runtime_for(ws)
    if spec.is_intraday:
        raise JobError("분 단위 펀드는 웹에서 실행할 수 없습니다.")
    try:
        runtime.check_ready(spec)
    except LiveNotReady as exc:
        raise JobError(str(exc)) from exc

    ran: list[str] = []
    stopped = None
    job.progress(0, count)
    with runtime.data() as data:
        for index in range(count):
            first = not Ledger(directory).sessions()
            try:
                record = tick(
                    directory, data,
                    session=session if index == 0 else None,
                    build_fund=runtime.paper_fund,
                    now=runtime.first_session_clock() if first else None,
                )
            except NothingDue as exc:
                stopped = str(exc)
                break
            except FundHalted as exc:
                raise JobError(str(exc)) from exc
            except ValueError as exc:
                if not ran:
                    raise JobError(str(exc)) from exc
                stopped = str(exc)
                break
            ran.append(record.session)
            job.progress(index + 1, count, dates=record.session, nav=record.nav)
    if not ran and stopped:
        raise JobError(stopped)
    return {"fund": name, "sessions": ran, "stopped_reason": stopped}


def halt(ws: Workspace, name: str, reason: str) -> dict[str, Any]:
    reason = reason.strip()
    if not reason:
        raise FundError("정지 사유를 입력하세요.")
    directory = _directory(ws, name)
    Ledger(directory).halt(reason)
    return _summary(directory)


def resume(ws: Workspace, name: str) -> dict[str, Any]:
    directory = _directory(ws, name)
    Ledger(directory).resume()
    return _summary(directory)


def session(ws: Workspace, name: str, session_id: str) -> dict[str, Any]:
    ledger = Ledger(_directory(ws, name))
    if session_id not in ledger.sessions():
        raise FundNotFound(f"세션 {session_id}가 이 펀드의 원장에 없습니다.")
    return views.session_detail(ledger.read(session_id))


def scorecard(ws: Workspace, name: str) -> dict[str, Any]:
    records = Ledger(_directory(ws, name)).records()
    if not records:
        raise FundNotFound("아직 기록된 세션이 없어 성적표를 만들 수 없습니다.")
    return score(records).model_dump(mode="json")
