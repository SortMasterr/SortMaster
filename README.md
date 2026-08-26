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

### Docker Compose

```bash
# .env는 프로젝트 루트에 위치해야 함(Notion 공유값)
docker compose --profile local up --build
```

- `backend`(포트 8047) + `mongo`(호스트 포트 27020) 상시 기동. 로컬 웹캠을 백엔드가 직접 여는 코드는 아직 없어서 지금은 컨테이너에 카메라 디바이스 패스스루 불필요
- `backend`/`mongo`는 `local` profile로 묶여 있음(GPU 서버의 `inference`/`side-overflow`와 같은 파일을 공유하므로, 이름 없이 `docker compose up`을 치면 아무것도 안 뜨게 해서 잘못된 환경에서 잘못된 서비스가 뜨는 걸 방지) — 반드시 `--profile local`을 붙일 것
- 여기서 뜨는 `mongo`는 로컬 전용 별도 인스턴스 — 팀 배포 서버(`<LOCAL_BACKEND_IP>`, 실제 값은 Notion 참고)와는 다른 DB. 팀 배포 서버를 쓰려면 `.env`의 `MONGO_HOST`를 그쪽으로 두고 compose의 `mongo` 서비스는 안 띄워도 됨(`docker compose --profile local up backend`)
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

## 현재 상태 (고도화 진행 중)

> MVP 데모(수동 HTTP 스텁으로 이벤트 플로우 시연)는 끝났고, 지금은 라즈베리파이/GPU
> `inference` 실제 하드웨어·소프트웨어 통합과 LLM 자동 라벨링 검증 등을 진행하는 고도화
> 단계. 아래 "아직 미착수"/TBD 표시는 실제 구현 상태 그대로임(데모 종료 ≠ 구현 완료).

- **영상 소스**: 구현됨. `streaming/cameraManager.py` — 카메라 1대당 독립 라즈베리파이 1대
  구성으로, `.env`의 `CAMERA_SOURCE_<CameraId>`(예: `CAMERA_SOURCE_ELEVTOP`,
  `CAMERA_SOURCE_ELEVSIDE`)마다 별도 `CameraManager`를 관리하고 `GET /api/stream/{cameraId}`로
  MJPEG 송출(role 파라미터 없음). `ELEV-TOP`만 기본값 `0`이라 웹캠 1대짜리 로컬 개발
  환경에서 바로 동작. 나머지 지점은 미설정 시 해당 `cameraId`만 503(다른 지점엔 영향 없음).
  메인보드 입고 후엔 `CAMERA_SOURCE_<CameraId>`를 RTSP URL로 교체(코드 불변).
  라즈베리파이 입고 전 RTSP 경로를 미리 테스트하려면 `debug/streaming/startRtspSim.py`
  참고(이 PC 웹캠 여러 대를 지점별로 할당해 RTSP 송신 흉내, 백엔드와 무관한 로컬 테스트 전용 도구).
  `CameraId`는 `ELEV-TOP`/`ELEV-SIDE`로 확정 및 코드 반영 완료 — 설치 위치는 12층
  엘리베이터 앞 쓰레기통 1개뿐이라 지점 번호가 필요 없음 — `.agentfiles/architecture.md` 참고
- **탐지**: **TOP은 GPU 서버 → 로컬 백엔드 end-to-end 연결성 검증 완료**(2026-08-25, 실제
  TOP MJPEG 스트림을 GPU가 SSH 역터널로 구독 → YOLO26 판정 → `POST
  /api/events/aiDisposal`까지 확인 — 단, 상시 서비스화(systemd/Docker)와 실제 통 위치 기준
  ROI 재보정은 아직 TBD). **SIDE도 이제 TOP과 완전히 동일한 구조**(GPU 서버가
  `models/trashoverflow/sideOverflow.py`로 MobileNet_V3_Small 판정 — 코드는 작성됐지만
  GPU 서버 실제 배포/실행+end-to-end 검증 완료, 2026-08-25). SIDE는 원래 룰 베이스 → 로컬 백엔드 CPU 추론(GPU
  미사용) → 지금의 GPU 서버 방식까지 두 번 재전환됐음(이유는 `.agentfiles/decisionLog.md`
  참고 — 기술적 필요보다는 TOP과의 아키텍처 일관성이 마지막 전환의 이유). 메인보드를 Jetson
  Orin Nano Super→**라즈베리파이**로 전환하면서 **TOP의 YOLO26 추론 위치도 엣지→GPU 서버
  (`models/trashdetect/tracking2.py`)로 이관**(라즈베리파이는 캡처+RTSP 송신+GPIO/스피커만
  담당, 추론 없음). Qwen3-VL-8B(LLM)는 실시간 경로엔 안 쓰고 학습 준비 단계의 자동 라벨링
  검증에 **이미 사용 중**(베이스 모델+프롬프트, 파인튜닝은 필요성 확인되면 착수 — 통 모양
  인식 데이터 생성은 아직 미착수). 트리거 조건은 손 감지 조합이 아니라 **쓰레기 감지
  자체**로 변경됨 — TOP(`tracking2.py`)/SIDE(`sideOverflow.py`) 둘 다 GPU 서버가 감지+판정을
  자체적으로 끝내서 결과를 로컬 백엔드로 푸시하면, 백엔드는 통 상태/쿨다운과 종합해
  `EVENT`로 저장(재계산 안 함, 상세는 `.agentfiles/architecture.md`의 "탐지 파이프라인"
  참고). 이벤트는
  `misclassification`(투기)/`overflow`(넘침) 두 카테고리로 나뉨(스키마에 반영 완료,
  `schemas/event.py`의 `EventCategory`).
