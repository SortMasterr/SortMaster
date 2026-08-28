# CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템 (1팀)

## 개발 환경 (버전 고정)

| 항목 | 버전/값 | 비고 |
|---|---|---|
| OS | Windows (로컬 개발) | 팀 공통 |
| Python | **3.11** | CTO 권장 버전, 반드시 3.11로 통일 |
| 패키지 관리 | `venv` + `pip` | `infra/checkEnv.py`가 목록 관리(별도 requirements.txt 없음) |
| 웹 프레임워크 | FastAPI (최신 안정 버전) + `uvicorn[standard]` | 버전도 `infra/checkEnv.py`에서 관리 |
| DB 드라이버 | `motor` (비동기) | MongoDB 연동용 |
| DB 실행 | Docker | 호스트 포트 `27020`, 컨테이너 내부는 `27017` 유지 (팀 간 포트 충돌 방지) |
| MongoDB 버전 | **`mongo:7.0`** | 확정됨, `docker-compose.yml`의 `mongo` 서비스 이미지 태그 |
| Docker / Docker Compose 버전 | **Compose V2** | V1(standalone `docker-compose`) 불가, `docker compose version`으로 확인. v29.6.2/Compose v5.3.1 조합으로 빌드+구동 검증 완료 |
| 형상관리 | GitHub | 브랜치 전략은 `Docs/skills/github/README.md` 참고 |
| IDE / AI 코딩 툴 | 개인별 사용 | 팀 공통 지정 없음, 각자 편한 도구 사용 |
| 프론트엔드 | Node.js/React 사용 안 함 — Jinja2 + 바닐라 JS | 별도 런타임 설치 불필요 |

> **TBD 항목은 확정되는 대로 이 표를 업데이트해서 전원이 동일한 버전으로 맞춰야 함.**
> 특히 Python은 3.11 외 버전(3.12, 3.10 등) 사용 금지 — 라이브러리 호환성 문제 방지.
>
> **`git pull` 이후에는 반드시 `python infra/checkEnv.py`를 실행할 것.** 패키지 버전이
> 팀원마다 갈리지 않도록 `requiredPackages`를 전부 정확히 버전 고정(`==`)해뒀는데,
> pull로 새 패키지가 추가되거나 버전이 바뀌어도 직접 실행하기 전까진 반영이 안 됨.

### 필수 설치 확인

```bash
python --version   # Python 3.11.x 인지 확인
docker --version   # Docker 설치 확인
docker compose version   # Compose V2인지 확인 (V1 standalone docker-compose인 경우 버전명이 안뜸)
git --version
```

패키지는 별도 requirements.txt 없이 `infra/checkEnv.py`가 직접
설치+체크까지 담당함(또는 `infra/checkEnv.bat` 더블클릭). Python 버전·필요 패키지
자동 설치·Docker 설치 여부·MongoDB(포트 27020) 접속을 한 번에 확인.

## 실행 방법

### Windows 로컬 개발

```bat
cd WebApps/backend
python -m venv venv
venv\Scripts\activate

python ..\..\infra\checkEnv.py
:: 패키지 자동 설치 + Python/Docker/MongoDB 체크. 전부 OK가 아니면 여기서 먼저 해결

:: .env는 Notion에 공유된 팀 값을 그대로 받아 프로젝트 루트(WebApps/backend 상위)에 저장
:: 필요 시 .env 값 수정 (CAMERA_SOURCE_ELEVTOP, CAMERA_SOURCE_ELEVSIDE, MONGO_HOST 등)
:: CAMERA_SOURCE_<CameraId> — 카메라 1대당 지점 1개. ELEV-TOP만 기본값 0(로컬 웹캠 1대로 바로 됨), 나머지는 미설정 시 해당 지점만 503

uvicorn main:app --reload --port 8047
```

브라우저에서 http://localhost:8047 접속.
API 상세 스펙은 `.agentfiles/apiSpec.md` 참고.

### 테스트 실행

```bat
cd WebApps/backend
venv\Scriptsctivate
python -m pytest
```

`pytest`는 `infra/checkEnv.py`가 설치한다(별도 설치 불필요). 테스트 파일명이 프로젝트
컨벤션대로 camelCase(`testEventMediaService.py`)라 pytest 기본 탐색 패턴(`test_*.py`)에 안 걸리므로,
`WebApps/backend/pytest.ini`가 `python_files`/`python_classes`를 재정의한다 — **반드시
`WebApps/backend`에서 실행할 것**(다른 위치에서 돌리면 `no tests ran`이 뜨거나 `schemas`
import가 깨진다). MongoDB 없이 전부 mock으로 도는 단위 테스트라 DB를 띄울 필요는 없다.

