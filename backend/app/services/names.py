"""Validation of names that become file names or tickers."""

from __future__ import annotations

import re

from hedge_fund.fund import normalize_universe

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_TICKER = re.compile(r"[A-Z][A-Z0-9.\-]{0,9}")


class InvalidName(ValueError):
    pass


def safe_name(name: str, what: str = "이름") -> str:
    """A name used as a path component: no separators, nothing hidden."""
    if not _NAME.fullmatch(name) or ".." in name:
        raise InvalidName(f"잘못된 {what}: {name!r} — 영문/숫자로 시작하고 영문, 숫자, '.', '_', '-'만 쓸 수 있습니다.")
    return name


def clean_universe(tickers: list[str]) -> list[str]:
    try:
        universe = normalize_universe(tickers)
    except ValueError:
        raise InvalidName("유니버스가 비어 있습니다. 종목을 하나 이상 지정하세요.") from None
    for ticker in universe:
        if not _TICKER.fullmatch(ticker):
            raise InvalidName(f"잘못된 티커: {ticker!r}")
    if len(universe) > 50:
        raise InvalidName("유니버스는 50종목까지 지정할 수 있습니다.")
    return universe