- **이벤트 트리거 녹화**: 구현됨. `services/recordingService.py` — 상시 녹화가 아니라
  트리거 시점에만 캡처(architecture.md 원칙). 고정 10초가 아니라, 향후 탐지 파이프라인이
  보내는 시작/종료 두 신호 사이의 실제 구간만큼 녹화(신호 유실 대비 최대 30초 안전 캡).
- **GIF 인코딩/GridFS 업로드**: 구현됨. `services/mediaService.py`(OpenCV 프레임 →
  애니메이션 GIF, Pillow) + `repositories/mediaRepository.py`(GridFS 업로드) —
  결과 파일 ID가 `Event.imageFileId`에 저장됨.
- **API/저장소**: `controllers/api.py` — 이벤트 CRUD(`/api/events`), 통계
  (`GET /api/statistics`), 모드 전환(`POST /api/mode`, MANAGE/COLLECT) 구현됨.
  `repositories/eventRepository.py`는 motor 기반 MongoDB 연동으로 전환 완료(In-memory
  Mock 제거) — `.env`의 `MONGO_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME` 사용.
- **RPA(전구/경고음)**: 아직 미착수. 모드 전환 API(`/api/mode`)는 있지만 실제
  RPA 트리거·Mute로 이어지는 코드는 없음.
- **DB**: MongoDB Docker(호스트 포트 `27020`, 컨테이너 내부는 `27017`)에 백엔드가
  motor로 연결됨. 이벤트 메타데이터는 `events` 컬렉션, GIF 클립은 GridFS에 저장 —
  버킷을 카메라별로 `topMedia`(위 카메라)/`sideMedia`(옆 카메라) 2개로 분리(관리 편의
  목적, 상세는 `Docs/ERD.md` 참고).

### 배포 전략

> **배포 위치(확정)** — 과거 "백엔드+DB+LLM 추론+학습을 GPU 서버에 전부 통합 배포" 결정을
> 뒤집음. **백엔드+DB는 로컬(`<LOCAL_BACKEND_IP>`, 실제 값은 Notion 참고)**에서 구동하고,
> **GPU 서버는 YOLO26(TOP)+MobileNet_V3_Small(SIDE) 추론+학습+LLM 자동 라벨링 검증** 담당
> (GPU 서버는 타 팀과 공유하는 자원이라 부담 경감 목적 — 단, SIDE를 GPU로 올린 건 자원
> 필요보다는 TOP과의 아키텍처 일관성 때문, `.agentfiles/decisionLog.md` 참고). LLM은 실시간
> 탐지 경로엔 여전히 안 씀 — 학습 준비 단계 검증용으로만 이미 사용 중. **메인보드를 Jetson
> Orin Nano Super→라즈베리파이로 전환하며 TOP의 YOLO26 추론도 엣지→GPU 서버로 이관**
> (라즈베리파이는 추론 성능 부족). 상세는 `.agentfiles/architecture.md` 참고.

