# naming.md — 네이밍 룰 요약

> 전체 표/예시는 `Docs/skills/naming/namingRules.xlsx` 참고 (원본).
> 이 파일은 AI가 빠르게 참고할 핵심 규칙만 요약.

## 핵심 규칙

- **카멜케이스로 전면 통일**: 변수명, 함수명, **파일명까지** 전부 `camelCase`
  - 예: `camera_manager.py` → `cameraManager.py`, `check_env.py` → `checkEnv.py`
- 모듈 전역 상수도 `UPPER_SNAKE_CASE` 대신 camelCase
  - 예: `REQUIRED_PYTHON` → `requiredPython`
- 클래스명은 **PascalCase** 유지 (카멜케이스 규칙 예외)

## 예외 (카멜케이스 적용 안 함)

- 클래스명 (PascalCase)
- Pydantic/FastAPI 등 프레임워크가 강제하는 이름 (`model_config` 등)
- `README.md`, `.env`, `.gitignore` 등 관례상 정해진 파일명
- Enum 멤버 식별자 (예: `CameraId.ELEV_01`) — 값(value)은 이미 `"ELEV-01"`로 고정
- 환경변수 키(`.env`의 `MONGO_HOST` 등)는 셸/OS 관례상 `SCREAMING_SNAKE_CASE` 유지

자세한 대상별 규칙, Before→After 전체 예시는 `Docs/skills/naming/namingRules.xlsx`에서 확인.
