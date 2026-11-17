"""The statement reader behind tools/verify_against_filings.py, on tables shaped
like SEC's: dollar signs and parentheses live in their own cells."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import verify_against_filings as v  # noqa: E402


def cells(label, *values):
    out = f"<tr><td>{label}</td>"
    for value in values:
        out += "<td>$</td>" if value.startswith("$") else ""
        digits = value.lstrip("$")
        out += f"<td>({digits.strip('()')}</td><td>)</td>" if digits.startswith("(") else f"<td>{digits}</td>"
    return out + "</tr>"


INCOME_10Q = "<table>" + "".join([
    cells("Total net sales", "$100,000", "$90,000", "$280,000", "$250,000"),
    cells("Gross margin", "46,000", "41,000", "130,000", "112,000"),
    cells("Operating income", "30,000", "26,000", "85,000", "70,000"),
    cells("Net income", "$25,000", "$22,000", "$70,000", "$60,000"),
    "<tr><td>Earnings per share:</td></tr>",
    cells("Diluted", "$1.70", "$1.40", "$4.60", "$3.80"),
    "<tr><td>Shares used in computing earnings per share:</td></tr>",
    cells("Diluted", "15,000", "15,500", "15,100", "15,600"),
]) + "</table>"
INCOME_10K = "<table>" + "".join([
    cells("Total net sales", "$400,000", "$370,000", "$350,000"),
    cells("Gross margin", "180,000", "165,000", "150,000"),
    cells("Operating income", "120,000", "110,000", "100,000"),
    cells("Net income", "$95,000", "$90,000", "$85,000"),
    cells("Diluted", "$6.10", "$5.70", "$5.20"),
]) + "</table>"
BALANCE = "<table>" + "".join([
    cells("Total current assets", "$150,000", "$140,000"),
    cells("Total assets", "$350,000", "$340,000"),
    cells("Total current liabilities", "$160,000", "$150,000"),
    cells("Commercial paper", "$5,000", "$4,000"),
    cells("Term debt", "9,000", "8,000"),
    cells("Term debt", "70,000", "72,000"),
    cells("Total liabilities", "$270,000", "$260,000"),
    cells("Total shareholders’ equity", "$80,000", "$80,000"),
]) + "</table>"


def filing(form, income):
    parser = v.Tables()
    parser.feed(income + "<p>noise</p>" + BALANCE)
    return v.Filing(form, "2026-06-27", v.statement(parser.tables, ["net income", "operating income"]),
                    v.statement(parser.tables, ["total assets", "total liabilities"]))


def test_rows_read_dollar_signs_and_negatives():
    assert v.parse_row(["Net income", "$", "1,234", "(", "56", ")"]) == ("Net income", [1234.0, -56.0])
    assert v.parse_row(["Diluted", "$", "1.70"]) == ("Diluted", [1.70])
    assert v.parse_row(["Other", "—", "12"]) == ("Other", [12.0])


def test_year_to_date_columns_are_chosen_by_form():
    quarter = filing("10-Q", INCOME_10Q)
    assert quarter.flow(*v.NET) == (70_000, 60_000), "the nine months, not the quarter"
    assert filing("10-K", INCOME_10K).flow(*v.NET) == (95_000, 90_000), "the year and the year before"
    first_quarter = filing("10-Q", "<table>" + cells("Net income", "$7,000", "$6,000") + cells("Operating income", "9,000", "8,000") + "</table>")
    assert first_quarter.flow(*v.NET) == (7_000, 6_000), "in the first quarter the quarter is the year to date"


def test_eps_skips_the_share_count_row():
    assert filing("10-Q", INCOME_10Q).flow(*v.EPS, small=True) == (4.60, 3.80)


def test_ttm_is_year_to_date_plus_last_year_minus_prior_year_to_date():
    quarter, annual = filing("10-Q", INCOME_10Q), filing("10-K", INCOME_10K)
    assert v.ttm_from_filings(quarter, annual, *v.NET) == 70_000 + 95_000 - 60_000
    assert v.ttm_from_filings(annual, None, *v.NET) == 95_000


def test_balance_sheet_items_and_total_debt():
    balance = filing("10-K", INCOME_10K)
    assert balance.instant(r"total (share|stock)holders[’'] equity") == 80_000
    assert balance.instant(r"total current assets") == 150_000
    assert balance.debt() == 5_000 + 9_000 + 70_000, "both 'Term debt' rows and the commercial paper"


def test_the_audited_statement_wins_over_the_mdna_summary():
    """MD&A repeats revenue, operating income and net income in a short table
    with a % change column; the reader must take the long, audited one."""
    summary = "<table>" + cells("Revenue", "$331,839", "$281,724", "18%") + cells("Operating income", "155,237", "128,528", "21%") \
        + cells("Net income", "133,749", "101,832", "31%") + cells("Diluted earnings per share", "$18.20", "$13.64", "33%") + "</table>"
    statement = "<table>" + cells("Total revenue", "$331,839", "$281,724", "$245,122") + cells("Gross margin", "225,465", "193,893", "171,008") \
        + cells("Operating income", "155,237", "128,528", "109,433") + cells("Net income", "133,749", "101,832", "88,136") \
        + cells("Diluted", "$18.20", "$13.64", "$11.80") + cells("Other income", "1", "2", "3") + "</table>"
    parser = v.Tables()
    parser.feed(summary + statement + BALANCE)
    filing = v.Filing("10-K", "2026-06-30", v.statement(parser.tables, ["net income", "operating income"]), {})
    assert filing.flow(*v.REVENUE) == (331_839, 281_724)
    assert filing.flow(*v.EPS, small=True) == (18.20, 13.64)


def test_eps_row_named_diluted_earnings_per_share():
    table = "<table>" + cells("Net income", "1", "2") + cells("Operating income", "1", "2") + cells("Diluted earnings per share", "$1.50", "$1.20") + "</table>"
    parser = v.Tables()
    parser.feed(table)
    income = v.statement(parser.tables, ["net income", "operating income"])
    assert v.pick(income, *v.EPS, small=True) == [1.50, 1.20]
