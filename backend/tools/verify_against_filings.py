"""Check the free data client against the filings themselves.

The client rebuilds trailing-twelve-month ratios from EDGAR's XBRL "company
facts". This script gets the same answer a second, independent way: it
downloads the 10-K / 10-Q documents, reads the printed financial statements
(the tables a person reads), computes the same ratios from those numbers,
and compares them with what the client returns for the same period.

    AIHF_WEB_CONTACT="Name you@example.com" uv run python tools/verify_against_filings.py [cache_dir]

SEC requires a real contact in the User-Agent; it is read from the
environment and never stored. Documents are cached in *cache_dir*.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engine.free.client import FreeDataClient  # noqa: E402

CHECKS = [  # (ticker, cik, period end, form, filing date)  — and the 10-K its year-to-date needs
    ("AAPL", 320193, "2026-09-26", "10-K"),
    ("AAPL", 320193, "2026-06-27", "10-Q"),
    ("AAPL", 320193, "2026-03-28", "10-Q"),
    ("MSFT", 789019, "2026-06-30", "10-K"),
    ("MSFT", 789019, "2026-09-30", "10-Q"),
]
NUMBER = re.compile(r"^\(?\$?\s*(\d[\d,]*(?:\.\d+)?)\)?%?$")


class Tables(HTMLParser):
    """Every table in a document as a list of rows of cell texts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._depth = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self.tables.append([])
        elif tag == "tr" and self._depth == 1:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self._depth = max(0, self._depth - 1)
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self._depth == 1:
            if any(self._row):
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_row(row: list[str]) -> tuple[str, list[float]]:
    """(label, numbers) of a statement row. A leading "(" makes a number
    negative; the "$" and ")" cells SEC splits them into are ignored."""
    label = next((c for c in row if c and not NUMBER.match(c) and c not in ("$", ")", "%")), "")
    numbers: list[float] = []
    pending_negative = False
    for cell in row:
        text = cell.replace("—", "").strip()
        if text == "(":
            pending_negative = True
            continue
        match = NUMBER.match(text)
        if match:
            value = float(match.group(1).replace(",", ""))
            negative = text.startswith("(") or pending_negative
            numbers.append(-value if negative else value)
            pending_negative = False
    return label, numbers


def statement(tables, must_have: list[str]) -> dict[str, list[list[float]]]:
    """The first table whose row labels include every phrase in *must_have*,
    as {label: [numbers, ...]} (a label can repeat, e.g. 'Diluted')."""
    for table in tables:
        parsed = [parse_row(row) for row in table]
        labels = " | ".join(label.lower() for label, _ in parsed)
        if all(phrase in labels for phrase in must_have):
            out: dict[str, list[list[float]]] = {}
            for label, numbers in parsed:
                if numbers:
                    out.setdefault(label, []).append(numbers)
            return out
    raise LookupError(f"no table with {must_have}")


def pick(table, *patterns: str, small: bool = False) -> list[float] | None:
    """Numbers of the first row whose label matches one of *patterns*.
    *small* skips rows of big numbers (to take EPS, not share counts)."""
    for pattern in patterns:
        for label, rows in table.items():
            if re.fullmatch(pattern, label.strip().rstrip(":"), re.IGNORECASE):
                for numbers in rows:
                    if not small or max(abs(n) for n in numbers) < 1000:
                        return numbers
    return None


@dataclass
class Filing:
    form: str
    period: str
    income: dict
    balance: dict
    ytd_cols: tuple[int, int] = (0, 1)  # (this year, last year) columns holding year-to-date figures

    def flow(self, *patterns, small=False) -> tuple[float, float] | None:
        numbers = pick(self.income, *patterns, small=small)
        if numbers is None:
            return None
        if self.form == "10-K":
            return numbers[0], numbers[1]
        if len(numbers) >= 4:  # 3 months this/last year, then year to date this/last year
            return numbers[2], numbers[3]
        return numbers[0], numbers[1]  # first quarter: the quarter is the year to date

    def annual(self, *patterns, small=False) -> float | None:
        numbers = pick(self.income, *patterns, small=small)
        return numbers[0] if numbers else None

    def instant(self, *patterns) -> float | None:
        numbers = pick(self.balance, *patterns)
        return numbers[0] if numbers else None

    def debt(self) -> float:
        total = 0.0
        for label, rows in self.balance.items():
            if re.fullmatch(r"(term debt|commercial paper|short-term debt|long-term debt|current portion of long-term debt)", label.strip().lower()):
                total += sum(numbers[0] for numbers in rows)
        return total


@dataclass
class Fetcher:
    contact: str
    cache: Path
    last: float = 0.0
    session: requests.Session = field(default_factory=requests.Session)

    def get(self, url: str) -> str:
        path = self.cache / re.sub(r"\W+", "_", url)
        if path.exists():
            return path.read_text()
        wait = 0.2 - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        response = self.session.get(url, headers={"User-Agent": f"AIHF-Web/0.1 {self.contact}"}, timeout=90)
        self.last = time.monotonic()
        response.raise_for_status()
        self.cache.mkdir(parents=True, exist_ok=True)
        path.write_text(response.text)
        return response.text


