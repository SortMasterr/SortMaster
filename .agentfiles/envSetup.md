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

- `MONGO_HOST=192.168.0.30` → 팀 공유 서버
- `MONGO_HOST=localhost` → 로컬 Docker(`my-mongo`)
- checkEnv.py/testDbConnection.py/testCrud.py 세 스크립트가 `.env` 키 공유 — 값 다르면 결과 엇갈림
