# envSetup.md — 개발 환경 세팅 요약

> 전체 가이드(트러블슈팅 포함)는 `Docs/skills/envSetup/README.md` 참고 (원본).
> 이 파일은 AI가 빠르게 참고할 핵심 사실만 요약.

## 핵심 사실

- Python **3.11** 고정 (다른 마이너 버전 사용 금지)
- `requirements.txt` 없음 — `infra/checkEnv.py` 하나가 패키지 목록(`requiredPackages`)
  관리 + 자동 설치 + 버전 체크를 전부 담당
- `infra/checkEnv.py`, `infra/checkEnv.bat`는 `WebApps/backend`가 아닌
  별도 `infra/` 폴더에 위치 (backend 코드와 무관하게 독립 실행)
- `checkEnv.py`가 확인하는 것: Python 버전 / 패키지 설치+버전 / Docker 설치 여부 /
  MongoDB 접속(`.env`의 `MONGO_HOST` 등 기준)
- 새 패키지 필요 시 `checkEnv.py`의 `requiredPackages` 리스트에 한 줄만 추가

## 포트

| 항목 | 값 |
|---|---|
| 백엔드 서버 | 8047 |
| MongoDB 호스트 포트 | 27020 (컨테이너 내부 27017) |

## DB 접속 대상 (.env)

- `MONGO_HOST=192.168.0.30` → 팀 공유 서버
- `MONGO_HOST=localhost` → 본인 로컬 Docker(`my-mongo`)
- `infra/checkEnv.py` / `debug/testDbConnection.py` / `debug/testCrud.py`
  세 스크립트가 모두 같은 `.env` 키를 공유하므로, 서로 다른 값이면 결과가
  엇갈릴 수 있음

자세한 트러블슈팅(MongoDB 접속 실패, Docker Desktop WSL2 포트 포워딩 문제 등)은
`Docs/skills/envSetup/README.md`에서 확인.