def load_filing(fetcher: Fetcher, submissions: dict, cik: int, form: str, period: str) -> Filing:
    recent = submissions["filings"]["recent"]
    index = next(i for i, f in enumerate(recent["form"]) if f == form and recent["reportDate"][i] == period)
    accession = recent["accessionNumber"][index].replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{recent['primaryDocument'][index]}"
    parser = Tables()
    parser.feed(fetcher.get(url))
    income = statement(parser.tables, ["net income", "operating income"])
    balance = statement(parser.tables, ["total assets", "total liabilities"])
    return Filing(form, period, income, balance)


def previous_10k(submissions: dict, period: str) -> str:
    """Report date of the latest 10-K for a fiscal year ended before *period*."""
    recent = submissions["filings"]["recent"]
    return max(recent["reportDate"][i] for i, f in enumerate(recent["form"]) if f == "10-K" and recent["reportDate"][i] < period)


REVENUE = (r"total net sales", r"total revenue", r"net sales", r"revenue")
GROSS = (r"gross margin", r"gross profit")
OPERATING = (r"operating income",)
NET = (r"net income",)
EPS = (r"diluted",)


def ttm_from_filings(this: Filing, base_10k: Filing | None, *patterns, small=False) -> float | None:
    """TTM as the statements give it: a 10-K's year; else this year to date
    + last fiscal year - the same year to date a year ago."""
    ytd = this.flow(*patterns, small=small)
    if ytd is None:
        return None
    if this.form == "10-K":
        return ytd[0]
    year = base_10k.annual(*patterns, small=small) if base_10k else None
    return None if year is None else ytd[0] + year - ytd[1]


def compare(client: FreeDataClient, fetcher: Fetcher, ticker: str, cik: int, period: str, form: str) -> list[dict]:
    submissions = json.loads(fetcher.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    this = load_filing(fetcher, submissions, cik, form, period)
    base = None if form == "10-K" else load_filing(fetcher, submissions, cik, "10-K", previous_10k(submissions, period))
    revenue = ttm_from_filings(this, base, *REVENUE)
    gross = ttm_from_filings(this, base, *GROSS)
    operating = ttm_from_filings(this, base, *OPERATING)
    income = ttm_from_filings(this, base, *NET)
    eps = ttm_from_filings(this, base, *EPS, small=True)
    equity = this.instant(r"total (share|stock)holders[’'] equity", r"total equity")
    assets = this.instant(r"total assets")
    current = (this.instant(r"total current assets"), this.instant(r"total current liabilities"))
    debt = this.debt()

    filed = next(r for r in [json.loads(fetcher.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))["filings"]["recent"]]
                 for _ in [0])
    recent = submissions["filings"]["recent"]
    filed_on = next(recent["filingDate"][i] for i, f in enumerate(recent["form"]) if f == form and recent["reportDate"][i] == period)
    ours = next(r for r in client.get_financial_metrics(ticker, filed_on, limit=12) if r.report_period == period)

    reference = {
        "gross_margin": gross / revenue,
        "operating_margin": operating / revenue,
        "net_margin": income / revenue,
        "return_on_equity": income / equity,
        "return_on_assets": income / assets,
        "current_ratio": current[0] / current[1],
        "debt_to_equity": debt / equity,
        "earnings_per_share": eps,
    }
    tolerance = {"earnings_per_share": 0.02, "debt_to_equity": 0.005, "return_on_equity": 0.002}
    rows = []
    for name, expected in reference.items():
        got = getattr(ours, name)
        diff = None if got is None else got - expected
        limit = tolerance.get(name, 0.0006)
        rows.append({
            "ticker": ticker, "period": period, "form": form, "metric": name,
            "filing": round(expected, 4), "client": got, "diff": None if diff is None else round(diff, 4),
            "ok": diff is not None and abs(diff) <= limit,
        })
    return rows


def main() -> int:
    contact = os.environ.get("AIHF_WEB_CONTACT", "")
    if "@" not in contact:
        print("Set AIHF_WEB_CONTACT to a real contact (Name you@example.com): SEC requires it.", file=sys.stderr)
        return 2
    cache = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/aihf-verify")
    client = FreeDataClient(contact, cache / "client")
    fetcher = Fetcher(contact, cache / "docs")
    rows: list[dict] = []
    for ticker, cik, period, form in CHECKS:
        try:
            rows += compare(client, fetcher, ticker, cik, period, form)
        except (LookupError, StopIteration, ZeroDivisionError, TypeError, KeyError) as exc:
            rows.append({"ticker": ticker, "period": period, "form": form, "metric": "(unreadable)", "filing": None,
                         "client": None, "diff": None, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    print(f"{'ticker':6} {'period':10} {'form':5} {'metric':18} {'filing':>10} {'client':>10} {'diff':>9}")
    for r in rows:
        print(f"{r['ticker']:6} {r['period']:10} {r['form']:5} {r['metric']:18} {str(r['filing']):>10} {str(r['client']):>10} "
              f"{str(r['diff']):>9} {'ok' if r['ok'] else 'MISMATCH ' + r.get('error', '')}")
    bad = [r for r in rows if not r["ok"]]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} within tolerance")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
