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

```powershell
cd WebApps/backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

cd ..\..
Copy-Item .env.example .env
# 기본값은 localhost + sortMasterTest. 공유 DB는 접속 대상과 권한을 확인한 뒤 명시적으로 변경

# 필요 시 .env 값 수정 (CAMERA_SOURCE_ELEVTOP, CAMERA_SOURCE_ELEVSIDE, MONGO_HOST 등)
# CAMERA_SOURCE_<CameraId> — 카메라 1대당 지점 1개. ELEV-TOP만 기본값 0(로컬 웹캠 1대로 바로 됨), 나머지는 미설정 시 해당 지점만 503

.\WebApps\backend\.venv\Scripts\python.exe .\infra\checkEnv.py
# 패키지 자동 설치 + Python/Docker/MongoDB 체크. 전부 OK가 아니면 여기서 먼저 해결

cd WebApps\backend
uvicorn main:app --reload --port 8047
```

앱은 시작할 때 `.env` 대상 MongoDB에 5초 제한 `ping`을 보내고 Event 인덱스를 준비한다.
연결·인증이 잘못되면 첫 API 요청에서 뒤늦게 500을 내는 대신 서버 startup이 실패하므로,
그 경우 터미널 오류와 `.env`의 DB 값을 먼저 확인한다.

브라우저에서 http://localhost:8047 접속.
API 상세 스펙은 `.agentfiles/apiSpec.md` 참고.

### Docker Compose

```bash
# .env는 프로젝트 루트에 위치해야 함
docker compose up --build
```

- `backend`(포트 8047) + `mongo`(호스트 loopback `127.0.0.1:27020`) 상시 기동.
  Mongo healthcheck가
  통과한 뒤 백엔드를 시작한다.
- 호스트 Python은 `MONGO_HOST`/`DB_PORT`/`DB_*`, Compose 백엔드는 별도
  `COMPOSE_MONGO_*`/`COMPOSE_DB_*`(기본 `mongo:27017/sortMasterTest`, 무인증)를
  사용한다. 따라서 호스트용 공유 DB 계정이 로컬 컨테이너로 잘못 전달되지 않는다.
  컨테이너에서 팀 배포 DB를 쓸 때만 다섯 `COMPOSE_*` 값을 해당 서버·계정으로 바꾸고
  `docker compose up --no-deps --build backend`를 실행한다.
- 로컬 웹캠을 컨테이너에 연결하는 장치 패스스루는 현재 제공하지 않는다.
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

## 현재 상태 (백엔드 MVP 구현, 엣지 AI·실제 HW 연동 대기)

- **영상 소스**: 구현됨. `streaming/cameraManager.py` — 카메라 1대당 독립 젯슨 나노 1대
  구성으로, `.env`의 `CAMERA_SOURCE_<CameraId>`(예: `CAMERA_SOURCE_ELEVTOP`,
  `CAMERA_SOURCE_ELEVSIDE`)마다 별도 `CameraManager`를 관리하고 `GET /api/stream/{cameraId}`로
  MJPEG 송출(role 파라미터 없음). `ELEV-TOP`만 기본값 `0`이라 웹캠 1대짜리 로컬 개발
  환경에서 바로 동작. 나머지 지점은 미설정 시 해당 `cameraId`만 503(다른 지점엔 영향 없음).
  메인보드 입고 후엔 `CAMERA_SOURCE_<CameraId>`를 RTSP URL로 교체(코드 불변).
  젯슨 나노 입고 전 RTSP 경로를 미리 테스트하려면 `debug/streaming/startRtspSim.py`
  참고(이 PC 웹캠 여러 대를 지점별로 할당해 RTSP 송신 흉내, 백엔드와 무관한 로컬 테스트 전용 도구).
  `CameraId`는 `ELEV-TOP`/`ELEV-SIDE`로 확정 및 코드 반영 완료 — 설치 위치는 12층
  엘리베이터 앞 쓰레기통 1개뿐이라 지점 번호가 필요 없음 — `.agentfiles/architecture.md` 참고
