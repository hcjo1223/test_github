"""The free data client, offline: EDGAR and Yahoo are replaced by fixtures
trimmed from real responses for AAPL."""

import json
from datetime import date
from pathlib import Path

import pytest

from hedge_fund.data import DataClient

from app.engine.free.client import FreeDataClient, FreeDataError, sector_for, valid_contact
from app.engine.free.edgar import NET_INCOME, Filings

FIXTURES = Path(__file__).parent / "fixtures"
FACTS = json.loads((FIXTURES / "edgar_aapl_facts.json").read_text())
SUBMISSIONS = json.loads((FIXTURES / "edgar_aapl_submissions.json").read_text())
YAHOO = json.loads((FIXTURES / "yahoo_aapl_2025.json").read_text())


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload


class FakeSession:
    """Routes the three hosts the client talks to, and records what it sent."""

    def __init__(self, ticker_known=True, status=200):
        self.calls: list[tuple[str, dict]] = []
        self.ticker_known, self.status = ticker_known, status

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append((url, headers or {}))
        if self.status != 200:
            return FakeResponse({}, self.status)
        if "company_tickers" in url:
            return FakeResponse({"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}} if self.ticker_known else {})
        if "companyfacts" in url:
            return FakeResponse(FACTS)
        if "submissions" in url:
            return FakeResponse(SUBMISSIONS)
        if "finance.yahoo.com" in url:
            return FakeResponse(YAHOO)
        raise AssertionError(f"unexpected url {url}")


@pytest.fixture
def client(tmp_path):
    return FreeDataClient("research@example.org", tmp_path, session=FakeSession())


def test_implements_the_engine_protocol(client):
    assert isinstance(client, DataClient)


def test_a_contact_is_required_and_sent(tmp_path):
    for bad in ("", "no-at-sign", "someone@"):
        with pytest.raises(FreeDataError, match="연락처"):
            FreeDataClient(bad, tmp_path)
    session = FakeSession()
    FreeDataClient("Research Team research@example.org", tmp_path, session=session).get_financial_metrics("AAPL", "2025-06-30")
    sec_calls = [headers for url, headers in session.calls if "sec.gov" in url]
    assert sec_calls and all("research@example.org" in h["User-Agent"] for h in sec_calls)
    assert valid_contact("a@b.co") and not valid_contact("a@b")


def test_sec_refusal_is_loud(tmp_path):
    with pytest.raises(FreeDataError, match="403"):
        FreeDataClient("r@example.org", tmp_path, session=FakeSession(status=403)).get_financial_metrics("AAPL", "2025-06-30")


def test_fundamentals_are_point_in_time(client):
    rows = client.get_financial_metrics("AAPL", "2025-06-30", limit=6)
    assert len(rows) == 6
    assert all(row.filing_date <= "2025-06-30" for row in rows)
    assert [row.filing_date for row in rows] == sorted((row.filing_date for row in rows), reverse=True)
    # The 10-K for the year ended 2024-09-28 was filed 2024-11-01: invisible the day before, visible on it.
    before = client.get_financial_metrics("AAPL", "2024-10-31", limit=1)[0]
    on_day = client.get_financial_metrics("AAPL", "2024-11-01", limit=1)[0]
    assert before.report_period == "2024-06-29" and on_day.report_period == "2024-09-28"
    assert on_day.filing_date == "2024-11-01"


def test_ttm_rebuilds_a_full_year_from_year_to_date_facts():
    filings = Filings(FACTS)
    # Year ended: the fiscal-year fact itself.
    assert filings.ttm(NET_INCOME, date(2024, 9, 28), date(2025, 1, 1)) == 93_736_000_000
    # A third quarter: nine months this year + last fiscal year - nine months last year.
    ttm = filings.ttm(NET_INCOME, date(2024, 6, 29), date(2024, 9, 1))
    nine_months, last_year, nine_months_before = 79_000_000_000, 96_995_000_000, 74_039_000_000
    assert ttm == nine_months + last_year - nine_months_before


def test_a_restated_value_is_seen_as_first_filed():
    facts = {"cik": 1, "facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
        {"start": "2023-01-01", "end": "2023-12-31", "val": 100, "filed": "2024-02-01", "form": "10-K"},
        {"start": "2023-01-01", "end": "2023-12-31", "val": 90, "filed": "2025-02-01", "form": "10-K"},
    ]}}}}}
    filings = Filings(facts)
    assert filings.ttm(NET_INCOME, date(2023, 12, 31), date(2024, 6, 1)) == 100, "before the restatement"
    assert filings.ttm(NET_INCOME, date(2023, 12, 31), date(2025, 6, 1)) == 90


def test_ratios_look_like_apple(client):
    row = client.get_financial_metrics("AAPL", "2025-06-30", limit=1)[0]
    assert 0.40 < row.gross_margin < 0.50 and 0.20 < row.net_margin < 0.30
    assert row.return_on_equity > 0.8, "Apple's equity is small, so ROE is very high"
    assert row.market_cap > 1e12 and 10 < row.price_to_earnings_ratio < 60
    assert row.current_ratio and row.debt_to_equity and row.earnings_per_share and row.book_value_per_share
    assert -0.1 < row.revenue_growth < 0.3


