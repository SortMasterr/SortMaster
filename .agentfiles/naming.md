# naming.md

전체 표/예시: `Docs/skills/naming/namingRules.xlsx` (원본, 아직 저장소에 없음 — 작성 전까지 이 문서가 유일한 기준)

## 규칙

- 변수명/함수명/파일명 전부 camelCase (`camera_manager.py`→`cameraManager.py`, `check_env.py`→`checkEnv.py`)
- 모듈 전역 상수도 camelCase (`REQUIRED_PYTHON`→`requiredPython`)
- 클래스명은 PascalCase 유지

## 예외

- 클래스명(PascalCase), 프레임워크 강제 이름(`model_config` 등)
- Python 내부용 식별자의 선행 언더스코어는 공개 범위 표시이므로 camelCase와 별개로 허용
  (`_buildDateQuery`, `_client` 등 `_camelCase` 형태)
- `README.md`/`.env`/`.gitignore` 등 관례적 파일명
- Enum 멤버 식별자(`CameraId.ELEVTOP`), 값은 `"ELEV-TOP"` 고정
- 환경변수 키(`.env`의 `MONGO_HOST` 등)는 SCREAMING_SNAKE_CASE 유지
- Docker 이미지/컨테이너 이름은 케밥케이스(`sortmaster-backend`) — Docker 이미지 이름은 대문자 자체가 불가능(소문자+`.`/`_`/`-`만 허용)하고, Docker 생태계 관례와도 일치
- GPU 서버 스크립트 및 학습 파이프라인과 연동되는 모델 가중치·산출물 파일명은 Python·학습 도구 관례와 기존 연동을 우선해 snake_case 허용
  (`best_side.pt` 등). 이름을 바꾸려면 GPU 서버 스크립트와 모든 참조 위치를 함께 변경
- **TOP 모델(`bestTop.pt`)이 내놓는 클래스명 문자열**(`tracking2.py`의 `model.names` — 예:
  `trash_normal`)은 **snake_case로 영구 고정**(2026-08-25 팀 결정) — camelCase 변환
  대상이 아님(프레임워크 강제 이름과 같은 성격). 재학습해도 이 표기는 바꾸지 않기로
  확정했으므로, `tracking2.py`의 `EXPECTED_CLASS_NAMES`/`TRASH_CLASSES`/`TRASH_TYPE_MAP`과
  `autoTraining/pipelineConfig.yaml`의 `dataset.classes` 전부 이 문자열을 그대로 써야 함
  — 과거에 이 값들을 camelCase로 "정리"했다가 `model.names`와 안 맞아서 모든 감지가
  조용히 무시되는 회귀가 있었음(`.agentfiles/decisionLog.md` 참고)

## 폴더 구조 (`WebApps/backend`)

레이어드 구조 — 새 파일은 역할에 맞는 폴더에 추가, 폴더 간 레이어를 건너뛰는 import 지양(예: `controllers`에서 `repositories` 직접 호출 금지, `services`를 거칠 것):

| 폴더 | 역할 |
|---|---|
| `controllers/` | HTTP 라우팅(FastAPI `APIRouter`). Jinja2 페이지는 `views.py`, API는 `api.py` |
| `services/` | 비즈니스 로직(쿨다운 판정, 모드 전환 등) |
| `repositories/` | 저장소 접근(현재 In-memory, 추후 motor/MongoDB) |
| `schemas/` | Pydantic 모델(요청/응답 스키마) |
| `streaming/` | 카메라 캡처·프레임 스트리밍 로직. `cameraManager.py` 구현됨(카메라 1대당 독립 `CameraId`, MJPEG) |
| `static/`, `templates/` | 정적 파일, Jinja2 템플릿 |

새로운 책임(예: 탐지 파이프라인, RPA 연동)이 생기면 위 표에 맞는 폴더가 없을 때만 최상위에 새 폴더 추가(`detection/`, `rpa/` 등) — 기존 폴더 하나에 억지로 우겨넣지 말 것.