- **개발**: Windows 노트북에서 Docker로 진행(로컬 웹캠 테스트)
- **배포**: `backend`+`mongo`는 로컬 `<LOCAL_BACKEND_IP>`(실제 값은 Notion 참고)에서
  `docker compose --profile local up -d backend mongo`로 구동. `training`/`llm`을 학원
  GPU 서버(Linux, **NVIDIA L40S 4장 중 할당받은 1장**)로 이전해서 `docker compose
  --profile training up`/`--profile llm up`(자동 라벨링 검증 파이프라인 돌 때만 같이
  기동). **TOP(`inference` 서비스, `models/trashdetect/tracking2.py`)/SIDE
  (`side-overflow` 서비스, `models/trashoverflow/sideOverflow.py`) 상시 추론은
  `gpu` profile로 묶어서 `docker compose --profile gpu up -d`로 한 번에 기동**
  (모두 같은 `docker-compose.yml`을 공유하므로, profile 없이 `docker compose up`을
  치면 로컬/GPU 어느 환경에서든 아무것도 안 뜨게 해서 잘못된 서비스가 실수로 같이
  뜨는 걸 방지). Docker 정의는 완료됐고 GPU 서버 rootless Docker가 이미
  `loginctl enable-linger`로 재부팅 시 자동 기동되게 설정돼 있어서 별도 systemd 없이
  `restart: unless-stopped`만으로 GPU 재부팅 복구가 됨. 2026-08-25에 GPU 서버에서 실제
  컨테이너 기동을 처음 시도했다가 `host.docker.internal` crash loop를 발견하고
  `network_mode: host`로 수정(커밋 `06f3d0d`)까지 반영됨 — **단, 수정 후 재기동해서 정상
  연결되는지 최종 재검증은 아직 안 됨**(그 전까지는 TOP/SIDE 둘 다 컨테이너 없이 venv+
  `python tracking2.py`/`sideOverflow.py`로 직접 실행해서만 검증됨). SSH 역터널이 살아있는
  건 여전히 별개 전제조건(로컬 배포 서버 쪽 `autossh` 필요, TBD)
- 다른 팀들과 서버를 공유하기 때문에 4장 중 **1장만 할당**받아 사용. **TOP/SIDE 상시 추론
  둘 다 GPU 서버가 담당**(라즈베리파이는 추론 없이 캡처+RTSP+GPIO만,
  `.agentfiles/architecture.md` 참고). GPU 패스스루는 `nvidia-docker`(NVIDIA Container
  Toolkit) 필요.
- 로컬(웹캠)과 GPU 서버 배포(RTSP 수신/샘플 영상) 간 영상 소스는 `.env`의
  `CAMERA_SOURCE` 값만 다르게 관리(코드 변경 없음).

### 라즈베리파이(메인보드) 엣지 코드

메인보드(라즈베리파이) 입고 완료, 별도 코드베이스로 진행 중(`webcamViewer.py` 등, 백엔드와는
다른 저장소). Jetson Orin Nano Super 발주는 취소, **라즈베리파이로 확정 대체**(YOLO26 추론을
GPU 서버로 이관하면서 메인보드엔 고성능 추론이 더 이상 필요 없어짐 — 상세는
`.agentfiles/architecture.md`의 "탐지 파이프라인"/"배포 전략" 참고):

1. **웹캠 캡처 → RTSP 송신**: **실기기(`elev-top`)에서 ffmpeg+MediaMTX로 검증 완료**(USB
   웹캠 기준, 카메라 모듈은 미착수). RTSP는 로컬 백엔드(LAN)로만 수신(GPU 서버는 RTSP를
   직접 안 받음 — TOP 카메라도 로컬 백엔드가 프레임을 샘플링해서 GPU에 API로 전달하는
   구조로 확정됨, `.agentfiles/architecture.md`의 "탐지 파이프라인" 참고). systemd 서비스로
   등록해 재부팅 시 자동 기동되도록 완료(재부팅 테스트로 검증됨) — 실전 셋업
   절차/트러블슈팅은 `.agentfiles/piSetupOps.md` 참고
2. **중앙 서버 알림 신호 수신 → GPIO/스피커 트리거**: 아직 설계 전. 현재 `RPAs/`는
   중앙 백엔드 안에서 Mock 처리 중인 자리만 잡아둔 상태 — 실제로는 라즈베리파이 쪽
   리스너로 옮겨야 할 가능성 높음(GPIO 릴레이로 전구, USB/오디오잭으로 스피커).
   신호 전달 방식(MQTT/HTTP/WebSocket)은 TBD.
3. **YOLO26 추론은 여기 없음** — GPU 서버의 `models/trashdetect/tracking2.py`가 전담(아직
   Docker 컨테이너 아닌 독립 스크립트, 아래 "메인보드 입고 후 개발할 부분" 참고)

## 메인보드 입고 후 개발할 부분

