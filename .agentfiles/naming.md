# naming.md

전체 표/예시: `Docs/skills/naming/namingRules.xlsx` (원본, 아직 저장소에 없음 — 작성 전까지 이 문서가 유일한 기준)

## 규칙

- 변수명/함수명/파일명 전부 camelCase (`camera_manager.py`→`cameraManager.py`, `check_env.py`→`checkEnv.py`)
- 모듈 전역 상수도 camelCase (`REQUIRED_PYTHON`→`requiredPython`)
- 클래스명은 PascalCase 유지

## 예외

- 클래스명(PascalCase), 프레임워크 강제 이름(`model_config` 등)
- `README.md`/`.env`/`.gitignore` 등 관례적 파일명
- Enum 멤버 식별자(`CameraId.ELEV_01`), 값은 `"ELEV-01"` 고정
- 환경변수 키(`.env`의 `MONGO_HOST` 등)는 SCREAMING_SNAKE_CASE 유지
- Docker 이미지/컨테이너 이름은 케밥케이스(`sortmaster-backend`) — Docker 이미지 이름은 대문자 자체가 불가능(소문자+`.`/`_`/`-`만 허용)하고, Docker 생태계 관례와도 일치