RPA·debug 테스트는 저장소 루트에서 실행한다(루트 `pytest.ini`가 `RPAs`와
`debug/detection`만 대상으로 잡는다 — `debug/db/testCrud.py` 등은 pytest 테스트가 아니라
손으로 돌리는 MongoDB 스크립트라 제외했다).

```bat
python -m pytest
```

`tzdata` 미설치 상태면 보고서 RPA 테스트가 `ModuleNotFoundError: No module named 'tzdata'`로
무더기 실패한다 — `python infra/checkEnv.py`를 먼저 돌릴 것.

### Docker Compose

```bash
# .env는 프로젝트 루트에 위치해야 함(Notion 공유값)
docker compose --profile local up --build
```

- `backend`(포트 8047) + `mongo`(호스트 포트 27020) + `report-scheduler` + `collection-scheduler` 상시 기동. `report-scheduler`는 예약 보고서를, `collection-scheduler`는 FULL 감지 수거 작업의 담당자 알림·재알림·관리자 에스컬레이션을 담당
- `backend`/`mongo`/`report-scheduler`/`collection-scheduler`는 `local` profile로 묶여 있음(GPU 서버의 `inference`/`side-overflow`와 같은 파일을 공유하므로, 이름 없이 `docker compose up`을 치면 아무것도 안 뜨게 해서 잘못된 환경에서 잘못된 서비스가 뜨는 걸 방지) — 반드시 `--profile local`을 붙일 것
- 여기서 뜨는 `mongo`는 로컬 전용 별도 인스턴스 — 팀 배포 서버(`<LOCAL_BACKEND_IP>`, 실제 값은 Notion 참고)와는 다른 DB. 팀 배포 서버를 쓰려면 `.env`의 `MONGO_HOST`를 그쪽으로 두고 compose의 `mongo` 서비스는 안 띄워도 됨(`docker compose --profile local up backend report-scheduler collection-scheduler`)
- 라벨링/학습(YOLO26 재학습 + Qwen3-VL-8B LoRA·QLoRA)은 평소엔 내려두고 필요할 때만:
  ```bash
  docker compose --profile training up --build training
  docker compose --profile training down   # best.pt 등 산출물 나오면
  ```
  GPU 패스스루에 `nvidia-docker`(NVIDIA Container Toolkit) 필요. GPU 서버에서
  띄우기 전엔 `.env`의 `GPU_DEVICE_ID`(할당받은 카드 번호)가 맞는지 꼭 확인할 것 —
  안 맞으면 다른 팀 카드를 잡을 수 있음
- **팀 공용 JupyterLab**: `training` 컨테이너가 뜨면 `http://<GPU서버IP>:${JUPYTER_PORT:-8899}`로
  접속(토큰은 `.env`의 `JUPYTER_TOKEN`, 팀원끼리만 공유). `ultralytics`/`transformers`/
  `peft`/`bitsandbytes`/`accelerate` 설치돼 있어 YOLO26 재학습·Qwen3-VL LoRA/QLoRA
  파인튜닝 코드를 노트북으로 바로 작성 가능. `/workspace`가 `training/` 디렉터리에
  마운트되어 저장한 노트북/코드는 호스트에 남음(단, 체크포인트·데이터셋·`best.pt`
  등 산출물은 `.gitignore`에 이미 제외 설정됨 — 별도 저장 방식은 TBD).
  **주의**: JupyterLab은 진짜 멀티유저(JupyterHub)가 아니라 커널 하나를 공유하는
  구조라, 팀원 여러 명이 동시에 같은 셀을 실행하면 충돌할 수 있음 — 번갈아 쓰는 걸 권장
- **초기 데이터셋 준비 스크립트**: `training/` 폴더에 모델팀이 초기 학습 데이터를 만들 때
  쓴 유틸(프레임 추출·자동 라벨링·증강·분할·클래스 집계)이 들어있음 — 개인 PC 절대경로가
  하드코딩된 수동 실행용이고, 운영 자동 재학습(`autoTraining/`)과는 별개다.
  상세는 `training/README.md` 참고

