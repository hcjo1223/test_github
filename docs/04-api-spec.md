# 04. API 명세

- Base: `/api` · JSON · 오류는 `{"detail": "<메시지>"}` (검증 오류 422, 없음 404, 충돌 409, 실행 불가 400)
- 자동 문서: 서버 실행 후 `/docs` (OpenAPI)

## 상태·설정

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/health` | `{status, version, aihf_version, mode}` |
| GET | `/settings` | 모드, 모델, 키 등록 현황(마스킹), live 가능 여부와 막는 이유 |
| PUT | `/settings` | `{mode?, model?}` — live 전환은 데이터 키 필요(400) |
| PUT | `/settings/credentials` | `{env_var, value}` — 허용된 환경변수 이름만 |
| GET | `/catalog` | 애널리스트·전략 라이브러리·모델·유니버스 프리셋·기본값 |

## 맨데이트

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/mandates` | 요약 목록(+ 최근 백테스트 성과, 깨진 파일은 `error`) |
| GET | `/mandates/{name}` | `FundSpec` 전체 |
| POST | `/mandates` | `FundSpec` JSON. 201 / 409(이름 중복) / 422(검증 실패) |
| DELETE | `/mandates/{name}` | 204 |

## 백테스트

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| POST | `/backtests` | `{mandate, universe[], start?, end?}` → 202 `{job_id}` |
| GET | `/backtests` | 저장된 결과 요약(최신순) |
| GET | `/backtests/{id}` | 리포트 뷰: 지표, 곡선(dates/nav/benchmark_nav/drawdown), 세션 요약, 최종 포지션, 성적표 |
| GET | `/backtests/{id}/sessions/{session}` | 세션 상세(결정·체결 전체) |
| DELETE | `/backtests/{id}` | 204 |

## 페이퍼 펀드

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/funds` | 펀드 요약 목록 |
| POST | `/funds` | `{name, mandate, universe[]}` → 201 |
| GET | `/funds/{name}` | 상세: 스펙, NAV 이력, 포지션, 대기 결정, 세션 요약, 이벤트, 정지 사유 |
| GET | `/funds/{name}/preview` | 다음 실행 세션(`due`)과 그때 체결될 결정. 없으면 `due=null` + 사유 |
| POST | `/funds/{name}/tick` | `{count?=1(≤60), session?}` → 202 `{job_id}` |
| POST | `/funds/{name}/halt` | `{reason}` |
| POST | `/funds/{name}/resume` | |
| GET | `/funds/{name}/sessions/{session}` | 세션 상세 |
| GET | `/funds/{name}/scorecard` | 성적표(세션 없으면 404) |

## 작업

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/jobs/{id}` | `{id, kind, status, label, progress{done,total}, partial{dates,nav,benchmark_nav}, result, error}` |

`status`: `queued → running → succeeded | failed`. 성공 시 `result`는 백테스트 `{backtest_id}`, 틱 `{sessions: [...], stopped_reason?}`.

## 주요 뷰 모델

```jsonc
// GET /backtests/{id}
{
  "id": "example-fund-2025-11-03-2026-11-13-20261117-101500",
  "fund": "example-fund", "universe": ["AAPL","MSFT"], "benchmark": "SPY",
  "start": "...", "end": "...", "rebalance": "weekly", "capital": 100000,
  "metrics": { /* FundBacktestMetrics 그대로 */ },
  "dates": [], "nav": [], "benchmark_nav": [], "drawdown": [],
  "sessions": [ { "session": "...", "nav": 0, "rebalance": true,
                  "executed": { "as_of": "...", "n_orders": 3, "traded_notional": 0, "trading_cost": 0 } | null,
                  "decided": { "n_signals": 6, "n_clamps": 1, "stopped_out": false } | null } ],
  "positions": [ { "ticker": "AAPL", "shares": 10, "mark": 0, "value": 0, "weight": 0 } ],
  "cash": 0,
  "scorecard": { /* Scorecard 그대로 */ }
}
```

세션 상세는 업스트림 `SessionRecord`를 그대로 내려 주되, 레코드마다 반복되는 `spec` 사본은 응답에서 뺀다(용량).
