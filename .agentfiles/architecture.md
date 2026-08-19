# architecture.md

원본(source of truth). 다른 문서와 내용이 겹치면 이 문서 우선.

## 파이프라인

```
CCTV → 프레임분할 → 객체디텍팅 → 오분류 판정
  ├─ 탐지 시 → 현장알림(전구+경고음)
  └─ 결과전송 → 백엔드(수신API) → 기록/통계
→ 관리자웹(스트리밍/기록/통계, 오분류 시 테두리 빨간색)
```

- 목적: 행정직원 분리수거 감독 부담 경감
- 알림: 전구+스피커 항상 동시 트리거
- 안면인식(투기자 식별) 미포함, CTO 공통과제는 3팀 소관

## 설치 환경

| 항목 | 내용 |
|---|---|
| 위치 | **엘리베이터 2대 계획은 없었던 것으로 정정** — 실제로는 12층 엘리베이터 앞에 쓰레기통 1개만
  고정 설치(`ELEV` 명칭은 여기서 유래). 카메라 지점 2개(위+옆), `CameraId`는 `ELEV-TOP`/`ELEV-SIDE`로
  확정(설치 위치 번호 불필요 — 위치가 1곳뿐이라서). 4층 휴게실(`REST-4F-01`) 추가는 **사실상
  제외**(진행 가능성 낮다고 판단, 완전 취소는 아니지만 계획에는 안 넣음) |
| 메인보드 | **Jetson Orin Nano Super 발주 건 완전 취소 → 라즈베리파이로 확정 대체.** YOLO26 추론을 GPU 서버로 이관하면서(아래 "탐지 파이프라인" 참고) 메인보드엔 고성능 추론이 더 이상 필요 없어짐 — 캡처+RTSP 송신+GPIO/스피커만 담당. Raspberry Pi OS(Python 3.11+)라 `WebApps/backend`와 문법 호환성 문제 없음 |
| 카메라 구성 | **"카메라 1대 = 지점 1개 = `CameraId` 1개 = 독립 라즈베리파이 1대" 규칙 유지**(안 깨짐). 설치 위치 1곳(12층 엘리베이터 앞)에 지점 2개(위+옆). `.env` 키는 기존 하이픈 제거 규칙 그대로 `CAMERA_SOURCE_ELEVTOP`/`CAMERA_SOURCE_ELEVSIDE` |
| 카메라 스펙 | 웹캠 실촬영 해상도 **640×480**(약 30만 화소). YOLO 입력 전처리는 **640×640**으로 통일(레터박스 패딩 방식 — 비율 유지, 단순 리사이즈 아님). TOP 카메라는 YOLO26 혼자 분류까지 끝내서 별도 모델로 좌표를 넘길 일이 없음(LLM에 좌표 넘기는 보정은 후순위 재검토 항목) |
| 배포 구조 | 지점별(카메라별) 독립 메인보드+카메라 1대 — 설치 위치 1곳에 지점(=메인보드+카메라 세트) 2개 |
| 클래스 | general, paper, plastic, can(신규, 플라스틱과 별도지만 같은 통), coffeeCup(별도 통) — 총 5종. `mixed`/`uncertain`은 제외 확정(자체 라벨링 시 전부 5종 중 하나로 분류 가능하다고 판단, 아래 "해결된 TBD" 참고) |

## 탐지 파이프라인

> **메인보드를 Jetson Orin Nano Super에서 라즈베리파이로 전환하면서 YOLO26 추론 위치도
> 엣지→GPU 서버로 이관 확정**(과거 "엣지 YOLO26 단독" 결정을 다시 뒤집음). 라즈베리파이는
> 추론 성능이 부족해 **캡처+RTSP 송신+GPIO(전구/스피커)만 담당**하고, **YOLO26 상시 추론
> (감지+추적+분류+판정)은 GPU 서버의 신규 `inference` 컨테이너가 전담**. 라즈베리파이의
> RTSP 스트림을 GPU 서버가 SSH 역터널로 직접 당겨서(같은 스트림을 로컬 백엔드도 동시에
> 받아 관리자 웹 실시간 송출에 그대로 씀 — `cameraManager.py` 변경 불필요) 연속 추론 루프를
> 돈다. LLM(Qwen3-VL-8B)은 여전히 이 실시간 경로엔 없음(고도화 전용, 아래 "LLM 활용" 참고) —
> **`inference`와 `llm`은 서로 다른 GPU 컨테이너**.

