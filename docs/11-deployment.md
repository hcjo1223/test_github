# 11. 배포 (본인 전용 비공개 인스턴스)

한 명(본인)만 쓰는 비공개 배포. 로그인 비밀번호 1개로 보호되며, 방문자 계정·결제·공개 가입은 없다.

## 구성

- 도커 이미지 1개: 빌드된 UI와 API를 한 프로세스가 함께 서빙한다.
- 영구 볼륨을 `/data`에 마운트한다. 설정(`web-settings.json`), API 키(`.env`), 맨데이트, 백테스트 결과, 원장, 캐시가 모두 여기에 있다.
- 비밀번호는 플랫폼 시크릿 `AIHF_PASSWORD`로만 넣는다. 이미지와 저장소에는 없다.

## 환경변수

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `AIHF_PASSWORD` | 예 | 로그인 비밀번호. 12자 이상. 이미지가 `AIHF_REQUIRE_AUTH=1`이라 없으면 서버가 시작되지 않는다 |
| `PORT` | 플랫폼이 설정 | 기본 8000 |
| `AIHF_WEB_HOME` | 기본 `/data` | 데이터 위치. 볼륨 경로와 맞출 것 |
| `AIHF_COOKIE_SECURE` | 기본 1 | HTTPS 뒤에서 쿠키를 보안 전용으로 표시 |

API 키(Financial Datasets, LLM 제공사)와 SEC 연락처는 환경변수가 아니라 **배포 후 설정 화면에서 입력**한다. 그러면 `/data/.env`(권한 0600)와 `/data/web-settings.json`에 저장된다.

## 로컬에서 먼저 확인

```bash
docker build -t aihf-web .
docker run --rm -p 8000:8000 -e AIHF_PASSWORD='본인이 정한 12자 이상 비밀번호' \
  -v aihf-data:/data aihf-web
# 브라우저: http://localhost:8000  → 로그인 화면이 떠야 한다
# AIHF_COOKIE_SECURE=1 이면 http://localhost에서는 로그인 쿠키가 저장되지 않는다.
# 로컬 확인 시에만 -e AIHF_COOKIE_SECURE=0 을 추가한다.
```

## 플랫폼에 올리기 (Render / Fly.io / Railway / VPS 공통)

1. 저장소를 연결하고 Dockerfile로 빌드한다.
2. 영구 볼륨을 `/data`에 붙인다(Render: Disk, Fly: volume, Railway: Volume).
3. 시크릿 `AIHF_PASSWORD`를 등록한다.
4. 포트 8000을 HTTPS 도메인에 연결한다. 헬스 체크 경로는 `/api/health`.
5. 배포 후 브라우저에서 로그인하고 설정 화면에서 API 키를 입력한다.

## 보안 점검표

- [ ] `AIHF_PASSWORD`가 12자 이상이고 저장소·채팅·문서 어디에도 없다
- [ ] 도메인이 HTTPS로만 열린다(쿠키 보안 설정이 HTTP에서는 동작하지 않는다)
- [ ] `/data`가 영구 볼륨이며 백업 방법이 있다
- [ ] 로그인 없이 `/api/mandates`가 401을 돌려준다
- [ ] 무료 데이터 모드는 본인 판단 아래에서만 쓴다(Yahoo 시세는 비공식)

## 알려진 한계

- 로그인은 비밀번호 1개와 쿠키 세션이다. 다중 사용자나 2단계 인증은 없다.
- 로그인 실패 시 0.5초 지연으로 추측을 늦추지만, 속도 제한은 없다. 이 정도면 개인용에 충분하지만 공개 서비스에는 부족하다.
- 작업 상태는 메모리에만 있다. 재배포 중에는 진행 중인 백테스트가 사라지고, 결과와 원장은 볼륨에 남는다.
- 비공개라도 데이터 라이선스는 적용된다. 본인 사용은 Credits(개인 라이선스)로 충분하지만, 다른 사람에게 보여 주거나 서비스로 제공하면 Professional 이상이 필요하다.
- 도커 빌드는 이 환경에 도커가 없어 실제로 빌드하지 못했다. 빌드 명령과 단계는 `docs/11`과 Dockerfile 그대로이며, 처음 배포할 때 확인이 필요하다.
