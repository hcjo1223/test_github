"""What a reader must know about the data behind a result, by mode."""

from __future__ import annotations

from hedge_fund.fund import FundSpec

FREE_NOTES = [
    "무료 데이터(SEC EDGAR 재무 + Yahoo 시세)입니다. 재무는 공시일 기준 시점 정합이지만 XBRL 태그로 재구성한 근사값이며, 결측이 있을 수 있습니다.",
    "시세는 비공식 Yahoo 엔드포인트의 분할 조정 종가(배당 미조정)입니다.",
    "애널리스트 추정치가 없어 실적 서프라이즈가 없습니다. PEAD(post-earnings drift) 모델은 신호를 내지 않습니다.",
]
FREE_DEMO_LLM = "선택한 모델의 API 키가 없어 투자자 에이전트는 규칙 기반 휴리스틱(`[demo]` 표기)으로 동작합니다. 논거는 LLM이 아닙니다."


def data_notes(mode: str, spec: FundSpec | None = None, demo_llm: bool = False) -> list[str]:
    """Caveats shown beside results. Empty for live."""
    if mode != "free":
        return []
    notes = list(FREE_NOTES)
    if demo_llm:
        notes.append(FREE_DEMO_LLM)
    if spec is not None and any(m.name == "pead" for s in spec.strategies for m in s.models):
        notes.append("이 맨데이트의 PEAD 전략은 이 모드에서 거래 신호를 만들지 않습니다.")
    return notes