## 현재 상태 (고도화 진행 중)

> MVP 데모(수동 HTTP 스텁으로 이벤트 플로우 시연)는 끝났고, 지금은 라즈베리파이/GPU 추론
> 실제 하드웨어·소프트웨어 통합과 LLM 자동 라벨링 검증 등을 진행하는 고도화 단계.
> 아래 "미착수"/TBD 표시는 실제 구현 상태 그대로임(데모 종료 ≠ 구현 완료).

**이 표는 "무엇이 어디까지 돼 있고 코드가 어디 있는지"만 본다.** 왜 그렇게 설계했는지와
경위·미해결 사항은 `Docs/ARCHITECTURE.md`에 있고 여기서 반복하지 않는다 — 같은 서술을 두
곳에 두면 반드시 갈라지기 때문이다.

| 기능 | 상태 | 주요 코드 | 상세 |
|---|---|---|---|
| 영상 소스(MJPEG 스트리밍) | 구현됨 | `streaming/cameraManager.py` | ARCHITECTURE "웹캠 시뮬레이션". 입고 후 `.env`의 `CAMERA_SOURCE_<CameraId>`만 RTSP URL로 교체(코드 불변) |
| 탐지 — TOP(오분류) | GPU→백엔드 end-to-end 검증 완료(2026-08-25). **상시 서비스화·실제 통 위치 ROI 재보정 TBD** | `models/trashdetect/tracking2.py` | ARCHITECTURE "탐지 파이프라인" |
| 탐지 — SIDE(넘침) | 위와 동일 구조·동일 검증 상태 | `models/trashoverflow/sideOverflow.py` | 〃. 가중치 `bestSide.pt`는 `.gitignore` 대상이라 레포에 없음 — 팀원에게 받아 GPU 서버의 `models/trashoverflow/`에 둬야 추론 테스트 가능 |
| 이벤트 트리거 녹화 | 구현됨 | `services/recordingService.py` | 상시 녹화 아님. 시작/종료 신호 사이 실제 구간(최대 30초 안전 캡) |
| GIF 인코딩·GridFS 업로드 | 구현됨 | `services/mediaService.py`, `repositories/mediaRepository.py` | 결과 ID가 `Event.imageFileId` |
| 사람 존재 감지 게이팅 | 구현됨. **임계값·디바운스 실측 튜닝 TBD** | `detection/presenceDetector.py`, `services/presenceGateService.py` | TOP 전용. GPU 판정과 완전 독립 |
| 방문 클립(`visitClips`) 저장 | 구현됨. **GPU 트랙 신호의 실기기 도달 검증 아직** | `services/visitClipService.py`, `repositories/visitClipRepository.py` | ARCHITECTURE "재학습용 미확정 방문 캡처" |
| 오분류 이벤트 영상 연결 | 구현됨. **운영에서 채워지는지 재확인 TBD** | `services/eventMediaService.py` | 방문 GIF에서 직전 약 5초 파생 |
| GPU 하트비트(헬스체크) | 구현됨. **30초/90초 수치 튜닝 TBD** | `services/gpuHeartbeatService.py` | ARCHITECTURE "추론 인프라" |
| API·저장소 | 구현됨(motor 기반, In-memory Mock 제거 완료) | `controllers/api.py`, `repositories/eventRepository.py` | `.agentfiles/apiSpec.md` |
| 자동 통계 보고서 | 구현됨 | `RPAs/reportAutomation/` | 별도 `report-scheduler`가 일일 09:00·주간 월 09:10 발송 |
| 수거 업무 자동화 RPA | 구현됨(기본 비활성). **배포 전 CTO 검토 필요** | `RPAs/collectionAutomation/`, `services/collectionTaskService.py` | `RPA_COLLECTION_ENABLED=true`일 때만 동작 |
| **RPA(전구/경고음)** | **미착수** — `services/rpaService.py` 없음 | — | 모드 전환 API는 있으나 실제 트리거로 이어지는 코드가 없음 |
| LLM 자동 라벨링 검증 | 사용 중(베이스 모델+프롬프트). **파인튜닝·통 모양 인식 데이터 생성 미착수** | `autoTraining/stages/reviewLabels.py` | `Docs/LLM.md`, ARCHITECTURE "LLM 활용" |
| 이벤트 파이프라인 데모 스텁 | 남아 있음(운영 경로 아님) | `services/detectionService.py` | 수동 HTTP로 DB에 이벤트를 채우는 용도. `recordingService.start`/`stop` → `mediaService.saveClipAsGif` → `eventService.createEvent` 체인을 그대로 호출한다. 검증은 `debug/detection/simulateEventPipeline.py` |
| DB | 구현됨 | `repositories/mongoClient.py` | `events` 컬렉션 + GridFS 버킷 2개(`topMedia`/`sideMedia`). `Docs/ERD.md` |

