# 03. 아키텍처 설계

## 1. 전체 구조

```
┌──────────────────────────── 브라우저 ────────────────────────────┐
│  React 19 + TypeScript + Vite (SPA)                              │
│  대시보드 · 맨데이트 · 백테스트 · 페이퍼 펀드 · 설정             │
└───────────────▲──────────────────────────────────────────────────┘
                │ REST/JSON  (/api/*, 작업은 폴링)
┌───────────────┴──────────────────────────────────────────────────┐
│  FastAPI (backend/app)                                           │
│  ├─ api/        라우터: settings · catalog · mandates ·          │
│  │              backtests · funds · jobs                         │
│  ├─ services/   유스케이스: 저장소 읽기/쓰기, 뷰 모델 조립       │
│  ├─ jobs.py     단일 워커 작업 큐(진행률·결과·오류)              │
│  └─ engine/     ★ aihf 와의 유일한 접점                          │
│       ├─ workspace.py  모드별 디렉터리(mandates/paper/research)  │
│       ├─ runtime.py    모드별 DataClient · Fund 조립             │
│       └─ demo.py       DemoDataClient · DemoLLM                  │
└───────────────▲──────────────────────────────────────────────────┘
                │ Python import (수정 없음, aihf==2.7.2)
┌───────────────┴──────────────────────────────────────────────────┐
│  aihf 엔진: FundSpec · backtest_fund · deploy/tick · Ledger ·    │
│             score · FDClient · make_llm                          │
└───────────────▲──────────────────────────────────────────────────┘
                │ 파일
        ~/.hedge-fund/            (live — TUI/CLI와 공유)
        ~/.hedge-fund/web-demo/   (demo — 격리)
```

## 2. 설계 원칙

1. **엔진은 블랙박스로 둔다.** 포크하지 않고 PyPI 패키지를 의존한다. 엔진 타입(`FundSpec`, `SessionRecord`, `FundBacktestResult`)이 곧 저장 포맷이며 웹 계층은 이를 그대로 직렬화하거나 화면용으로 요약만 한다.
2. **접점 격리.** `hedge_fund.*` import는 `app/engine/`과 `app/services/`에만 둔다. 업스트림이 바뀌면 이 두 곳만 고친다.
3. **모드는 조립 단계에서만 갈린다.** demo와 live의 차이는 "어떤 DataClient/LLM을 주입하느냐"와 "어느 디렉터리를 쓰느냐"뿐이고, 이후 `backtest_fund` / `tick` 호출 코드는 동일하다. 업스트림의 "one engine, three modes" 철학을 그대로 따른다.
4. **상태는 파일이 진실.** 서버 메모리에는 작업 큐 상태만 둔다. 서버를 재시작해도 맨데이트·결과·원장은 그대로다.

## 3. 모드

| | demo | live |
| --- | --- | --- |
| 데이터 | `DemoDataClient` — 티커를 시드로 한 결정적 합성 시세·재무·실적 | `CachedDataClient(FDClient())` |
| LLM 에이전트 | `DemoLLM` — 프롬프트의 재무 지표를 읽어 페르소나별 규칙으로 JSON 응답, 논거에 `[demo]` 접두 | `make_llm()` (선택 모델, 업스트림 그대로) |
| 백테스트 블라인드 | 미사용(외부 breakpoints 다운로드 불필요) | `Fund(spec, blind=True)` |
| 저장소 | `~/.hedge-fund/web-demo/` | `~/.hedge-fund/` |
| 페이퍼 첫 세션 | 90일 전으로 백데이트(바로 여러 세션 체험) | 가장 최근 완료 세션(업스트림 동작) |

모드와 선택 모델은 `~/.hedge-fund/web-settings.json`에 저장한다. 환경변수 `AIHF_WEB_HOME`으로 루트를 바꿀 수 있다(테스트가 사용).

### 데모 데이터 생성 규칙

- 시세: 평일만 존재하는 기하 랜덤워크. 티커 해시로 시드·드리프트·변동성을 정하므로 같은 티커는 항상 같은 곡선. 시장 공통 요인을 섞어 종목 간 상관을 만든다.
- 재무: 분기 간격 TTM 행. `filing_date = 분기말 + 35일`로 두고 `end_date` 이전에 공시된 행만 반환 → **시점 정합 규약을 데모에서도 지킨다.**
- 실적: 분기마다 8-K 1건, BEAT/MISS/MEET은 해시로 결정 → PEAD 모델이 실제로 발화한다.

## 4. 작업 큐

LLM이 끼면 백테스트·틱은 수십 초 이상 걸린다. 요청-응답으로 묶지 않는다.

```
POST /api/backtests ──► Job(queued) ──► worker thread ──► running(progress n/N, 중간 곡선)
                                                      └─► succeeded(result_id) | failed(error)
GET  /api/jobs/{id}  ◄── 프런트가 0.7초 간격 폴링
```

- `ThreadPoolExecutor(max_workers=1)`: 엔진 작업 직렬화(NFR-2). 같은 원장을 두 요청이 동시에 전진시키는 경합을 원천 차단.
- 진행률은 `backtest_fund(on_valuation=…)` 콜백으로 갱신.
- SSE/WebSocket 대신 폴링을 택한 이유: 프록시·단일 프로세스 서빙에서 가장 단순하고, 갱신 주기가 초 단위면 충분.
- 작업 기록은 메모리(최근 50건). 결과물 자체는 파일로 남는다.

## 5. 디렉터리 구조

```
backend/
  pyproject.toml            aihf==2.7.2, fastapi, uvicorn
  app/
    main.py                 앱 팩토리, 라우터 등록, 정적 파일(SPA) 서빙
    config.py               루트 경로, 모드/모델 설정 파일
    jobs.py                 작업 큐
    engine/                 workspace · runtime · demo
    services/               catalog · mandates · backtests · funds · views · settings
    api/                    라우터
  tests/                    pytest (데모 엔진, 임시 홈)
frontend/
  src/
    api/                    타입 + fetch 클라이언트
    components/             차트, 표, 레이아웃, 세션 상세
    pages/                  Dashboard · Mandates · MandateBuilder · Backtests ·
                            BacktestReport · Funds · FundConsole · Settings
docs/                       기획~검증 문서
```

## 6. 기술 선택

| 영역 | 선택 | 이유 |
| --- | --- | --- |
| 백엔드 | FastAPI + Uvicorn | 엔진이 Pydantic v2 → 모델을 그대로 응답 스키마로 사용 |
| 패키지 | uv, Python 3.12 | `aihf`가 numpy 1.x 고정 → 3.13 휠 없음, 3.12 사용 |
| 프런트 | React + TypeScript + Vite | 정적 빌드 후 백엔드가 그대로 서빙(단일 프로세스) |
| 라우팅 | react-router | 리포트·펀드 상세의 딥링크 |
| 차트 | 직접 그린 SVG | 선 2개·막대 수준이라 의존성 없이 테마·접근성 통제 |
| 스타일 | CSS 변수 토큰(라이트/다크) | 프레임워크 없이 가볍게 |

## 7. 보안 메모

- 인증이 없다. **로컬 단일 사용자 도구**로 설계했고 기본 바인딩은 `127.0.0.1`이다. 외부에 노출하지 말 것.
- 키는 업스트림과 같은 `~/.hedge-fund/.env`(0600)에 저장하고 API는 마스킹 값만 돌려준다.
- 이름 파라미터(맨데이트/펀드/결과 ID)는 `[A-Za-z0-9][A-Za-z0-9._-]*` 검증 후에만 경로로 쓴다.