- **탐지**: 실제 YOLO 추론 연동은 미완료지만, 엣지가 호출할
  `POST /api/detection/start`·`stop` HTTP 연결부와 녹화→GIF→GridFS→이벤트 저장은 구현됨.
  **MVP는 YOLO26 단독**(상시감시+투척판단+쓰레기 종류 분류까지 전부 엣지에서)으로 확정
  (상세는 `.agentfiles/architecture.md`, `.agentfiles/apiSpec.md` 참고).
  Qwen3-VL-8B(LLM)는 MVP 실시간 경로엔 안 쓰고 고도화
  단계 학습 보조용(불확실한 분류 안정화/환경별 통 모양 인식 데이터 생성)으로 후순위.
  트리거 조건은 손 감지 조합이 아니라 **쓰레기 감지 자체**로 변경됨 — 옆 카메라 단독으로
  넘침 감지 시 위치 특정 없이 바로 `overflow` 판정, 위 카메라는 엣지(젯슨) YOLO26이 감지+
  추적+분류를 전부 끝내고 `misclassification` 판정까지 완결(GPU/LLM 호출 없음, 상세는
  `.agentfiles/architecture.md`의 "탐지 파이프라인" 참고). 이벤트는
  `misclassification`(투기)/`overflow`(넘침) 두 카테고리로 나뉨(스키마에 반영 완료,
  `schemas/event.py`의 `EventCategory`). 실제 트리거는 아직 없어서
  `debug/detection/simulateEventPipeline.py`로 시작/종료 신호를 흉내내 파이프라인만
  검증 중. 수령한 `bestTop.pt`는 쓰레기 `plastic`/`can`을 합친 8클래스라 확정
  9클래스 의미 계약과 불일치하며 현재 연동 보류(`Docs/DATASET_DESCRIPTION.md` 참고).
- **이벤트 트리거 녹화**: 구현됨. `services/recordingService.py` — 상시 녹화가 아니라
  트리거 시점에만 캡처(architecture.md 원칙). 고정 10초가 아니라, 향후 탐지 파이프라인이
  보내는 시작/종료 두 신호 사이의 실제 구간만큼 녹화(신호 유실 대비 최대 30초 안전 캡).
  stop 성공 결과는 120초 동안 멱등 캐시하고 원본 프레임은 즉시 해제한다.
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

> **MVP 배포 위치 재조정(확정)** — 과거 "백엔드+DB+LLM 추론+학습을 GPU 서버에 전부 통합
> 배포" 결정을 뒤집음. **백엔드+DB는 로컬(`192.168.0.40`, 마지막 옥텟 유동적)**에서 구동하고,
> **GPU 서버는 YOLO26 학습만** MVP 범위(GPU 서버는 타 팀과 공유하는 자원이라 부담 경감
> 목적). **MVP는 LLM(Qwen3-VL-8B)을 아예 안 씀** — YOLO26이 쓰레기 종류 분류까지 전담하게
> 되면서 LLM은 고도화 단계 학습 보조용으로 후순위. 상세는 `.agentfiles/architecture.md` 참고.

- **개발**: Windows 노트북에서 Docker로 진행(로컬 웹캠 테스트)
- **배포**: `192.168.0.40`의 인증 MongoDB 접속값을 `COMPOSE_MONGO_HOST`/
  `COMPOSE_DB_PORT`/`COMPOSE_DB_NAME`/`COMPOSE_DB_USER`/`COMPOSE_DB_PASSWORD`에 넣고
  `docker compose up --no-deps --build backend`로 백엔드만 구동한다. Compose의 `mongo`
  서비스는 loopback 전용 무인증 `sortMasterTest` 개발 DB이므로 배포 서버에서는 실행하지 않는다.
  `training`(학습)만 학원 GPU 서버(Linux, **NVIDIA L40S 4장 중 할당받은 1장**)로 이전해서
  `docker compose --profile training up`로 구동(`llm`은 고도화 단계 전까지 안 씀)
