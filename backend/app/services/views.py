"""Turn the engine's records into what the screens show.

Nothing here computes performance: metrics and scores come from the
engine. This module only summarizes, flattens and drops repetition.
"""

from __future__ import annotations

from typing import Any

from hedge_fund.pipeline import CycleRecord, DecisionRecord, SessionRecord


def drawdown_curve(nav: list[float]) -> list[float]:
    """Fall from the running peak at every point, as a non-positive fraction."""
    curve, peak = [], float("-inf")
    for value in nav:
        peak = max(peak, value)
        curve.append(round(value / peak - 1, 6) if peak > 0 else 0.0)
    return curve


def session_summary(record: SessionRecord) -> dict[str, Any]:
    executed = record.executed
    decision = record.decision
    return {
        "session": record.session,
        "nav": record.nav,
        "cash": record.cash,
        "rebalance": record.rebalance,
        "executed": None if executed is None else {
            "as_of": executed.as_of,
            "n_orders": len(executed.orders),
            "traded_notional": round(executed.traded_notional, 2),
            "trading_cost": round(executed.trading_cost, 2),
        },
        "decided": None if decision is None else {
            "n_signals": sum(len(strategy.signals) for strategy in decision.strategies),
            "n_clamps": len(decision.clamps),
            "stopped_out": decision.is_stopped_out,
            "halved": decision.is_halved,
        },
    }


def positions(record: SessionRecord) -> list[dict[str, Any]]:
    rows = []
    for ticker, shares in sorted(record.positions.items()):
        if shares == 0:
            continue
        mark = record.marks.get(ticker)
        value = shares * mark if mark is not None else None
        rows.append({
            "ticker": ticker, "shares": shares, "mark": mark, "value": value,
            "weight": value / record.nav if value is not None and record.nav else None,
        })
    return sorted(rows, key=lambda row: -(abs(row["value"]) if row["value"] is not None else 0))


def decision_view(decision: DecisionRecord) -> dict[str, Any]:
    """A decision without its embedded copy of the mandate."""
    data = decision.model_dump(mode="json", exclude={"spec"})
    data["stopped_out"] = decision.is_stopped_out
    data["halved"] = decision.is_halved
    return data


def cycle_view(cycle: CycleRecord) -> dict[str, Any]:
    data = cycle.model_dump(
        mode="json", exclude={"spec", "original_assessment", "refreshed_assessment"},
    )
    data.update(
        traded_notional=round(cycle.traded_notional, 2),
        trading_cost=round(cycle.trading_cost, 2),
        slippage=round(cycle.slippage, 2),
        commission=round(cycle.commission, 2),
    )
    return data


def session_detail(record: SessionRecord) -> dict[str, Any]:
    data = record.model_dump(mode="json", exclude={"executed", "decision"})
    data["executed"] = cycle_view(record.executed) if record.executed is not None else None
    data["decision"] = decision_view(record.decision) if record.decision is not None else None
    data["positions_view"] = positions(record)
    return data


def spec_summary(spec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "capital": spec.capital,
        "rebalance": spec.rebalance,
        "cadence_label": spec.cadence_label,
        "benchmark": spec.benchmark,
        "strategies": [
            {
                "name": strategy.name, "title": strategy.title, "mode": strategy.blend.mode,
                "weight": strategy.weight, "models": [model.name for model in strategy.models],
            }
            for strategy in spec.strategies
        ],
    }
