"""Backtests: run one as a job, and read saved results.

Results are written in the engine's own `FundBacktestResult` format under
research/, with the same file naming as `aihf backtest`, so the CLI/TUI and
the web app read each other's results.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from hedge_fund.backtesting import FundBacktestResult, backtest_fund, summarize
from hedge_fund.data.sessions import completed_through
from hedge_fund.fund import FundSpec
from hedge_fund.scorecard import score
from hedge_fund.tui.shared import BACKTEST_DAYS

from app.engine import LiveNotReady, Workspace, runtime_for
from app.jobs import Job, JobError
from app.services import views
from app.services.notes import data_notes
from app.services.names import safe_name


class BacktestError(ValueError):
    pass


class BacktestNotFound(LookupError):
    pass


def resolve_window(start: str | None, end: str | None) -> tuple[str, str]:
    latest = completed_through()
    try:
        end = min(date.fromisoformat(end).isoformat(), latest) if end else latest
        start = (date.fromisoformat(start).isoformat() if start
                 else (date.fromisoformat(end) - timedelta(days=BACKTEST_DAYS)).isoformat())
    except ValueError:
        raise BacktestError("날짜는 YYYY-MM-DD 형식이어야 합니다.") from None
    if start >= end:
        raise BacktestError(f"시작일({start})이 종료일({end})보다 빨라야 합니다.")
    return start, end


def run(ws: Workspace, spec: FundSpec, universe: list[str], start: str, end: str, job: Job) -> dict[str, Any]:
    """The job body: replay the mandate, save the result, return its id."""
    runtime = runtime_for(ws)
    try:
        runtime.check_ready(spec)
    except LiveNotReady as exc:
        raise JobError(str(exc)) from exc
    fund = runtime.backtest_fund(spec)

    def on_valuation(index, total, value):
        job.progress(index + 1, total, dates=value.as_of, nav=value.nav, benchmark_nav=value.benchmark_nav)

    with runtime.data() as data:
        try:
            result = backtest_fund(fund, start, end, data, universe, on_valuation=on_valuation)
        except ValueError as exc:  # no benchmark bars in the window, and the like
            raise JobError(str(exc)) from exc
    return {"backtest_id": save(ws, result).stem}


def save(ws: Workspace, result: FundBacktestResult) -> Path:
    ws.research.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = ws.research / f"{result.fund}-{result.start}-{result.end}-{stamp}.json"
    path.write_text(result.model_dump_json(indent=2))
    return path


def list_results(ws: Workspace) -> list[dict[str, Any]]:
    rows = []
    for path in ws.research.glob("*.json"):
        mtime = path.stat().st_mtime
        summary = summarize(path, mtime)
        if summary is None:
            continue
        summary.pop("path", None)
        rows.append({
            "id": path.stem, **summary,
            "created": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
        })
    return sorted(rows, key=lambda row: row["mtime"], reverse=True)


def latest_by_fund(ws: Workspace) -> dict[str, dict[str, Any]]:
    """Each mandate's most recent result, for the mandate list."""
    latest: dict[str, dict[str, Any]] = {}
    for row in list_results(ws):  # newest first
        latest.setdefault(row["fund"], {
            "id": row["id"], "total": row["total"], "excess": row["excess"], "benchmark": row["benchmark"],
        })
    return latest


def _path(ws: Workspace, backtest_id: str) -> Path:
    safe_name(backtest_id, "백테스트 ID")
    path = ws.research / f"{backtest_id}.json"
    if not path.is_file():
        raise BacktestNotFound(f"백테스트 {backtest_id!r}를 찾을 수 없습니다.")
    return path


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> FundBacktestResult:
    return FundBacktestResult.model_validate_json(Path(path).read_text())


def load(ws: Workspace, backtest_id: str) -> FundBacktestResult:
    path = _path(ws, backtest_id)
    try:
        return _load(str(path), path.stat().st_mtime)
    except ValueError as exc:
        raise BacktestError(f"{path.name}: 결과 파일을 읽을 수 없습니다: {exc}") from exc


def report(ws: Workspace, backtest_id: str) -> dict[str, Any]:
    result = load(ws, backtest_id)
    last = result.records[-1]
    return {
        "id": backtest_id,
        "mode": ws.mode,
        "fund": result.fund,
        "universe": result.universe,
        "benchmark": result.benchmark,
        "start": result.start,
        "end": result.end,
        "rebalance": result.rebalance,
        "capital": result.capital,
        "llm_model": last.llm_model,
        "notes": data_notes(ws.mode, last.decision.spec if last.decision else None, last.llm_model == "demo-heuristic"),
        "metrics": result.metrics.model_dump(),
        "dates": result.dates,
        "nav": result.nav,
        "benchmark_nav": result.benchmark_nav,
        "drawdown": views.drawdown_curve(result.nav),
        "sessions": [views.session_summary(record) for record in result.records],
        "positions": views.positions(last),
        "cash": last.cash,
        "spec": views.spec_summary(result.records[0].decision.spec) if result.records[0].decision else None,
        "scorecard": score(result.records).model_dump(mode="json"),
    }


def session(ws: Workspace, backtest_id: str, session_id: str) -> dict[str, Any]:
    result = load(ws, backtest_id)
    record = next((r for r in result.records if r.session == session_id), None)
    if record is None:
        raise BacktestNotFound(f"세션 {session_id}가 이 백테스트에 없습니다.")
    return views.session_detail(record)


def delete(ws: Workspace, backtest_id: str) -> None:
    _path(ws, backtest_id).unlink()
