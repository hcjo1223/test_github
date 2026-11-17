"""Demo mode: synthetic market data and a rule-based stand-in for the LLM.

Lets the whole product run with no API keys. Everything here is
deterministic: a ticker always gets the same prices, filings and earnings,
so two runs of the same backtest agree and the engine's caches stay valid.

The data is noise with a drift. It has no built-in edge, so a demo return
says nothing about a strategy; it only shows how the engine behaves.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

import numpy as np

from hedge_fund.data.models import (
    CompanyFacts,
    Earnings,
    EarningsData,
    EarningsRecord,
    FinancialMetrics,
    Price,
    PriceSnapshot,
)
from hedge_fund.data.sessions import completed_through

DEMO_MODEL = "demo-heuristic"

_EPOCH = date(2012, 1, 2)          # a Monday; every series starts here
_HORIZON = date(2040, 12, 31)      # series are generated to here, then cut at "today"
_FILING_LAG_DAYS = 35              # metrics become public this long after quarter end
_EARNINGS_LAG_DAYS = 30            # the 8-K lands a little before the 10-Q

_SECTORS = [
    "Technology", "Healthcare", "Financials", "Energy", "Consumer Discretionary",
    "Consumer Staples", "Industrials", "Communication Services", "Utilities", "Materials",
]
_KNOWN_SECTORS = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "GOOGL": "Communication Services", "META": "Communication Services",
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "JPM": "Financials", "UNH": "Healthcare", "XOM": "Energy",
}
# Index-like tickers move with the market factor alone.
_INDEX_TICKERS = {"SPY", "QQQ", "IWM", "DIA", "VTI", "VOO"}


def _seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode()).digest()
    return int.from_bytes(digest[:8], "big")


@lru_cache(maxsize=1)
def _weekdays() -> tuple[date, ...]:
    days = []
    day = _EPOCH
    while day <= _HORIZON:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


@lru_cache(maxsize=1)
def _market_returns() -> np.ndarray:
    rng = np.random.default_rng(_seed("market"))
    return rng.normal(0.0004, 0.009, len(_weekdays()))


@lru_cache(maxsize=512)
def _series(ticker: str) -> tuple[np.ndarray, np.ndarray]:
    """(closes, volumes) for every weekday from the epoch to the horizon."""
    rng = np.random.default_rng(_seed("prices", ticker))
    market = _market_returns()
    if ticker in _INDEX_TICKERS:
        beta, drift, sigma = 1.0, 0.0, 0.001
    else:
        beta = rng.uniform(0.6, 1.5)
        drift = rng.uniform(-0.0002, 0.0005)
        sigma = rng.uniform(0.008, 0.022)
    returns = beta * market + drift + rng.normal(0.0, sigma, len(market))
    start = rng.uniform(20.0, 300.0)
    closes = start * np.exp(np.cumsum(returns))
    volumes = rng.uniform(0.6, 1.4, len(market)) * rng.uniform(2e6, 6e7)
    return closes, volumes


def _quarter_ends() -> list[date]:
    ends = []
    for year in range(_EPOCH.year, _HORIZON.year + 1):
        ends += [date(year, 3, 31), date(year, 6, 30), date(year, 9, 30), date(year, 12, 31)]
    return ends


_QUARTERS = _quarter_ends()


@lru_cache(maxsize=1)
def _ordinals() -> np.ndarray:
    return np.array([day.toordinal() for day in _weekdays()])


def _close_on(ticker: str, day: date) -> float:
    """The last close on or before *day*."""
    index = int(np.searchsorted(_ordinals(), day.toordinal(), side="right")) - 1
    return float(_series(ticker)[0][max(index, 0)])


@lru_cache(maxsize=512)
def _fundamentals(ticker: str) -> tuple[FinancialMetrics, ...]:
    """One ttm row per quarter, oldest first, each stamped with its filing date."""
    rng = np.random.default_rng(_seed("fundamentals", ticker))
    roe = rng.uniform(0.04, 0.34)
    gross = rng.uniform(0.22, 0.72)
    net = rng.uniform(0.03, 0.28)
    debt = rng.uniform(0.05, 1.9)
    current = rng.uniform(0.8, 3.0)
    growth = rng.uniform(-0.04, 0.26)
    pe = rng.uniform(8.0, 38.0)
    shares = rng.uniform(2e8, 6e9)

    rows = []
    for quarter in _QUARTERS:
        # Slow random walks: a company's profile drifts, it does not jump.
        roe = float(np.clip(roe + rng.normal(0, 0.008), 0.0, 0.5))
        gross = float(np.clip(gross + rng.normal(0, 0.006), 0.05, 0.9))
        net = float(np.clip(net + rng.normal(0, 0.006), -0.05, min(gross, 0.45)))
        debt = float(np.clip(debt + rng.normal(0, 0.04), 0.0, 3.0))
        current = float(np.clip(current + rng.normal(0, 0.05), 0.5, 4.0))
        growth = float(np.clip(growth + rng.normal(0, 0.015), -0.2, 0.5))
        pe = float(np.clip(pe + rng.normal(0, 0.8), 5.0, 60.0))
        filed = quarter + timedelta(days=_FILING_LAG_DAYS)
        price = _close_on(ticker, filed)
        # Per-share figures follow from the price and the ratios, so the
        # valuation an agent reads is consistent with the tape.
        eps = price / pe
        bvps = eps / max(roe, 0.02)
        rows.append(FinancialMetrics(
            ticker=ticker,
            report_period=quarter.isoformat(),
            period="ttm",
            currency="USD",
            filing_date=filed.isoformat(),
            market_cap=round(price * shares, 0),
            price_to_earnings_ratio=round(price / eps, 2),
            price_to_book_ratio=round(price / bvps, 2),
            gross_margin=round(gross, 4),
            operating_margin=round((gross + net) / 2, 4),
            net_margin=round(net, 4),
            return_on_equity=round(roe, 4),
            debt_to_equity=round(debt, 3),
            current_ratio=round(current, 3),
            revenue_growth=round(growth, 4),
            earnings_per_share=round(eps, 3),
            book_value_per_share=round(bvps, 3),
            free_cash_flow_per_share=round(eps * 0.9, 3),
        ))
    return tuple(rows)


@lru_cache(maxsize=512)
def _earnings(ticker: str) -> tuple[EarningsRecord, ...]:
    """One 8-K per quarter, oldest first."""
    rng = np.random.default_rng(_seed("earnings", ticker))
    surprises = rng.choice(["BEAT", "MISS", "MEET"], size=len(_QUARTERS), p=[0.5, 0.3, 0.2])
    return tuple(
        EarningsRecord(
            ticker=ticker,
            report_period=quarter.isoformat(),
            source_type="8-K",
            filing_date=(quarter + timedelta(days=_EARNINGS_LAG_DAYS)).isoformat(),
            currency="USD",
            quarterly=EarningsData(eps_surprise=str(surprise)),
        )
        for quarter, surprise in zip(_QUARTERS, surprises)
    )


class DemoDataClient:
    """A `DataClient` (hedge_fund.data.protocol) over synthetic data.

    Keeps the engine's point-in-time contract: a metrics row is visible only
    from its filing date, and no price after the last completed session is
    ever returned.
    """

    def get_prices(self, ticker, start_date, end_date, interval="day", interval_multiplier=1, **_):
        if interval != "day":
            return []  # demo funds are daily; there are no intraday bars
        end = min(end_date[:10], completed_through())
        closes, volumes = _series(ticker.upper())
        bars = []
        for index, day in enumerate(_weekdays()):
            iso = day.isoformat()
            if iso < start_date[:10]:
                continue
            if iso > end:
                break
            close = float(closes[index])
            previous = float(closes[index - 1]) if index else close
            bars.append(Price(
                open=round(previous, 4), close=round(close, 4),
                high=round(max(previous, close) * 1.004, 4),
                low=round(min(previous, close) * 0.996, 4),
                volume=int(volumes[index]), time=f"{iso}T00:00:00",
            ))
        return bars

    def get_snapshot(self, ticker):
        bars = self.get_prices(ticker, (date.today() - timedelta(days=10)).isoformat(), date.today().isoformat())
        if not bars:
            return None
        return PriceSnapshot(ticker=ticker.upper(), price=bars[-1].close,
                             time=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=10):
        cutoff = min(end_date[:10], completed_through())
        filed = [row for row in _fundamentals(ticker.upper()) if row.filing_date <= cutoff]
        return list(reversed(filed))[:limit]

    def get_news(self, ticker, end_date, start_date=None, limit=1000):
        return []

    def get_insider_trades(self, ticker, end_date, start_date=None, limit=1000):
        return []

    def get_company_facts(self, ticker):
        ticker = ticker.upper()
        sector = _KNOWN_SECTORS.get(ticker) or _SECTORS[_seed("sector", ticker) % len(_SECTORS)]
        return CompanyFacts(ticker=ticker, name=f"{ticker} (demo)", sector=sector, industry=f"{sector} (demo)")

    def get_earnings(self, ticker) -> Earnings | None:
        return None

    def get_earnings_history(self, ticker, limit=12):
        today = completed_through()
        filed = [record for record in _earnings(ticker.upper()) if record.filing_date <= today]
        return list(reversed(filed))[:limit]

    def get_market_cap(self, ticker, end_date):
        rows = self.get_financial_metrics(ticker, end_date, limit=1)
        return rows[0].market_cap if rows else None

    def screen(self, as_of, filters, *, order_by=None, limit=100):
        return []

    def screener_fields(self):
        raise RuntimeError("the screener is not available in demo mode")


# ---------------------------------------------------------------------------
# The stand-in LLM
# ---------------------------------------------------------------------------

# How much each persona cares about each trait. Stylized, like the prompts.
_PERSONAS: dict[str, tuple[str, dict[str, float]]] = {
    "Warren Buffett": ("버핏", {"quality": 0.35, "margin": 0.20, "leverage": 0.20, "value": 0.15, "growth": 0.10}),
    "Charlie Munger": ("멍거", {"quality": 0.40, "margin": 0.25, "trend": 0.15, "value": 0.10, "leverage": 0.10}),
    "Benjamin Graham": ("그레이엄", {"value": 0.45, "safety": 0.25, "leverage": 0.20, "quality": 0.10}),
    "Peter Lynch": ("린치", {"growth": 0.45, "value": 0.30, "quality": 0.15, "leverage": 0.10}),
    "Stanley Druckenmiller": ("드러켄밀러", {"growth": 0.45, "trend": 0.35, "margin": 0.20}),
}
_DEFAULT_PERSONA = ("애널리스트", {"quality": 0.3, "value": 0.3, "growth": 0.2, "leverage": 0.2})
_NUMBER = r"(-?\d+(?:\.\d+)?)"


class DemoLLM:
    """An `LLMClient` that answers from the numbers in the prompt.

    It reads the fundamentals the engine rendered, scores them with weights
    that caricature each persona, and returns the JSON the agents expect.
    Every thesis is prefixed with [demo] so it cannot be mistaken for a
    model's reasoning.
    """

    model = DEMO_MODEL

    def complete(self, system: str, user: str) -> str:
        label, weights = next(
            (profile for name, profile in _PERSONAS.items() if name in system), _DEFAULT_PERSONA,
        )
        facts = _read_prompt(user)
        traits = {
            "quality": _scale(facts.get("roe"), 0.12, 0.15),
            "margin": _scale(facts.get("net_margin"), 0.08, 0.12),
            "leverage": _scale(facts.get("debt_to_equity"), 1.0, -1.0),
            "value": _scale(facts.get("pe"), 20.0, -15.0),
            "growth": _scale(facts.get("revenue_growth"), 0.05, 0.15),
            "safety": _scale(facts.get("current_ratio"), 1.5, 1.0),
            "trend": _scale(facts.get("gross_margin_trend"), 0.0, 0.05),
        }
        score = sum(weight * traits[trait] for trait, weight in weights.items())
        if score > 0.15:
            signal, word = "bullish", "강세"
        elif score < -0.15:
            signal, word = "bearish", "약세"
        else:
            signal, word = "neutral", "중립"
        confidence = round(min(95.0, 40.0 + abs(score) * 60.0)) if signal != "neutral" else 40
        seen = ", ".join(part for part in (
            _describe("ROE 평균", facts.get("roe"), percent=True),
            _describe("순이익률", facts.get("net_margin"), percent=True),
            _describe("부채비율(D/E)", facts.get("debt_to_equity")),
            _describe("P/E", facts.get("pe")),
            _describe("매출 성장", facts.get("revenue_growth"), percent=True),
        ) if part)
        reasoning = (
            f"[demo] {label} 규칙 기반 판단: {seen or '지표 부족'} → {word}(점수 {score:+.2f}). "
            "실제 LLM 호출이 아닌 데모 휴리스틱입니다."
        )
        return json.dumps({"signal": signal, "confidence": confidence, "reasoning": reasoning}, ensure_ascii=False)


def _read_prompt(user: str) -> dict[str, float]:
    """Pull the numbers the heuristic uses out of FundamentalsSnapshot.render()."""
    facts: dict[str, float] = {}
    for key, pattern in (
        ("roe", rf"ROE avg: {_NUMBER}"),
        ("net_margin", rf"Net margin avg: {_NUMBER}"),
        ("gross_margin_trend", rf"Gross margin trend \(latest-oldest\): {_NUMBER}"),
        ("debt_to_equity", rf"Debt/equity \(latest\): {_NUMBER}"),
    ):
        match = re.search(pattern, user)
        if match:
            facts[key] = float(match.group(1))
    # The first history row is the latest period:
    # period | filed | mktcap | P/E | ROE | gross_m | op_m | net_m | D/E | curr | rev_gr | ...
    rows = user.split("| EPS | BVPS | FCF/sh")
    if len(rows) == 2:
        latest = [cell.strip() for cell in rows[1].strip().splitlines()[0].split("|")]
        for key, index in (("pe", 3), ("current_ratio", 9), ("revenue_growth", 10)):
            try:
                facts[key] = float(latest[index])
            except (IndexError, ValueError):
                pass
    return facts


def _scale(value: float | None, center: float, width: float) -> float:
    """Map *value* to [-1, 1]: 0 at *center*, +1 one *width* above it. A
    negative width flips the sense (lower is better). Missing reads as 0."""
    if value is None:
        return 0.0
    return float(np.clip((value - center) / width, -1.0, 1.0))


def _describe(label: str, value: float | None, percent: bool = False) -> str:
    if value is None:
        return ""
    return f"{label} {value:.1%}" if percent else f"{label} {value:.2f}"