1. ~~`streaming/cameraManager.py`~~ **완료** — 카메라 1대당 독립 지점(`CameraId`), `/api/stream/{cameraId}`
   MJPEG 송출 구현됨. 메인보드 입고 후엔 `CAMERA_SOURCE_<CameraId>`를
   RTSP URL로 교체만 하면 됨(코드 변경 불필요). 저장/DB 연동은 아래 항목들이 선행돼야 함
2. `services/detectionService.py` — **데모용 임시 스텁**(`debug/detection/`의 스크립트로
   수동 HTTP 요청을 보내 DB에 이벤트 데이터를 채워 넣는 용도)은 계속 남아있지만, **TOP의
   실제 연동은 이 스텁을 대체하는 게 아니라 별도 경로로 이미 구현·검증됨** —
   `services/eventService.py`의 `createEventFromAiDisposal`이 GPU 서버
   `models/trashdetect/tracking2.py`(YOLO26, `inference` Docker 서비스로 정의됨 — 2026-08-25에
   GPU 서버 실제 기동을 처음 시도해 `network_mode: host`로 수정까지 반영됐고, 수정 후
   재기동 최종 재검증은 아직 TBD)가
   자체적으로 감지+추적+분류+정상/오분류 판정까지 끝내고 `POST /api/events/aiDisposal`로
   보내는 결과를 받아 통 상태/쿨다운과 종합해 저장(2026-08-25 실제 스트림 기준 end-to-end
   검증됨, `.agentfiles/architecture.md` 참고). **SIDE도 이제 완전히 같은 패턴** —
   `models/trashoverflow/sideOverflow.py`(GPU 서버, 독립 스크립트)가 MobileNet_V3_Small로
   자체 판정 후 `POST /api/binStates`로 결과를 푸시(로컬 백엔드가 SIDE를 호출하지 않음) —
   TOP과 마찬가지로 실제 GPU 서버 배포/실행+end-to-end 검증 완료(2026-08-25, `overflow`
   전환 시 `POST /api/binStates -> 200` 확인, `decisionLog.md` 참고). Qwen3-VL-8B(LLM)는
   실시간 경로엔 안 들어감, 학습 준비 단계
   자동 라벨링 검증에만 사용. 지금 스텁(`services/detectionService.py`)도 이벤트 시작/종료
   시점마다 아래 3~5번 파이프라인(`recordingService.start`/`stop` →
   `mediaService.saveClipAsGif` → `eventService.createEvent`)을 그대로 호출함(수동 검증은
   `debug/detection/simulateEventPipeline.py` 또는 `testDetectionApi.http` 참고). SIDE
   모델 가중치(`bestSide.pt`)는 `.gitignore` 대상이라 레포에 없음 — 실제 추론 테스트는
   가중치 파일을 팀원에게 받아 GPU 서버의 `models/trashoverflow/`에 둬야 가능
3. ~~**이벤트 트리거 녹화**~~ **완료** — `services/recordingService.py`. 탐지 서비스가
   아직 없어서 고정 10초 대신, 시작/종료 두 신호(향후 탐지 파이프라인이 전달) 사이의
   실제 구간을 캡처하는 구조로 미리 구현. 2번이 없는 지금은 디버그 스크립트로 신호를
   흉내내서 검증
4. ~~**GridFS 업로드**~~ **완료** — `services/mediaService.py`(GIF 인코딩) +
   `repositories/mediaRepository.py`(GridFS 저장), 파일 ID 발급까지 구현됨
5. ~~`repositories/eventRepository.py`~~ **완료** — motor 기반 MongoDB 연동으로 교체,
   4번의 GridFS 파일 ID를 `imageFileId`로 같이 저장
6. `services/rpaService.py` — 아직 미작성. 실제 GPIO/HW 연동(`RPAs/` 참고, 라즈베리파이
   쪽으로 이전 검토 중)

## TBD (팀 논의 필요)

- 오탐 confidence threshold (현재 `.env`에 임시값 0.7) — `mixed`/`uncertain` 클래스는 제외로
  확정됐지만(`.agentfiles/architecture.md` 참고), 신뢰도 임계값 자체는 별개로 여전히 TBD
- MongoDB 버전, Docker/Compose 버전 (개발 환경 표 참고)
- 통계 대시보드 세부 지표
- 안면인식(투기자 식별) 포함 여부 — 기본 제외
- 라즈베리파이↔중앙 백엔드(RPA 트리거) 신호 전달 방식(MQTT/HTTP/WebSocket, 미정 — GPU
  서버↔중앙 백엔드의 판정 결과 전달은 HTTP POST로 이미 확정+검증됨, `.agentfiles/architecture.md`
  참고)