- **넘침(overflow) 판정**(**옆 카메라** 단독, **로컬 백엔드, 룰 베이스 — GPU 미사용**): 옆
  카메라 라즈베리파이가 보낸 RTSP를 로컬 백엔드가 LAN으로 그대로 받아(관리자 웹 송출과
  같은 스트림) **딥러닝 모델이 아니라 룰 베이스**로 쓰레기통 넘침 상태를 판정. GPU 서버는
  전혀 관여하지 않음 — `NORMAL`→`FULL` 전환 시점마다 바로 `BIN_STATES` 갱신+`EVENT`
  생성(기존과 동일). SIDE 카메라는 GPU 서버로 RTSP를 보낼 필요가 없어서, GPU 서버 SSH
  역터널은 TOP 카메라 하나만 있으면 됨(아래 "배포 전략" 참고)
- **투기(misclassification) 판정**(**위 카메라** 단독, GPU 서버 추론 + 로컬 백엔드 판정):
  1. 위 카메라 라즈베리파이가 보낸 RTSP를 GPU `inference`가 상시 수신 → 쓰레기 감지 시
     "감지 시작" 신호를 로컬 백엔드로 전송 → 백엔드가 이 시점부터 녹화 시작(DB 저장용)
  2. GPU `inference`가 **감지+추적+쓰레기 종류 분류를 프레임 단위로 계속 수행**(투척 궤적
     추적처럼 프레임 간 연속성이 필요한 상태는 GPU 쪽에서 유지 — 매 프레임 백엔드에
     왕복하면 실시간성이 떨어지므로)
  3. 투척 완료를 GPU가 판단하면 분류 결과+`trackingId`를 담아 **"판정 완료" 신호 1회**를
     로컬 백엔드로 전송 → 백엔드가 이미 갖고 있는 통 상태/쿨다운(5초) 로직으로 최종
     오분류 여부 확정 → **`EVENT` 저장** → 불일치 시 RPA 트리거 신호를 라즈베리파이로 전송
  4. 투척 완료 후 **약 3초 텀**을 두고 녹화 종료(신호는 백엔드가 자체 타이머로 처리, 기존과 동일)
  - GPU `inference` ↔ 로컬 백엔드 신호는 원본 프레임이 아니라 소형 JSON이라 왕복해도
    지연 영향이 작음 — 무거운 건 라즈베리파이→GPU 서버로 가는 RTSP 영상 자체(아래
    "배포 전략"의 SSH 역터널 참고). 실제 전달 방식(MQTT/HTTP/WS)은 TBD
- **역할 분담**:
  - **라즈베리파이(엣지, TOP+SIDE 공통)**: 캡처+RTSP 송신+GPIO(전구 릴레이)+스피커(경고음) —
    **추론 없음**(SIDE의 룰 베이스 판정도 라즈베리파이가 아니라 로컬 백엔드에서 돎)
  - **GPU 서버 `inference`(TOP 전용)**: YOLO26 상시 추론(감지+추적+분류), 투척 궤적처럼 프레임
    연속성이 필요한 판정까지만 담당(상태는 진행 중인 투척 1건 범위 내에서만 GPU가 들고 있음)
  - **로컬 백엔드**: TOP은 통 상태(`BIN_STATES`)/쿨다운/최종 `EVENT` 생성/녹화 시작·종료
    타이밍/RPA 트리거 신호 송신을 담당하고, SIDE는 룰 베이스 판정 자체부터 `BIN_STATES`/
    `EVENT` 생성까지 전부 직접 수행(GPU 서버 관여 없음) — 지속 상태는 전부 백엔드(로컬
    MongoDB) 소유
  - GPU 서버 컨테이너는 `training`(전처리+자동 라벨링+학습)/`inference`(YOLO26 TOP 모델
    상시 추론)/`llm`(Qwen3-VL-8B, 자동 라벨링 검증용으로 이미 사용 중 — 실시간 탐지 경로엔
    여전히 없음) 3개

## LLM 활용

Qwen3-VL-8B는 실시간 탐지 경로엔 없음(위 "탐지 파이프라인" 참고) — **학습/데이터 준비
단계에서만** 사용:

1. **자동 라벨링 검증(진행 중)**: 이미지 폴더 → 전처리+자동 라벨링 도구로 1차 라벨 생성 →
   자동 라벨링이 100% 정확하지 않아서, 불확실한 라벨만 LLM이 검증/보정하는 형태로 진행 중.
   `training` 컨테이너의 파이프라인 코드가 `llm` 컨테이너의 vLLM API를 호출. **우선 베이스
   Qwen3-VL-8B-Instruct + 프롬프트만으로 진행**(파인튜닝 없이 5종 분류는 비교적 쉬운 과제라
   판단 — 정확도 부족이 확인되면 그때 아래 파인튜닝 착수)
2. **환경별 통 모양 인식 학습 데이터 생성**: 설치 환경이 달라지면 물리 통 4개의 실제 생김새도
   달라지므로, LLM을 이용해 그런 환경별 통 인식 초기 학습 데이터를 만드는 데 활용 예정(아직
   미착수, 정확한 방식은 TBD)

**LLM 파인튜닝(미착수, 필요 시 진행)**: 위 1번 자동 라벨링 검증에서 베이스 모델 정확도가
부족하다고 확인되면, **Qwen3-VL-8B** + LoRA/QLoRA(Unsloth 또는 LLaMA-Factory)로 GPU 1장(48GB)
내 진행. 파인튜닝 후 4/8bit 양자화해 추론 시 VRAM 최소화(`training`과 같은 카드에서 동시 서빙
가능하도록). Full fine-tuning이나 32B/235B(MoE) 등 상위 사이즈는 단일 카드로 비현실적이라
배제. 데이터 규모에 따라 수시간~하루 내 소요 예상. 학습 작업과 실시간 서비스가 같은 카드를
쓰므로 트래픽 적은 시간대 학습 권장. 라이선스는 배포 전 해당 사이즈 조항 확인 필요

## 추론 인프라

- NVIDIA L40S 총 4장, **팀당 1장씩 전용 할당**(다른 팀과 경합 없음)
- 모델/역할 분담은 위 "탐지 파이프라인" 참고(YOLO26 TOP 모델만 GPU 서버 `inference`, SIDE는
  로컬 백엔드 룰 베이스, LLM은 자동 라벨링 검증용 — 실시간 탐지엔 미사용)