이벤트는 `misclassification`(투기)/`overflow`(넘침) 두 카테고리다(`schemas/event.py`의
`EventCategory`). **`overflow`에는 영상이 붙지 않는다** — 이유는 ARCHITECTURE "이벤트 적재".

### 배포 전략

**백엔드+DB는 로컬(`<LOCAL_BACKEND_IP>`, 실제 값은 Notion), GPU 서버는 추론+학습+LLM 검증.**

| 환경 | 기동 | 비고 |
|---|---|---|
| 개발 | Windows 노트북 + Docker | 로컬 웹캠 |
| 로컬 배포 | `docker compose --profile local up -d backend mongo report-scheduler collection-scheduler` | |
| GPU 서버 — 상시 추론 | `docker compose --profile gpu up -d` | `inference`(TOP) + `side-overflow`(SIDE) |
| GPU 서버 — 온디맨드 | `docker compose --profile training up` / `--profile llm up` | 학습·라벨링 검증 돌 때만 |

profile 없이 `docker compose up`을 치면 **아무것도 안 뜬다** — 로컬/GPU가 같은 파일을 공유해서
잘못된 환경에 잘못된 서비스가 뜨는 걸 막으려는 의도다.

카드는 L40S 4장 중 **1장만 할당**받아 쓰고, GPU 패스스루에 `nvidia-docker`가 필요하다.
영상 소스는 환경별로 `.env`의 `CAMERA_SOURCE_<CameraId>` 값만 다르다(코드 변경 없음).

→ 전환 경위, `network_mode: host` 수정과 **아직 남은 재검증**, SSH 역터널 전제조건:
`Docs/ARCHITECTURE.md`의 "배포 전략"

### 라즈베리파이(메인보드) 엣지 코드

메인보드 입고 완료. **별도 저장소**로 진행 중(`webcamViewer.py` 등, 이 레포 아님).
추론은 하지 않고 **캡처 + RTSP 송신 + GPIO/스피커**만 담당한다.

| 항목 | 상태 |
|---|---|
| 웹캠 캡처 → RTSP 송신 | 실기기 검증 완료(ffmpeg+MediaMTX, USB 웹캠). systemd 자동 기동까지 확인. **CSI 카메라 모듈은 미착수** |
| 알림 수신 → GPIO/스피커 | 스피커 검증용 리스너만 있음(`debug/hardware/alertListener.py`). **상시 서비스화·GPIO 전구 연동 미착수** |
| YOLO26 추론 | **여기 없음** — GPU 서버가 전담 |

RTSP는 **로컬 백엔드로만** 보낸다(라즈베리파이는 GPU 서버와 직접 연결되지 않음). GPU는
로컬 백엔드가 서빙하는 MJPEG 스트림을 SSH 역터널로 구독한다.

→ 실전 셋업 절차·트러블슈팅: `.agentfiles/piSetupOps.md` /
설계 배경: `Docs/ARCHITECTURE.md`의 "메인보드(라즈베리파이) 엣지 코드"


## TBD (팀 논의 필요)

미해결 항목은 **`Docs/ARCHITECTURE.md`의 "TBD"** 한 곳에서 관리한다(여기 옮겨 적으면 갈라진다).

이 README 범위에서 특히 자주 묻는 것만:

- **오탐 confidence threshold** — `.env` 값이 아니라 GPU 스크립트 안의 상수다
  (`sideOverflow.py`의 `CONFIDENCE_THRESHOLD`, `tracking2.py`의
  `CONFIDENCE`/`NEW_TRASH_CONFIDENCE`)
- **`services/rpaService.py` 미작성** — 실제 전구/경고음 GPIO 연동은 아직 없다(위 상태 표)

MongoDB·Docker/Compose 버전은 **더 이상 TBD가 아니다** — 위 "개발 환경" 표에서 확정됐다
(`mongo:7.0`, Compose V2).
