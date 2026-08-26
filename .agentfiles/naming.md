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
- **학습된 모델 파일이 실제로 내놓는 클래스명 문자열**(`tracking2.py`의 `model.names`)은
  코드 컨벤션(camelCase)과 무관하게, **그 시점에 로드하는 체크포인트가 실제로 내놓는
  문자열과 정확히 일치**해야 함(프레임워크 강제 이름과 같은 성격 — 값을 바꾸려면 실제
  모델을 재로드해서 `model.names` 대조 후 바꿀 것, 코드만 보고 "일관성 있게" 리네임하면
  안 됨). **지금 운영 중인 `bestTop.pt`는 snake_case**(`trash_normal` 등)를 내놓으므로
  `tracking2.py`의 `EXPECTED_CLASS_NAMES`/`TRASH_CLASSES`/`TRASH_TYPE_MAP`도 snake_case를
  써야 함 — 과거에 이 값들을 camelCase로 "정리"했다가 회귀가 있었음(`.agentfiles/decisionLog.md`
  참고). **전체 camelCase 통일이 팀 목표**(2026-08-25 재확정, `autoTraining/pipelineConfig.yaml`의
  `dataset.classes`가 이미 이 목표를 반영)라 다음 재학습되는 새 TOP 모델은 camelCase
  클래스명으로 만들 예정 — 그 모델이 실제로 `bestTop.pt`를 교체하는 시점에 `tracking2.py`의
  위 세 값도 함께 camelCase로 전환할 것(전환 전까지는 설정 파일=목표(camelCase),
  `tracking2.py`=현재 운영 모델 값(snake_case)이 서로 다른 게 정상)
- **`autoTraining/models/bootstrap/best.pt`(재학습 파이프라인의 Label/Train 두 단계가 같은
  사이클에 고정해 공용으로 쓰는 기준 모델, `trainingPipeline.py`의 `pinActiveModel`/
  `getCycleModel`)는 실제로 `TrashNormal`/`TrashPaper`/`TrashRecyclables`/`TrashCoffeecup`을
  냄**(2026-08-26 `model.names` 직접 대조 확인) — camelCase 목표(`trashNormal` 등)도,
  운영 `bestTop.pt`의 snake_case도 아닌 PascalCase에 가까운 표기이고 `Coffeecup`은
  중간 대문자도 하나 빠져 있음. **의도적으로 그대로 승인된 예외**로, 이 모델을 다시
  받거나 교체하지 않는 한 리네임하지 않는다 — `autoTraining/pipelineConfig.yaml`의
  `dataset.classes`는 이 목록과 정확히 일치해야 Label 단계가 통과함(위와 동일한 규칙:
  코드 일관성을 이유로 임의로 고치지 말고 실제 `model.names`를 기준으로 맞출 것)

## 폴더 구조 (`WebApps/backend`)

레이어드 구조 — 새 파일은 역할에 맞는 폴더에 추가, 폴더 간 레이어를 건너뛰는 import 지양(예: `controllers`에서 `repositories` 직접 호출 금지, `services`를 거칠 것):

| 폴더 | 역할 |
|---|---|
| `controllers/` | HTTP 라우팅(FastAPI `APIRouter`). Jinja2 페이지는 `views.py`, API는 `api.py` |
| `services/` | 비즈니스 로직(쿨다운 판정, 모드 전환 등) |
| `repositories/` | 저장소 접근(motor 기반 MongoDB 연동, In-memory Mock 제거 완료) |
| `schemas/` | Pydantic 모델(요청/응답 스키마) |
| `streaming/` | 카메라 캡처·프레임 스트리밍 로직. `cameraManager.py` 구현됨(카메라 1대당 독립 `CameraId`, MJPEG) |
| `static/`, `templates/` | 정적 파일, Jinja2 템플릿 |

새로운 책임(예: 탐지 파이프라인, RPA 연동)이 생기면 위 표에 맞는 폴더가 없을 때만 최상위에 새 폴더 추가(`detection/`, `rpa/` 등) — 기존 폴더 하나에 억지로 우겨넣지 말 것.
