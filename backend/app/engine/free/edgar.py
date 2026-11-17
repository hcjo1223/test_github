"""Point-in-time fundamentals from SEC EDGAR "company facts" (XBRL).

Every fact EDGAR serves carries the date its filing was *submitted*
(`filed`). That is what makes honest backtests possible on free data: on a
given date, only facts filed on or before it are visible, and a value that
was later restated is seen as it was first known to be.

Statements are rebuilt into trailing-twelve-month rows the way the engine's
`FinancialMetrics` expects. Flow items (revenue, income, cash flow) are
TTM = latest year-to-date + last fiscal year - the same year-to-date a year
earlier. Balance items are read at the period end.

Approximations, stated so nobody mistakes them for the paid feed:
  * tags differ between companies; a small alias list covers the common
    ones and a metric is None when none of them is reported;
  * total debt is long-term debt plus the short-term pieces EDGAR names
    most often, not a reconciled figure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Iterable

from hedge_fund.data.models import FinancialMetrics

GAAP = "us-gaap"

REVENUE = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
           "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"]
GROSS_PROFIT = ["GrossProfit"]
COST_OF_REVENUE = ["CostOfRevenue", "CostOfGoodsAndServicesSold"]
OPERATING_INCOME = ["OperatingIncomeLoss"]
NET_INCOME = ["NetIncomeLoss", "ProfitLoss"]
EPS = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]
OPERATING_CASH_FLOW = ["NetCashProvidedByUsedInOperatingActivities"]
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]
EQUITY = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
ASSETS = ["Assets"]
LIABILITIES = ["Liabilities"]
CURRENT_ASSETS = ["AssetsCurrent"]
CURRENT_LIABILITIES = ["LiabilitiesCurrent"]
LONG_TERM_DEBT = ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermNotesPayable"]
SHORT_TERM_DEBT = ["LongTermDebtCurrent", "ShortTermBorrowings", "CommercialPaper", "DebtCurrent"]

_FILING_FORMS = ("10-Q", "10-K")


@dataclass(frozen=True)
class Fact:
    start: date | None
    end: date
    val: float
    filed: date
    form: str


def _day(text: str) -> date:
    return date.fromisoformat(text[:10])


class Filings:
    """One company's facts, queried as of a date."""

    def __init__(self, raw: dict) -> None:
        self.cik = raw.get("cik")
        self.name = raw.get("entityName")
        self._facts: dict[tuple[str, str], list[Fact]] = {}
        for taxonomy, concepts in (raw.get("facts") or {}).items():
            for tag, body in concepts.items():
                rows: list[Fact] = []
                for unit_rows in (body.get("units") or {}).values():
                    for row in unit_rows:
                        if row.get("val") is None or not row.get("end") or not row.get("filed"):
                            continue
                        rows.append(Fact(
                            start=_day(row["start"]) if row.get("start") else None,
                            end=_day(row["end"]), val=float(row["val"]),
                            filed=_day(row["filed"]), form=row.get("form") or "",
                        ))
                self._facts[(taxonomy, tag)] = rows

    # ---- lookups ------------------------------------------------------------

    def _known(self, tags: Iterable[str], as_of: date, taxonomy: str = GAAP) -> dict[tuple[date | None, date], Fact]:
        """For each (start, end) the value as last filed on or before *as_of*.
        An earlier alias in *tags* wins when two aliases report the same period."""
        merged: dict[tuple[date | None, date], Fact] = {}
        for tag in reversed(list(tags)):  # later aliases first, so earlier ones overwrite
            latest: dict[tuple[date | None, date], Fact] = {}
            for fact in self._facts.get((taxonomy, tag), ()):
                if fact.filed > as_of:
                    continue
                key = (fact.start, fact.end)
                if key not in latest or fact.filed > latest[key].filed:
                    latest[key] = fact
            merged.update(latest)
        return merged

    def periods(self, as_of: date) -> list[tuple[date, date]]:
        """(period end, first filing date) for every 10-Q/10-K filed by *as_of*, oldest first.
        The balance sheet marks a filing: every 10-Q and 10-K has one."""
        first: dict[date, date] = {}
        for tag in ASSETS:
            for fact in self._facts.get((GAAP, tag), ()):
                if fact.form not in _FILING_FORMS or fact.filed > as_of or fact.start is not None:
                    continue
                if fact.end not in first or fact.filed < first[fact.end]:
                    first[fact.end] = fact.filed
        return sorted(first.items())

    def instant(self, tags: list[str], end: date, as_of: date) -> float | None:
        fact = self._known(tags, as_of).get((None, end))
        return fact.val if fact else None

    def ttm(self, tags: list[str], end: date, as_of: date) -> float | None:
        """Trailing twelve months ending at *end*, from facts filed by *as_of*."""
        known = self._known(tags, as_of)
        spans = [f for (start, e), f in known.items() if e == end and start is not None and (end - start).days <= 380]
        if not spans:
            return None
        ytd = max(spans, key=lambda f: (end - f.start).days)
        if (end - ytd.start).days >= 350:
            return ytd.val  # a full year
        fiscal_start = ytd.start
        prior_year = next((
            f for (s, e), f in known.items()
            if s is not None and 350 <= (e - s).days <= 380 and abs((e - (fiscal_start - timedelta(days=1))).days) <= 7
        ), None)
        prior_ytd = next((
            f for (s, e), f in known.items()
            if s is not None and abs((e - (end - timedelta(days=365))).days) <= 10
            and abs((s - (fiscal_start - timedelta(days=365))).days) <= 10
            and (e - s).days <= 380
        ), None)
        if prior_year is None or prior_ytd is None:
            return None
        return ytd.val + prior_year.val - prior_ytd.val

    def shares(self, filed: date, as_of: date) -> float | None:
        """Shares outstanding from the cover page of the filing made on *filed*
        (or the nearest earlier one)."""
        candidates = [f for f in self._facts.get(("dei", "EntityCommonStockSharesOutstanding"), ()) if f.filed <= as_of]
        if not candidates:
            return None
        best = min(candidates, key=lambda f: (abs((f.filed - filed).days), -f.filed.toordinal()))
        return best.val if abs((best.filed - filed).days) <= 120 else None

    # ---- the engine's row ---------------------------------------------------

    def metrics(
        self, ticker: str, as_of: date, limit: int, price_on: Callable[[date], float | None],
    ) -> list[FinancialMetrics]:
        """TTM rows for the last *limit* filings made by *as_of*, newest first."""
        periods = self.periods(as_of)
        ends = [end for end, _ in periods]
        rows: list[FinancialMetrics] = []
        for end, filed in reversed(periods[-limit:]):
            rows.append(self._row(ticker, end, filed, as_of, ends, price_on))
        return rows

    def _row(self, ticker, end, filed, as_of, ends, price_on) -> FinancialMetrics:
        revenue = self.ttm(REVENUE, end, as_of)
        gross = self.ttm(GROSS_PROFIT, end, as_of)
        if gross is None and revenue is not None:
            cost = self.ttm(COST_OF_REVENUE, end, as_of)
            gross = revenue - cost if cost is not None else None
        operating = self.ttm(OPERATING_INCOME, end, as_of)
        income = self.ttm(NET_INCOME, end, as_of)
        eps = self.ttm(EPS, end, as_of)
        ocf = self.ttm(OPERATING_CASH_FLOW, end, as_of)
        capex = self.ttm(CAPEX, end, as_of)
        equity = self.instant(EQUITY, end, as_of)
        assets = self.instant(ASSETS, end, as_of)
        cur_assets = self.instant(CURRENT_ASSETS, end, as_of)
        cur_liabilities = self.instant(CURRENT_LIABILITIES, end, as_of)
        debt = self._debt(end, as_of)
        shares = self.shares(filed, as_of)
        price = price_on(filed)

        year_ago = next((e for e in ends if abs((e - (end - timedelta(days=365))).days) <= 20), None)
        revenue_before = self.ttm(REVENUE, year_ago, as_of) if year_ago else None
        bvps = equity / shares if equity is not None and shares else None
        fcf = ocf - capex if ocf is not None and capex is not None else None

        return FinancialMetrics(
            ticker=ticker, report_period=end.isoformat(), period="ttm", currency="USD",
            filing_date=filed.isoformat(),
            market_cap=round(price * shares, 0) if price and shares else None,
            price_to_earnings_ratio=_ratio(price, eps, positive=True),
            price_to_book_ratio=_ratio(price, bvps, positive=True),
            gross_margin=_ratio(gross, revenue),
            operating_margin=_ratio(operating, revenue),
            net_margin=_ratio(income, revenue),
            return_on_equity=_ratio(income, equity, positive=True),
            return_on_assets=_ratio(income, assets),
            debt_to_equity=_ratio(debt, equity, positive=True),
            current_ratio=_ratio(cur_assets, cur_liabilities),
            revenue_growth=_ratio_change(revenue, revenue_before),
            earnings_per_share=round(eps, 4) if eps is not None else None,
            book_value_per_share=round(bvps, 4) if bvps is not None else None,
            free_cash_flow_per_share=round(fcf / shares, 4) if fcf is not None and shares else None,
        )

    def _debt(self, end: date, as_of: date) -> float | None:
        long_term = self.instant(LONG_TERM_DEBT, end, as_of)
        short_term = sum(v for tag in SHORT_TERM_DEBT if (v := self.instant([tag], end, as_of)) is not None)
        if long_term is None and not short_term:
            return None
        return (long_term or 0.0) + short_term


def _ratio(numerator: float | None, denominator: float | None, positive: bool = False) -> float | None:
    """numerator / denominator, or None when it is not meaningful. With
    *positive*, a non-positive denominator gives None (a P/E on a loss, a
    return on negative equity)."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    if positive and denominator < 0:
        return None
    return round(numerator / denominator, 4)


def _ratio_change(now: float | None, before: float | None) -> float | None:
    if now is None or before is None or before <= 0:
        return None
    return round(now / before - 1, 4)
