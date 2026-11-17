"""A DataClient over free sources: SEC EDGAR for fundamentals, Yahoo Finance
for prices.

For exploration, not for conclusions. What differs from the paid feed:

  * Fundamentals are point-in-time (EDGAR dates every filing), but are
    rebuilt from XBRL tags, so some companies and some ratios are missing.
  * Prices come from an unofficial Yahoo endpoint: split-adjusted, not
    dividend-adjusted, and the endpoint can change or throttle without
    notice. Anything unexpected raises; nothing is silently emptied.
  * There are no analyst estimates, so there is no earnings surprise: the
    PEAD model never fires. `get_earnings_history` is empty on purpose.
  * News, insider trades and the screener are not available.

SEC's fair-access policy requires automated clients to identify themselves
with a real contact, and to stay under 10 requests a second. Both are
enforced here; the contact is the user's to supply.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from hedge_fund.data.models import (
    CompanyFacts, CompanyNews, Earnings, EarningsRecord, FinancialMetrics, InsiderTrade, Price, PriceSnapshot,
)
from hedge_fund.data.sessions import completed_through

from app.engine.free.edgar import Filings

SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

SEC_MIN_INTERVAL = 0.15       # seconds between SEC requests (policy: under 10 a second)
TICKERS_TTL = 7 * 86400
FACTS_TTL = 86400
PRICES_TTL = 12 * 3600
HISTORY_START = date(2005, 1, 1)
_CONTACT = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class FreeDataError(RuntimeError):
    """A free source failed or refused. Never swallowed into 'no data'."""


def valid_contact(contact: str | None) -> bool:
    return bool(contact and _CONTACT.search(contact))


_SECTOR_OVERRIDES = [(range(3570, 3580), "Technology"), (range(3670, 3680), "Technology"), (range(7370, 7380), "Technology"),
                     (range(2830, 2837), "Healthcare"), (range(8000, 8100), "Healthcare"), (range(6000, 6800), "Financials"),
                     (range(1300, 1390), "Energy"), (range(2900, 2912), "Energy"), (range(4900, 4950), "Utilities")]
_SECTOR_DIVISIONS = [(100, "Agriculture"), (1000, "Mining"), (1500, "Construction"), (4000, "Manufacturing"),
                     (5000, "Transportation & Communications"), (5200, "Wholesale"), (6000, "Retail"),
                     (7000, "Financials"), (9000, "Services"), (10000, "Public Administration")]


def sector_for(sic: int | None) -> str | None:
    """A coarse sector from an SIC code. Coarse on purpose: SIC is an industry
    code from 1937, and sector limits built on it are only as good as that."""
    if sic is None:
        return None
    for codes, sector in _SECTOR_OVERRIDES:
        if sic in codes:
            return sector
    return next((name for ceiling, name in _SECTOR_DIVISIONS if sic < ceiling), None)


class FreeDataClient:
    def __init__(
        self, contact: str, cache_dir: Path | str, *, session: requests.Session | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        if not valid_contact(contact):
            raise FreeDataError(
                "SEC EDGAR 이용 정책상 요청자의 실제 연락처(이메일)가 필요합니다. 설정에서 연락처를 입력하세요."
            )
        self._contact = contact.strip()
        self._dir = Path(cache_dir)
        self._session = session or requests.Session()
        self._now = now
        self._lock = threading.Lock()
        self._last_sec = 0.0
        self._filings: dict[str, Filings | None] = {}
        self._bars: dict[str, list[Price]] = {}
        self._ciks: dict[str, int] | None = None

    # ---- plumbing -----------------------------------------------------------

    def _cached(self, name: str, ttl: float, fetch: Callable[[], Any]) -> Any:
        path = self._dir / name
        try:
            if self._now() - path.stat().st_mtime < ttl:
                return json.loads(path.read_text())
        except (OSError, ValueError):
            pass
        try:
            data = fetch()
        except FreeDataError:
            if path.exists():  # a stale copy beats failing a long run
                try:
                    return json.loads(path.read_text())
                except (OSError, ValueError):
                    pass
            raise
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, separators=(",", ":")))
        return data

    def _sec(self, url: str) -> Any:
        with self._lock:  # one SEC request at a time, spaced out
            wait = SEC_MIN_INTERVAL - (time.monotonic() - self._last_sec)
            if wait > 0:
                time.sleep(wait)
            try:
                response = self._session.get(url, headers={"User-Agent": f"AIHF-Web/0.1 {self._contact}"}, timeout=60)
            except requests.RequestException as exc:
                raise FreeDataError(f"SEC 요청 실패: {exc}") from exc
            finally:
                self._last_sec = time.monotonic()
        if response.status_code == 404:
            return None
        if response.status_code == 403:
            raise FreeDataError("SEC가 요청을 거절했습니다(403). 연락처가 올바른 이메일인지 확인하세요.")
        if response.status_code != 200:
            raise FreeDataError(f"SEC 응답 오류 {response.status_code}: {url}")
        return response.json()

    # ---- SEC: who is this ticker ---------------------------------------------

    def _cik(self, ticker: str) -> int | None:
        if self._ciks is None:
            raw = self._cached("sec/tickers.json", TICKERS_TTL, lambda: self._sec(SEC_TICKERS))
            self._ciks = {row["ticker"].upper(): int(row["cik_str"]) for row in raw.values()}
        return self._ciks.get(ticker.upper().replace("-", "."), self._ciks.get(ticker.upper()))

    def _filings_for(self, ticker: str) -> Filings | None:
        ticker = ticker.upper()
        if ticker not in self._filings:
            cik = self._cik(ticker)
            if cik is None:
                self._filings[ticker] = None  # not an SEC registrant (an ETF, say)
            else:
                raw = self._cached(f"sec/facts-{cik}.json", FACTS_TTL, lambda: self._sec(SEC_FACTS.format(cik=cik)))
                self._filings[ticker] = Filings(raw) if raw else None
        return self._filings[ticker]

    # ---- Yahoo: prices --------------------------------------------------------

    def _series(self, ticker: str) -> list[Price]:
        ticker = ticker.upper()
        if ticker in self._bars:
            return self._bars[ticker]
        symbol = ticker.replace(".", "-")
        newest = completed_through()

        def fetch() -> dict:
            start = int(datetime.combine(HISTORY_START, datetime.min.time(), timezone.utc).timestamp())
            end = int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp())
            try:
                response = self._session.get(
                    YAHOO_CHART.format(symbol=symbol),
                    params={"period1": start, "period2": end, "interval": "1d", "events": "div,split"},
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=30,
                )
            except requests.RequestException as exc:
                raise FreeDataError(f"Yahoo 시세 요청 실패: {exc}") from exc
            if response.status_code == 404:
                return {"bars": []}
            if response.status_code != 200:
                raise FreeDataError(f"Yahoo 시세 응답 오류 {response.status_code} ({ticker})")
            return {"bars": _parse_chart(response.json(), ticker)}

        data = self._cached(f"prices/{ticker}.json", PRICES_TTL, fetch)
        bars = [Price(open=o, high=h, low=l, close=c, volume=v, time=f"{d}T00:00:00") for d, o, h, l, c, v in data["bars"]]
        if bars and bars[-1].time[:10] < newest:
            # The cache is fresh by age but stops short of the last completed session.
            try:
                (self._dir / f"prices/{ticker}.json").unlink()
                data = self._cached(f"prices/{ticker}.json", PRICES_TTL, fetch)
                bars = [Price(open=o, high=h, low=l, close=c, volume=v, time=f"{d}T00:00:00") for d, o, h, l, c, v in data["bars"]]
            except (OSError, FreeDataError):
                pass
        self._bars[ticker] = bars
        return bars

    def _close_on_or_before(self, ticker: str, day: date) -> float | None:
        iso = day.isoformat()
        last = None
        for bar in self._series(ticker):
            if bar.time[:10] > iso:
                break
            last = bar.close
        return last

    # ---- DataClient protocol --------------------------------------------------

    def get_prices(self, ticker, start_date, end_date, interval="day", interval_multiplier=1, **_) -> list[Price]:
        if interval != "day":
            return []  # no intraday bars from this source
        end = min(end_date[:10], completed_through())
        return [bar for bar in self._series(ticker) if start_date[:10] <= bar.time[:10] <= end]

    def get_snapshot(self, ticker) -> PriceSnapshot | None:
        bars = self._series(ticker)
        if not bars:
            return None
        return PriceSnapshot(ticker=ticker.upper(), price=bars[-1].close, time=f"{bars[-1].time[:10]}T21:00:00Z")

    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=10) -> list[FinancialMetrics]:
        filings = self._filings_for(ticker)
        if filings is None or period != "ttm":
            return []
        as_of = min(date.fromisoformat(end_date[:10]), date.fromisoformat(completed_through()))
        return filings.metrics(ticker.upper(), as_of, limit, lambda day: self._close_on_or_before(ticker, day))

    def get_company_facts(self, ticker) -> CompanyFacts | None:
        cik = self._cik(ticker)
        if cik is None:
            return None
        raw = self._cached(f"sec/submissions-{cik}.json", TICKERS_TTL, lambda: self._sec(SEC_SUBMISSIONS.format(cik=cik)))
        if not raw:
            return None
        sic = int(raw["sic"]) if str(raw.get("sic") or "").isdigit() else None
        return CompanyFacts(
            ticker=ticker.upper(), name=raw.get("name"), cik=str(cik), sector=sector_for(sic),
            industry=raw.get("sicDescription"), exchange=(raw.get("exchanges") or [None])[0],
            sic_code=str(sic) if sic is not None else None, sic_industry=raw.get("sicDescription"),
        )

    def get_market_cap(self, ticker, end_date) -> float | None:
        rows = self.get_financial_metrics(ticker, end_date, limit=1)
        return rows[0].market_cap if rows else None

    def get_earnings_history(self, ticker, limit=12) -> list[EarningsRecord]:
        return []  # no analyst estimates, so no surprise: PEAD stays silent

    def get_earnings(self, ticker) -> Earnings | None:
        return None

    def get_news(self, ticker, end_date, start_date=None, limit=1000) -> list[CompanyNews]:
        return []

    def get_insider_trades(self, ticker, end_date, start_date=None, limit=1000) -> list[InsiderTrade]:
        return []

    def screen(self, as_of, filters, *, order_by=None, limit=100):
        raise FreeDataError("무료 데이터 모드에는 스크리너가 없습니다.")

    def screener_fields(self):
        raise FreeDataError("무료 데이터 모드에는 스크리너가 없습니다.")


def _parse_chart(payload: dict, ticker: str) -> list[list]:
    """Daily bars from Yahoo's chart response, as [date, o, h, l, c, volume]."""
    chart = payload.get("chart") or {}
    if chart.get("error"):
        code = (chart["error"] or {}).get("code")
        if code == "Not Found":
            return []
        raise FreeDataError(f"Yahoo 오류 ({ticker}): {chart['error']}")
    results = chart.get("result") or []
    if not results:
        return []
    result = results[0]
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    offset = (result.get("meta") or {}).get("gmtoffset", 0)
    bars = []
    for i, stamp in enumerate(stamps):
        close = (quote.get("close") or [None] * len(stamps))[i]
        if close is None:
            continue
        day = datetime.fromtimestamp(stamp + offset, timezone.utc).date().isoformat()
        open_, high, low = ((quote.get(k) or [None] * len(stamps))[i] for k in ("open", "high", "low"))
        volume = (quote.get("volume") or [0] * len(stamps))[i] or 0
        bars.append([day, round(open_ if open_ is not None else close, 4), round(high if high is not None else close, 4),
                     round(low if low is not None else close, 4), round(close, 4), int(volume)])
    # One bar per day; the last one wins if Yahoo repeats a day.
    return list({bar[0]: bar for bar in bars}.values())
