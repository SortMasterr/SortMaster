# envSetup.md

전체 가이드(트러블슈팅 포함): `Docs/skills/envSetup/README.md` (원본)

## 핵심

- Python 3.11 고정
- requirements.txt 없음 — `infra/checkEnv.py`가 패키지 목록(`requiredPackages`)+자동설치+버전체크 전담
- `infra/checkEnv.py`, `infra/checkEnv.bat`는 `WebApps/backend`와 무관한 별도 `infra/` 폴더
- checkEnv.py 체크 항목: Python 버전 / 패키지 / Docker 설치 여부 / MongoDB 접속(`.env` 기준)
- 새 패키지는 `requiredPackages` 리스트에 한 줄 추가

## 포트

| 항목 | 값 |
|---|---|
| 백엔드 | 8047 |
| MongoDB 호스트 | 27020 (컨테이너 내부 27017) |

## DB 접속 대상 (.env)

- `MONGO_HOST=192.168.0.30` → 팀 공유 서버
- `MONGO_HOST=localhost` → 로컬 Docker(`my-mongo`)
- checkEnv.py/testDbConnection.py/testCrud.py 세 스크립트가 `.env` 키 공유 — 값 다르면 결과 엇갈림