- **GPU 서버엔 컨테이너 3개**: `training`(전처리+자동 라벨링+학습, 필요할 때만 기동) /
  `inference`(YOLO26 TOP 모델 상시 추론, 상시 기동) / `llm`(Qwen3-VL-8B 서빙, vLLM — 자동
  라벨링 검증용으로 **이미 사용 중**, `training`과 함께 필요할 때만 기동. 실시간 탐지
  경로엔 여전히 없음). `backend`/`mongo`는 GPU 서버가 아니라 **로컬에서 구동**(아래 "배포
  전략" 참고)
- `inference`는 `training`과 같은 카드(`GPU_DEVICE_ID`)를 공유하는 상시 컨테이너라, 학습을
  돌리는 시간대엔 두 워크로드가 VRAM/연산을 나눠 써야 함 — `llm`처럼 GPU 메모리 사용량을
  제한해두는 게 안전(실측 후 조정 필요, 아래 TBD 참고)
- (과거 TBD였던) `training`에서 나온 `.pt` 가중치를 젯슨(엣지)에 배포하는 문제는 이번 이관으로
  해소 — `training`/`inference` 둘 다 GPU 서버 안에 있어 로컬 파일/볼륨 공유로 충분(원격 배포
  불필요)
- `training` 컨테이너는 JupyterLab을 띄워서 팀원이 브라우저로 같이 접속해 학습 코드 작성
  (`.env`의 `JUPYTER_PORT`/`JUPYTER_TOKEN`, 진짜 멀티유저 격리는 아니라 동시 실행 지양).
  GPU 서버 운영 실무(계정/rootless Docker/포트/SSH 터널 등)는 `gpuServerOps.md` 참고
- `inference` 컨테이너 자체(FastAPI+ultralytics 등 실제 구현/Dockerfile/docker-compose.yml
  서비스 정의)는 아직 미착수 — 위 "탐지 파이프라인" 설계대로 구현 예정

## 배포 전략

> **배포 위치(확정)** — 과거 "백엔드+DB+LLM 추론+학습을 GPU 서버 안에 전부 통합 배포"였던
> 결정을 뒤집음. **백엔드+DB는 로컬**, **GPU 서버는 YOLO26 학습+추론+자동 라벨링 검증(LLM)**
> 담당(실시간 탐지 경로에 LLM은 여전히 안 씀 — 위 "탐지 파이프라인"/"LLM 활용" 참고). 이유:
> GPU 서버는 다른 팀과 공유하는 자원이라 학습·추론 외 부담(백엔드/DB)은 줄이고, 백엔드/DB는
> 애초에 GPU를 안 쓰므로 로컬에 둬도 기능상 문제없음.
>
> **메인보드를 Jetson Orin Nano Super → 라즈베리파이로 전환하며 TOP 카메라 YOLO26 추론도
> 엣지→GPU 서버로 이관** — 라즈베리파이는 추론 성능이 부족해 엣지 단독 추론이 불가능해짐.
> 이 결정으로 GPU 서버가 실시간 경로에 들어옴(단, LLM이 아니라 YOLO26 `inference`만, SIDE는
> 애초에 GPU 미사용). 상세는 위 "탐지 파이프라인" 참고

- 개발: Windows+Docker, 로컬 웹캠 테스트(기존과 동일)
- **배포**: `backend`+`mongo`는 로컬 `<LOCAL_BACKEND_IP>`(확정, 실제 값은 Notion 참고)에서
  `docker compose up backend mongo`로 실행. `training`/`inference`/`llm`은 GPU 서버로 이전해서
  `training`/`llm`은 `docker compose --profile training up`/`--profile llm up`(둘 다 자동
  라벨링 검증 파이프라인 돌 때만 같이 기동), `inference`는 `docker compose up inference`
  (YOLO26 TOP 모델 상시 추론, 상시 기동)로 실행 — **하나의 `docker-compose.yml`을 그대로
  쓰되, 호스트/시점마다 띄우는 서비스 조합만 다름**(별도 compose 파일 분리 불필요)
- **로컬(라즈베리파이 TOP) → GPU 서버 `inference` 컨테이너 연결은 상시 필요** — TOP 카메라
  라즈베리파이의 RTSP를 SSH 역터널로 GPU 서버까지 계속 흘려보내야 YOLO26 상시 추론이 가능
  (**TOP 카메라 포트 1개만** — SIDE는 룰 베이스로 로컬 백엔드에서만 처리해서 GPU로 안 감).
  끊기면 그 순간 탐지가 통째로 멈추는 **단일 장애점**이라 `training`/`llm`의 간헐적 연결보다
  안정성 요구가 훨씬 높음 — `autossh` 등 자동 재연결 검토 필요(아래 TBD 참고). 같은 RTSP
  스트림을 로컬 백엔드도 LAN으로 그대로 받아 관리자 웹 실시간 송출에 씀(`cameraManager.py`
  변경 불필요, TOP 라즈베리파이의 RTSP 서버 하나에 클라이언트 2곳: 로컬 백엔드+GPU 서버).
  SIDE 라즈베리파이는 로컬 백엔드 클라이언트 1곳뿐(GPU 역터널 불필요)
- **백엔드(로컬) → LLM(GPU 서버) 실시간 연결은 여전히 불필요** — 이건 향후 LLM을 실시간
  탐지 경로에 쓰게 될 때 얘기고, 지금 진행 중인 자동 라벨링 검증은 `training`↔`llm`이 둘 다
  GPU 서버 안에 있어 SSH 터널 없이 컨테이너 간 통신으로 충분함. 실시간 경로에 쓰게 되면 그때
  SSH 터널(예: `ssh -p 2222 -L 8100:localhost:8100 soma@<GPU_SERVER_IP>`)을 상시 유지해야 함
- **`training`(GPU 서버) → MongoDB(로컬) 연결은 상시 필요** — 학습용 원본 이미지를
  로컬 GridFS에서 그대로 가져다 쓰기로 확정(위 "이벤트 적재" 참고)해서, 학습/라벨링 돌릴
  때마다 역방향 터널(위 라즈베리파이 RTSP 터널과 같은 SSH 세션에 포트만 추가)이 필요함
- **GPU 연산 자체는 `training`/`inference`/`llm` 컨테이너만 사용**(셋 다 실제로 씀 — `llm`은
  자동 라벨링 검증용) — DB/백엔드가 로컬로 빠지면서 이 구분은 자연히 유지됨(`docker run --gpus`는
  `training`/`inference`/`llm`에만 적용)
- 서버 CPU/RAM이 팀별로 분리되는지(GPU만 분리되는지)는 서버 관리자 확인 필요(TBD)
- GPU 패스스루: nvidia-docker 필요
- **GPU 서버는 다인 공유 환경**(팀 5명뿐 아니라 다른 수강생들도 같은 호스트 공유) — 계정 격리,
  rootless Docker, GPU 카드 지정, 포트포워딩(SSH 터널) 등 실무 절차는 `gpuServerOps.md` 참고
- 영상 소스는 `.env`의 `CAMERA_SOURCE_<CameraId>`(예: `CAMERA_SOURCE_ELEVTOP`)만 환경별로 교체, 코드 불변

## 웹캠 시뮬레이션 (메인보드 입고 전) — 구현됨

- `streaming/cameraManager.py`: `CameraId`(`schemas/event.py`)마다 별도 `CameraManager` 인스턴스로 관리
  (`GET /api/stream/{cameraId}`, role 파라미터 없음 — 카메라 1대=지점 1개=1`CameraId`). `.env`
  키는 `CAMERA_SOURCE_ELEVTOP`/`CAMERA_SOURCE_ELEVSIDE`/`CAMERA_SOURCE_REST4F01`(하이픈 제거+대문자).
  `ELEV-TOP`만 기본값 `0`이라 로컬 웹캠 1대짜리 개발 환경에서 바로 동작. 나머지는 미설정 시
  해당 `cameraId` 요청만 503(다른 지점엔 영향 없음)
- 입고 후 CameraId별 독립 RTSP로 교체(소스 문자열만 RTSP URL로 교체, 로직 불변)
- `cv2.VideoCapture().read()` 동기 블로킹 → `asyncio.to_thread()`로 감쌈(적용 완료)
- **로컬에서 RTSP 경로 미리 테스트**: `debug/streaming/startRtspSim.py` — 이 PC의 웹캠 여러 대를
  각각 다른 지점(`CameraId`)에 할당해서, 지점별로 독립된 라즈베리파이 역할(FFmpeg+MediaMTX로
  RTSP 송신)을 동시에 흉내냄. `infra/checkEnv.py`처럼 필요한 것 자동 설치하지만, RTSP
  테스트하는 사람만 필요해서 `checkEnv.py`와는 별도 유지(`debug/db/`와 같은 패턴).
  WebApps/backend·docker-compose.yml과 무관 — 백엔드는 수정 없이 그대로 RTSP 수신

## 메인보드(라즈베리파이) 엣지 코드 (미착수)

> **Jetson Orin Nano Super 발주 건은 완전히 취소, 라즈베리파이로 확정 대체.** 이유: 애초
> Orin을 쓰려던 목적(YOLO26 엣지 상시 추론)이 라즈베리파이로는 성능상 불가능해서, YOLO26을
> GPU 서버(`inference`)로 이관(위 "탐지 파이프라인" 참고)하기로 하면서 메인보드에 고성능
> NPU/GPU가 더 이상 필요 없어짐 — 캡처+RTSP 송신+GPIO/스피커만 하면 되는 역할이라 라즈베리
> 파이로 충분.

**추론 없음, 캡처+송신+RPA 출력만 담당**(위 "탐지 파이프라인"의 "역할 분담" 참고):

1. 웹캠(또는 카메라 모듈)→RTSP 송신: GStreamer 또는 ffmpeg. 라즈베리파이는 표준 Linux
   배포판(Raspberry Pi OS)이라 별도 SDK 제약 없음(TOP/SIDE 둘 다 동일)
2. **TOP만** GPU 서버 `inference`가 도달할 수 있도록 RTSP를 SSH 역터널로 노출(위 "배포 전략"
   참고) — 같은 스트림을 로컬 백엔드에도 LAN으로 그대로 흘려 관리자 웹 송출에 사용(TOP은
   듀얼 클라이언트: 로컬 백엔드+GPU 서버). **SIDE는 로컬 백엔드에만** RTSP를 흘리면 됨(GPU
   역터널 불필요 — 룰 베이스 판정이 로컬 백엔드에서 돎)
3. 로컬 백엔드로부터 RPA 트리거 신호 수신 → **GPIO(릴레이 경유 전구 점등)** + **스피커
   (USB 또는 3.5mm 오디오잭, Python에서 `aplay` 서브프로세스 등으로 경고음 재생)** 출력.
   `RPAs/alertController.py`는 현재 중앙에서 Mock 처리 중, 라즈베리파이 쪽으로 이전 예정.
   신호 전달 방식(MQTT/HTTP/WS) TBD

라즈베리파이(Raspberry Pi OS)는 표준 최신 Python(3.11+)을 쓸 수 있어 `WebApps/backend`와
문법 호환성 문제 없음 — 과거 Jetson Nano 4GB의 Python 3.6 제약 이슈는 애초에 해당 없음.

## RPA 정책

- 오분류 시 전구+경고음 즉시 자동 트리거(재전파 없음)
- `COLLECT` 모드: 알림 전부 Mute, 탐지 로직은 계속 동작(통계만 갱신)

## 이벤트 적재

- 매 프레임 Insert 금지, 판정 시점만 저장
- `eventCategory`로 구분: misclassification(투기, 분류 결과 포함) / overflow(넘침, 분류 없이 영상만)
- **물리 쓰레기통 4개**(일반/플라스틱·캔/커피컵/종이, `binId`)가 옆 카메라(`ELEV-SIDE`) 시야
  안에 고정 설치. "플라스틱·캔" 통(`binType=plasticCan`)은 캔과 플라스틱을 물리적으로
  같이 받지만, AI는 `DetectedClass`에서 `plastic`/`can`을 별도 클래스로 구분(이미 학습
  중) — `isMisclassified` 판정 시 `plastic`/`can` 둘 다 `plasticCan`에 매핑해서 비교
  (다대일 관계, 상세는 `Docs/ERD.md` 참고). 각 통의 현재 상태(`NORMAL`/`FULL`)를 별도
  `BIN_STATES`로 지속 추적하고,
  **`NORMAL`→`FULL`로 전환되는 순간에만** overflow `EVENT` 생성+알림(기존 "5초 Cooldown"
  방식 폐기 — 상세는 `Docs/ERD.md` 참고). misclassification은 동일 카메라+클래스 5초
  Cooldown 그대로 유지
- **`EVENT`에 `detectionId`(DB 유니크, 중복 저장 방지)/`trackingId`(YOLO26 추적 ID, 디버깅용)/
  `modelVersion`/`binId`/`binType` 필드 반영 완료** — `schemas/event.py`,
  `repositories/eventRepository.py`, `services/eventService.py`에 구현. 상세는 `Docs/ERD.md` 참고
- 이미지/영상은 MongoDB GridFS, **버킷을 카메라별로 2개 분리 구현 완료**(`topMedia`=위 카메라/투기,
  `sideMedia`=옆 카메라/넘침) — 물리 DB 분리 아니고 같은 DB 안 GridFS 버킷만 나눈 것(연결/인증
  추가 불필요). 순수 저장 구조 관리 편의 목적, 보관정책 차이는 없음(`EVENT` 컬렉션 자체는
  카메라별로 안 나누고 하나로 유지 — 상세는 `Docs/ERD.md` 참고)
- **학습용 원본 이미지는 로컬 GridFS 재사용으로 확정**(GPU 서버 로컬 디스크 축적 방식은 기각) —
  `training`(GPU 서버)이 학습 때마다 로컬(`<LOCAL_BACKEND_IP>`) GridFS에 네트워크로 직접 접속.
  역방향 SSH 터널 필요(아래 "배포 전략" 참고)

## Event Flow

```
Detect → Create Event → Save Event → Check mode
  ├─ COLLECT: 통계만 갱신
  └─ MANAGE: WS Broadcast + RPA 트리거 → 통계 갱신
```

## 포트

| 항목 | 값 |
|---|---|
| 백엔드 | 8047 (기본값 8000 대신, 타 팀 충돌 방지) |
| MongoDB 호스트 | 27020 (컨테이너 내부 27017) |

## DB 접속 (팀 공유 vs 로컬)

> ⚠️ **MongoDB를 GPU 서버(`e8000`)로 이전했던 최근 작업은 이번 "백엔드+DB는 로컬" 재조정으로
> 보류됨** — GPU 서버 `mongo` 컨테이너에 만들어둔 `root`+`user01`~`05` 계정·데이터는 당장은
> 안 쓰임(나중에 재활용할 수도 있어 지우진 않음). **"로컬" 호스트는 `<LOCAL_BACKEND_IP>`로 확정**
> (실제 값은 Notion 참고) — 과거 `<LEGACY_SHARED_SERVER_IP>`(팀 공유 서버)와는 별개.

- `.env`의 `MONGO_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`를 팀원마다 다르게 설정
  - **팀 배포(확정)**: `MONGO_HOST=<LOCAL_BACKEND_IP>`(실제 값은 Notion 참고)
  - 개인 로컬 개발용: `MONGO_HOST=localhost`
- `infra/checkEnv.py`, `debug/db/testDbConnection.py`, `debug/db/testCrud.py` 세 스크립트가 `.env` 키 공유 — 값 다르면 결과 엇갈림
- 디버그 스크립트는 Atlas → 로컬/자체 Docker로 전환(`mongodb+srv://` → `mongodb://`+포트)
- **팀 공유 서버 계정**: 공유 Mongo는 팀원별 계정(`user01`~`user05`, `sortMaster` DB에
  `readWrite` 권한만)으로 인증, root(관리자) 계정은 팀장만 보유. 계정 생성 절차는
  `gpuServerOps.md` 참고(GPU 서버 `mongo`용으로 만든 절차지만 다른 호스트에도 동일하게
  적용 가능). 각 팀원은 자기 `.env`의 `DB_USER`/`DB_PASSWORD`를 배정받은 계정으로 채우면 됨

## TBD

- **라즈베리파이(TOP) → GPU 서버 `inference` SSH 역터널 안정성** — 상시 연결이 필요한
  단일 장애점(끊기면 탐지 전체 중단). `autossh` 등 자동 재연결 방안 검토 필요(SIDE는
  로컬 백엔드 룰 베이스라 해당 없음)
- **GPU 서버 `inference` 컨테이너 실제 구현 미착수** — FastAPI+ultralytics 등 구체 스택,
  Dockerfile, `docker-compose.yml` 서비스 정의(GPU 카드 공유 방식은 `training`/`llm` 패턴
  재사용 예정) 전부 TBD
- **GPU 카드 공유 시 `inference`(상시)-`training`(간헐) 동시 실행 지연/자원 경합 실측 필요** —
  `inference`가 상시 기동으로 바뀌면서 `llm`-`training` 조합보다 경합 빈도가 높아짐
- 라즈베리파이 RTSP를 GPU 서버로 역터널링할 때 **역터널을 어느 호스트에서 실행할지**(라즈베리
  파이 자체 vs 로컬 백엔드 호스트) 미정
- LLM 자동 라벨링 검증의 세부 프롬프트/자동 라벨링 도구 구현(진행 중), "환경별 통 모양 인식
  데이터 생성"의 구체적 방식(아직 미착수)
- `DetectedClass`→`binType` 매핑표를 어디에 둘지(GPU `inference` 코드 하드코딩 vs 설정 파일
  등) — 매핑표 자체는 확정(`Docs/ERD.md` 참고), 위치만 미정
- misclassification Cooldown 5초 조정 여부(overflow는 상태 전환 기반으로 확정돼 별도
  Cooldown 없음 — 해결된 TBD 참고)
- 경고 전구 HW/GPIO 연동 상세, 라즈베리파이↔중앙 백엔드(RPA 트리거)/GPU 서버↔백엔드(판정
  결과) 신호 전달 방식(MQTT/HTTP/WS, 둘 다 미정)
- 안면인식 레포 포함 여부
- **GPU 서버 CPU/디스크/네트워크 병목 실측**: GPU(VRAM)는 팀별 카드 분리로 경합 없음
  확인됨(아래 "해결된 TBD" 참고). CPU(192스레드)/디스크(2.8GB/s)는 여유 있어 보이지만
  다른 팀과 공유라 완전히 보장은 안 됨. **네트워크**는 TOP 라즈베리파이→GPU 서버로 RTSP가
  상시 스트리밍되는 구조라(엣지 단독 시절 기대했던 "감지 시에만 전송" 절감 효과가 사라짐,
  단 SIDE는 로컬 백엔드 처리라 이 부담이 없음)
  대역폭/지연 실측이 오히려 더 중요해짐 — 메인보드 입고 후 최우선 실측 필요

## 해결된 TBD

과거 결정 이력(왜 이렇게 정했는지)은 `decisionLog.md`로 옮김 — **자동 로드 안 함**, 필요할
때만 열어볼 것. 현재 상태는 위 본문 섹션들에 이미 다 반영돼 있음.