def test_prices_follow_the_engine_contract(client):
    bars = client.get_prices("AAPL", "2025-03-03", "2025-03-14")
    assert 8 <= len(bars) <= 10
    assert all(bar.low <= bar.close <= bar.high and bar.close > 0 for bar in bars)
    assert [bar.time for bar in bars] == sorted(bar.time for bar in bars)
    assert client.get_prices("AAPL", "2025-03-03", "2025-03-14", interval="minute") == []
    assert client.get_prices("AAPL", "2090-01-01", "2090-02-01") == []


def test_unknown_tickers_and_missing_features_are_empty_not_faked(tmp_path):
    client = FreeDataClient("r@example.org", tmp_path, session=FakeSession(ticker_known=False))
    assert client.get_financial_metrics("SPY", "2025-06-30") == []
    assert client.get_company_facts("SPY") is None
    assert client.get_earnings_history("SPY") == [] and client.get_news("SPY", "2025-06-30") == []
    with pytest.raises(FreeDataError):
        client.screen("2025-06-30", [])


def test_company_facts_and_sectors(client):
    facts = client.get_company_facts("AAPL")
    assert facts.name == "Apple Inc." and facts.sector == "Technology" and facts.sic_code == "3571"
    assert sector_for(2834) == "Healthcare" and sector_for(6022) == "Financials" and sector_for(None) is None


def test_second_client_reads_the_disk_cache(tmp_path):
    first = FakeSession()
    FreeDataClient("r@example.org", tmp_path, session=first).get_financial_metrics("AAPL", "2025-06-30")
    second = FakeSession()
    FreeDataClient("r@example.org", tmp_path, session=second).get_financial_metrics("AAPL", "2025-06-30")
    assert not [url for url, _ in second.calls if "sec.gov" in url], "SEC is not asked twice within the cache window"


# ---- the free mode inside the app ------------------------------------------------

def test_free_mode_needs_a_contact(home):
    from fastapi.testclient import TestClient
    from app.main import create_app

    client = TestClient(create_app())
    refused = client.put("/api/settings", json={"mode": "free"})
    assert refused.status_code == 400 and "연락처" in refused.json()["detail"]
    assert client.put("/api/settings", json={"contact": "no-email"}).status_code == 400

    saved = client.put("/api/settings", json={"contact": "Research research@example.org"}).json()
    assert saved["free_ready"] is True and saved["free_uses_demo_llm"] is True
    assert client.put("/api/settings", json={"mode": "free"}).json()["mode"] == "free"


def test_free_mode_runs_a_backtest_on_free_data(home, monkeypatch):
    """The whole path with EDGAR and Yahoo faked: free data, rule-based analysts, notes on the report."""
    import time
    from fastapi.testclient import TestClient
    from app.engine import runtime
    from app.main import create_app

    session = FakeSession()
    monkeypatch.setattr(runtime, "FreeDataClient", lambda contact, cache: FreeDataClient(contact, cache, session=session))
    client = TestClient(create_app())
    client.put("/api/settings", json={"contact": "r@example.org", "mode": "free"})
    assert [m["name"] for m in client.get("/api/mandates").json()] == ["example-fund"]
    assert (home / "web-free" / "mandates" / "example.yaml").is_file(), "free mode has its own workspace"

    spec = {"name": "free-test", "strategies": [{"name": "value", "blend": {"mode": "long_only"},
            "models": [{"name": "graham"}, {"name": "buffett"}]}],
            "risk": {"max_position_pct": 0.5, "max_gross_exposure": 1.0}, "rebalance": "weekly"}
    assert client.post("/api/mandates", json=spec).status_code == 201
    job_id = client.post("/api/backtests", json={"mandate": "free-test", "universe": ["AAPL"],
                         "start": "2025-03-03", "end": "2025-06-30"}).json()["job_id"]
    for _ in range(600):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "succeeded", job["error"]

    report = client.get(f"/api/backtests/{job['result']['backtest_id']}").json()
    assert report["mode"] == "free" and report["llm_model"] == "demo-heuristic"
    assert any("PEAD" in note or "Yahoo" in note for note in report["notes"])
    assert any("규칙 기반" in note for note in report["notes"]), "the stand-in analysts are disclosed"
    decided = next(s for s in report["sessions"] if s["decided"])
    detail = client.get(f"/api/backtests/{report['id']}/sessions/{decided['session']}").json()
    signal = detail["decision"]["strategies"][0]["signals"][0]
    assert signal["reasoning"].startswith("[demo]") and signal["ticker"] == "AAPL"
    assert "ROE 평균" in signal["reasoning"], "the analysts read real AAPL fundamentals"
    assert not (home / "web-demo").exists(), "free results never land in the demo workspace"
