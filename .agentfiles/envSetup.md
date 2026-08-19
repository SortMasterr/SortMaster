# envSetup.md

전체 가이드(트러블슈팅 포함): `Docs/skills/envSetup/README.md` (원본, 아직 저장소에 없음 — 작성 전까지 이 문서가 유일한 기준)

## 핵심

- Python 3.11 고정
- requirements.txt 없음 — `infra/checkEnv.py`가 패키지 목록(`requiredPackages`)+자동설치+버전체크 전담
- `requiredPackages`는 전부 **정확히 버전 고정(`==`)**. 팀별로 환경이 갈리지 않게 하는 게 `infra/` 폴더의 목적이라, `>=` 하한선만 두면 설치 시점에 따라 팀원마다 실제 버전이 달라질 수 있어서 지양. 버전 올릴 땐 팀 합의 후 이 목록만 갱신
- `infra/checkEnv.py`, `infra/checkEnv.bat`는 `WebApps/backend`와 무관한 별도 `infra/` 폴더
- checkEnv.py 체크 항목: Python 버전 / 패키지 / Docker 설치 여부 / MongoDB 접속(`.env` 기준)
- 새 패키지는 `requiredPackages` 리스트에 정확한 버전으로 한 줄 추가

## 포트

| 항목 | 값 |
|---|---|
| 백엔드 | 8047 |
| MongoDB 호스트 | 27020 (컨테이너 내부 27017) |

## DB 접속 대상 (.env)

- `MONGO_HOST=<LOCAL_BACKEND_IP>`(실제 값은 Notion 참고) → 팀 배포 서버(로컬, 확정 — 인증 필요, `DB_USER`/`DB_PASSWORD`를
  배정받은 `user01`~`user05` 계정으로 채울 것 — 계정 생성/관리는 `architecture.md`의 "DB 접속" 절 참고)
- `MONGO_HOST=localhost` → 로컬 Docker(`my-mongo`, 무인증이면 `DB_USER`/`DB_PASSWORD` 비워둠)
- Compose 내부 백엔드는 컨테이너 네트워크용
  `COMPOSE_MONGO_HOST=mongo`/`COMPOSE_DB_PORT=27017`/`COMPOSE_DB_NAME=sortMasterTest`와
  비어 있는 `COMPOSE_DB_USER`/`COMPOSE_DB_PASSWORD`를 사용한다. 호스트 Python용
  `MONGO_HOST`/`DB_PORT`/`DB_*`와 혼용하지 않는다.
- `.env.example`은 안전한 로컬 기본값(`MONGO_HOST=localhost`,
  `DB_NAME=sortMasterTest`)을 제공한다.
- `checkEnv.py`와 `testDbConnection.py`는 `.env` 접속 대상에 ping만 수행한다.
  `debug/db/testCrud.py`와 `seedTestEvents.py`는 데이터를 쓰므로 loopback +
  `DB_NAME=sortMasterTest`가 아니면 실행 전에 중단한다.
- 백엔드도 startup에서 5초 제한 MongoDB `ping`과 Event 인덱스 준비를 수행한다. 실패하면
  uvicorn startup을 중단하며, shutdown에서는 연결 풀을 닫는다.