- 다른 팀들과 서버를 공유하기 때문에 4장 중 **1장만 할당**받아 사용. **YOLO26 상시 추론은
  GPU가 아니라 엣지(젯슨 Orin Nano Super)가 담당**(MVP는 GPU/LLM 호출 자체가 없음,
  `.agentfiles/architecture.md` 참고). GPU 패스스루는 `nvidia-docker`(NVIDIA Container Toolkit) 필요.
- 로컬(웹캠)과 배포 환경(RTSP 수신/샘플 영상) 간 영상 소스는 `.env`의
  `CAMERA_SOURCE_<CameraId>` 값만 다르게 관리(코드 변경 없음).

### 젯슨 나노(메인보드) 엣지 코드

메인보드 입고 전까지 별도 진행 중 (`webcamViewer.py` 등, 백엔드와는 다른 코드베이스):

1. **웹캠 캡처 → RTSP 송신**: 1단계(웹캠 뷰어) 노트북에서 테스트 완료. 다음 단계로
   GStreamer 기반 RTSP 송신 서버로 확장 예정 (JetPack 기본 포함).
2. **중앙 서버 알림 신호 수신 → GPIO 트리거**: 아직 설계 전. 현재 `RPAs/`는
   중앙 백엔드 안에서 Mock 처리 중인 자리만 잡아둔 상태 — 실제로는 젯슨 나노 쪽
   리스너로 옮겨야 할 가능성 높음. 신호 전달 방식(MQTT/HTTP/WebSocket)은 TBD.

## 메인보드 입고 후 개발할 부분

1. ~~`streaming/cameraManager.py`~~ **완료** — 카메라 1대당 독립 지점(`CameraId`), `/api/stream/{cameraId}`
   MJPEG 송출 구현됨. 메인보드 입고 후엔 `CAMERA_SOURCE_<CameraId>`를
   RTSP URL로 교체만 하면 됨(코드 변경 불필요). 저장/DB 연동은 아래 항목들이 선행돼야 함
2. ~~`services/detectionService.py` HTTP 연결부~~ **완료** — 엣지는 이벤트 시작/종료마다
   `/api/detection/start`·`stop`을 호출하면 아래 3~5번 파이프라인을 사용한다.
   남은 일은 젯슨 YOLO 추론·추적 결과를 이 계약으로 변환해 호출하는 엣지 코드이며,
   순수 HTTP 클라이언트는 `debug/detection/detectionApiClient.py`에 제공한다.
3. ~~**이벤트 트리거 녹화**~~ **완료** — `services/recordingService.py`. 탐지 서비스가
   아직 없어서 고정 10초 대신, 시작/종료 두 신호(향후 탐지 파이프라인이 전달) 사이의
   실제 구간을 캡처하는 구조로 미리 구현. 2번이 없는 지금은 디버그 스크립트로 신호를
   흉내내서 검증
4. ~~**GridFS 업로드**~~ **완료** — `services/mediaService.py`(GIF 인코딩) +
   `repositories/mediaRepository.py`(GridFS 저장), 파일 ID 발급까지 구현됨
5. ~~`repositories/eventRepository.py`~~ **완료** — motor 기반 MongoDB 연동으로 교체,
   4번의 GridFS 파일 ID를 `imageFileId`로 같이 저장
6. `services/rpaService.py` — 아직 미작성. 실제 GPIO/HW 연동(`RPAs/` 참고, 젯슨
   나노 쪽으로 이전 검토 중)

## TBD (팀 논의 필요)

- 오탐 confidence threshold (현재 `.env`에 임시값 0.7) — `mixed`/`uncertain` 클래스는 제외로
  확정됐지만(`.agentfiles/architecture.md` 참고), 신뢰도 임계값 자체는 별개로 여전히 TBD
- MongoDB 버전, Docker/Compose 버전 (개발 환경 표 참고)
- 통계 대시보드 세부 지표
- 안면인식(투기자 식별) 포함 여부 — 기본 제외
- 젯슨 나노 ↔ 중앙 서버 알림 신호 전달 방식(MQTT/HTTP/WebSocket)
