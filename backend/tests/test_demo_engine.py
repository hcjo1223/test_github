"""The synthetic data must honour the engine's contracts."""

import json

from hedge_fund.data import DataClient
from hedge_fund.llm import LLMClient

from app.engine.demo import DemoDataClient, DemoLLM


def test_demo_client_satisfies_the_engine_protocols():
    assert isinstance(DemoDataClient(), DataClient)
    assert isinstance(DemoLLM(), LLMClient)


def test_prices_are_deterministic_weekdays_inside_the_window():
    first = DemoDataClient().get_prices("AAPL", "2025-01-01", "2025-03-31")
    second = DemoDataClient().get_prices("AAPL", "2025-01-01", "2025-03-31")
    assert [bar.close for bar in first] == [bar.close for bar in second]
    assert first, "a quarter of history has bars"
    assert all("2025-01-01" <= bar.time[:10] <= "2025-03-31" for bar in first)
    assert all(bar.close > 0 and bar.low <= bar.close <= bar.high for bar in first)
    assert DemoDataClient().get_prices("MSFT", "2025-01-01", "2025-03-31")[0].close != first[0].close


def test_no_price_from_the_future():
    assert DemoDataClient().get_prices("AAPL", "2039-01-01", "2039-12-31") == []


def test_financial_metrics_are_point_in_time():
    data = DemoDataClient()
    rows = data.get_financial_metrics("AAPL", "2025-06-30", limit=8)
    assert len(rows) == 8
    assert all(row.filing_date <= "2025-06-30" for row in rows), "nothing filed after the as-of date"
    assert [row.report_period for row in rows] == sorted((row.report_period for row in rows), reverse=True)
    earlier = data.get_financial_metrics("AAPL", "2025-01-15", limit=8)
    assert earlier[0].report_period < rows[0].report_period


def test_earnings_history_is_newest_first_with_surprises():
    records = DemoDataClient().get_earnings_history("NVDA", limit=8)
    assert len(records) == 8
    assert records[0].filing_date > records[-1].filing_date
    assert {record.quarterly.eps_surprise for record in records} <= {"BEAT", "MISS", "MEET"}


def test_demo_llm_answers_in_the_agent_contract():
    prompt = (
        "Summary:\n  ROE avg: 0.30  |  Net margin avg: 0.25\n"
        "  Gross margin trend (latest-oldest): 0.03\n  Debt/equity (latest): 0.20\n"
        "period | filed | mktcap | P/E | ROE | gross_m | op_m | net_m | D/E | curr | rev_gr | EPS | BVPS | FCF/sh\n"
        "2025-03-31 | 2025-05-05 | 1.0B | 9.00 | 0.30 | 0.60 | 0.40 | 0.25 | 0.20 | 2.50 | 0.20 | 5.00 | 20.00 | 4.50"
    )
    answer = json.loads(DemoLLM().complete("You are Warren Buffett, evaluating", prompt))
    assert answer["signal"] == "bullish"
    assert 0 <= answer["confidence"] <= 100
    assert answer["reasoning"].startswith("[demo]")

    weak = prompt.replace("0.30", "0.02").replace("0.25", "0.01").replace("9.00", "55.00").replace("0.20", "2.80")
    assert json.loads(DemoLLM().complete("You are Benjamin Graham", weak))["signal"] == "bearish"
