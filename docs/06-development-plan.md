# 06. 개발 계획

## 단계

| 단계 | 내용 | 완료 기준 |
| --- | --- | --- |
| M0 정리 | 기존 Spring 실습 코드 제거, 저장소 골격 | 빈 트리 + `backend/` `frontend/` `docs/` |
| M1 기획·설계 | 문서 01~06 | 문서 커밋 |
| M2 엔진 접점 | workspace · 데모 데이터/LLM · runtime | 데모 백테스트가 파이썬에서 끝까지 돈다 |
| M3 API | 설정·카탈로그·맨데이트·백테스트·펀드·작업 | pytest 통과, `/docs` 확인 |
| M4 UI | 8개 화면 + 차트 + 세션 상세 | 타입체크·빌드 통과 |
| M5 검증 | 브라우저 E2E 스모크(Playwright), 스크린샷 확인 | 핵심 시나리오 3종 통과 |
| M6 마감 | README, 개발 일지, 테스트 리포트, 노션 정리 | 푸시 완료 |

## 작업 분해 (M2~M4)

- M2: `DemoDataClient`(시세·재무·실적·기업정보), `DemoLLM`, `Workspace`, `Runtime.build_data()/build_fund()`
- M3: 서비스 계층(`views`가 `SessionRecord` → 화면용 요약 변환), 작업 큐, 라우터 6개, 오류 매핑
- M4: API 클라이언트·타입, 레이아웃, 공통 부품(KPI·표·차트·신호 칩), 페이지 순서 = 설정 → 맨데이트 → 백테스트 → 펀드 → 대시보드

## 테스트 전략

| 층 | 도구 | 범위 |
| --- | --- | --- |
| 엔진 접점 | pytest | 데모 데이터의 결정성·시점 정합, 데모 LLM 응답 형식 |
| API | pytest + FastAPI TestClient | 전 엔드포인트 정상/오류 경로, 백테스트·틱 작업 완료까지 |
| 프런트 | `tsc`, `vite build` | 타입·번들 |
| E2E | Playwright(Chromium) | 맨데이트 생성 → 백테스트 → 리포트 → 펀드 배치·실행 |

LIVE 경로(실제 Financial Datasets / LLM 호출)는 키가 없어 자동 검증 대상에서 제외하고, 문서에 미검증으로 표기한다.
