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
| 위치(최종 목표) | 엘리베이터 2대(`ELEV-01`,`ELEV-02`), 4층 휴게실 1대(`REST-4F-01`) — MVP 이후 순서/구성 재확인 필요 |
| 위치(MVP) | 카메라 지점은 위+옆 2개, `CameraId`는 `ELEV-TOP`/`ELEV-SIDE`로 확정(지점 번호 없음 — 기존 `ELEV-01`/`ELEV-02` 2곳 동시 운영 구도와 어떻게 맞물리는지는 TBD 참고). 4층(`REST-4F-01`)은 고도화 단계에 추가 예정 |
| 메인보드 | Jetson Nano, 입고 약 2주 소요 |
| 카메라 구성 | **"카메라 1대 = 지점 1개 = `CameraId` 1개 = 독립 젯슨 나노 1대" 규칙은 그대로 유지**(안 깨짐). `CameraId` 명명 확정: `ELEV-TOP`/`ELEV-SIDE`(위/옆 각도 구분만, 설치 위치 번호는 없음). `.env` 키는 기존 하이픈 제거 규칙 그대로 `CAMERA_SOURCE_ELEVTOP`/`CAMERA_SOURCE_ELEVSIDE` |
| 카메라 스펙 | 웹캠 실촬영 해상도 **640×480**(약 30만 화소). YOLO 입력 전처리는 **640×640**으로 통일(레터박스 패딩 방식 — 비율 유지, 단순 리사이즈 아님). 크롭 좌표를 LLM에 넘길 때 패딩 오프셋 보정 필요 |
| 배포 구조 | 지점별(카메라별) 독립 메인보드+카메라 1대 — 기존과 동일, 설치 위치당 지점 수만 2개로 늘어남 |
| 클래스 | general, paper, plastic(coffeeCup 별도), mixed, uncertain |

## 탐지 파이프라인 (YOLO26 + LLM 분류, 확정)

카메라 1대당 젯슨 나노 1대(위/옆 각각 독립 세트)에서 캡처한 두 영상을 각각 RTSP로 중앙
GPU 서버에 실시간 송신. **손 감지 조건은 폐지** — 기존 "손 O/X + 쓰레기 O" 조합 판정 방식은
더 이상 쓰지 않고, 쓰레기 감지 자체가 트리거.

- **넘침(overflow) 판정**: **옆 카메라**가 쓰레기통 넘침 상태를 감지 → 넘침 확인되면
  **위 카메라**로 어느 쓰레기통이 넘쳤는지 위치 특정. LLM 호출 없이 영상 녹화만(기존과 동일)
- **투기(misclassification) 판정**:
  1. **YOLO26**(GPU 서버 상시 구동, 젯슨→RTSP로 수신한 영상 처리)이 쓰레기 감지
  2. 감지 즉시 **LLM(Qwen3-VL-8B, 비동기 호출)**로 쓰레기 종류 분류 시작 — 이 응답을
     기다리지 않고 YOLO26은 계속 추적 진행(실시간 추적 블로킹 금지)
  3. YOLO26이 투척 완료 시점과 투척된 위치(어느 통에 들어갔는지)를 계속 추적·판단
  4. 두 결과가 모두 도착하면 백엔드가 합쳐서 판정 — **투척된 위치(통)와 LLM이 분류한
     쓰레기 종류가 일치하는지 비교**해 최종 오분류 여부 확정 → 불일치 시 RPA 트리거
  - **투기 판정에서 위/옆 카메라 역할 분담(어느 쪽이 감지, 어느 쪽이 크롭 이미지 제공)은
    미정 — 아래 "TBD" 참고**
  - **기존 YOLOv8-Medium 정밀분류 단계는 Qwen3-VL-8B로 완전히 대체**(변경 없음, 유지)
- **LLM 파인튜닝**: **Qwen3-VL-8B** + LoRA/QLoRA(Unsloth 또는 LLaMA-Factory)로 GPU 1장(48GB) 내 진행. 파인튜닝 후 4/8bit 양자화해 추론 시 VRAM 최소화(backend+YOLO26과 같은 카드에서 동시 서빙 가능하도록). Full fine-tuning이나 32B/235B(MoE) 등 상위 사이즈는 단일 카드로 비현실적이라 배제. 데이터 규모에 따라 수시간~하루 내 소요 예상. 학습 작업과 실시간 서비스가 같은 카드를 쓰므로 트래픽 적은 시간대 학습 권장. 라이선스는 배포 전 해당 사이즈 조항 확인 필요
- 전부 **중앙 GPU 서버에서 처리 확정** — 어차피 RTSP가 계속 중앙으로 들어오므로 엣지에서 중복 처리할 이유 없음. 젯슨 나노는 캡처+RTSP 송신+GPIO 알림 수신만 담당(모델 미탑재)

## 추론 인프라

- NVIDIA L40S 총 4장, **팀당 1장씩 전용 할당**(다른 팀과 경합 없음 — VRAM 경합은 팀 내부 backend/DB/학습/추론 컨테이너 사이에서만 고려하면 됨)
- 메인보드 → RTSP → 중앙(GPU 1장)에서 탐지+분류 수행 (엣지 추론 아님)
- 탐지 모델 확정: YOLO26(상시감시+투척판단) + **Qwen3-VL-8B(정밀분류, YOLOv8-Medium 대체)** — 상세는 위 "탐지 파이프라인" 참고
- **컨테이너 3개**: `backend` / `mongo` / `training`(GPU). `training`은 라벨링·학습(YOLO 재학습+LLM 파인튜닝) 때만 기동 → `best.pt` 등 산출물 나오면 내리고 평소엔 `backend`+`mongo`만 상시 구동
- `training` 컨테이너는 JupyterLab을 띄워서 팀원이 브라우저로 같이 접속해 학습 코드 작성
  (`.env`의 `JUPYTER_PORT`/`JUPYTER_TOKEN`, 진짜 멀티유저 격리는 아니라 동시 실행 지양).
  GPU 서버 운영 실무(계정/rootless Docker/포트/SSH 터널 등)는 `gpuServerOps.md` 참고

## 배포 전략

- 개발: Windows+Docker, 로컬 웹캠 테스트
- 배포: 동일 이미지를 할당받은 GPU 1장으로 이전
- MVP: 백엔드+DB+추론(학습 포함)을 GPU 서버 안에 전부 배포. 단 **GPU 연산 자체는
  탐지/추론 컨테이너만 사용**, DB/백엔드는 GPU 미사용(CPU/RAM만) — VRAM은
  탐지 모델 몫으로 남겨둠 (`docker run --gpus`는 추론 컨테이너에만 적용)
- 서버 CPU/RAM이 팀별로 분리되는지(GPU만 분리되는지)는 서버 관리자 확인 필요(TBD)
- GPU 패스스루: nvidia-docker 필요
- **GPU 서버는 다인 공유 환경**(팀 5명뿐 아니라 다른 수강생들도 같은 호스트 공유) — 계정 격리,
  rootless Docker, GPU 카드 지정, 포트포워딩(SSH 터널) 등 실무 절차는 `gpuServerOps.md` 참고
- 영상 소스는 `.env`의 `CAMERA_SOURCE_<CameraId>`(예: `CAMERA_SOURCE_ELEV01`)만 환경별로 교체, 코드 불변

## 웹캠 시뮬레이션 (메인보드 입고 전) — 구현됨(신규 지점 반영 전, `CameraId` 항목 추가 필요)

> ⚠️ "카메라 1대=지점 1개=1`CameraId`" 구조 자체는 안 바뀜(위 "설치 환경" 참고) — 다만
> 지점 수가 늘어난 만큼(설치 위치당 위/옆 2개) `CameraId` Enum과 `.env`의
> `CAMERA_SOURCE_<CameraId>` 키를 새 지점 수만큼 추가해야 함. 정확한 `CameraId` 명명
> 규칙은 TBD.

- `streaming/cameraManager.py`: `CameraId`(`schemas/event.py`)마다 별도 `CameraManager` 인스턴스로 관리
  (`GET /api/stream/{cameraId}`, role 파라미터 없음 — 카메라 1대=지점 1개=1`CameraId`). `.env`
  키는 `CAMERA_SOURCE_ELEV01`/`CAMERA_SOURCE_ELEV02`/`CAMERA_SOURCE_REST4F01`(하이픈 제거+대문자).
  `ELEV-01`만 기본값 `0`이라 로컬 웹캠 1대짜리 개발 환경에서 바로 동작. 나머지는 미설정 시
  해당 `cameraId` 요청만 503(다른 지점엔 영향 없음)
- 입고 후 CameraId별 독립 RTSP로 교체(소스 문자열만 RTSP URL로 교체, 로직 불변)
- `cv2.VideoCapture().read()` 동기 블로킹 → `asyncio.to_thread()`로 감쌈(적용 완료)
- **로컬에서 RTSP 경로 미리 테스트**: `debug/streaming/startRtspSim.py` — 이 PC의 웹캠 여러 대를
  각각 다른 지점(`CameraId`)에 할당해서, 지점별로 독립된 젯슨 나노 역할(FFmpeg+MediaMTX로
  RTSP 송신)을 동시에 흉내냄. `infra/checkEnv.py`처럼 필요한 것 자동 설치하지만, RTSP
  테스트하는 사람만 필요해서 `checkEnv.py`와는 별도 유지(`debug/db/`와 같은 패턴).
  WebApps/backend·docker-compose.yml과 무관 — 백엔드는 수정 없이 그대로 RTSP 수신

## 젯슨 나노 엣지 코드 (미착수)

역할은 캡처+RTSP 송신+GPIO뿐, 탐지 모델(YOLO26/Qwen3-VL-8B) 미탑재(전부 중앙 GPU 처리).

1. 웹캠→RTSP 송신: GStreamer(JetPack 포함) 예정. 1단계 웹캠 뷰어(Py 3.11)는 노트북 테스트 완료
2. 중앙 신호 수신→GPIO 트리거: 설계 전. `RPAs/alertController.py`는 현재 중앙에서 Mock 처리 중, 젯슨 쪽으로 이전 가능성. 전달 방식(MQTT/HTTP/WS) TBD

> **주의**: 원조 Jetson Nano(4GB)는 JetPack 4.6.x(Ubuntu 18.04, Python **3.6**)가 마지막 지원
> 버전 — `WebApps/backend`의 Python 3.11 문법(`str | None`, `@dataclass`, `asyncio.run()` 등)은
> 젯슨 쪽 코드에 그대로 못 씀. 상세는 `gpuServerOps.md` 참고

## RPA 정책

- 오분류 시 전구+경고음 즉시 자동 트리거(재전파 없음)
- `COLLECT` 모드: 알림 전부 Mute, 탐지 로직은 계속 동작(통계만 갱신)

## 이벤트 적재

- 매 프레임 Insert 금지, 이벤트 시점만 저장
- `eventCategory`로 구분: misclassification(투기, 정밀분류 결과 포함) / overflow(넘침, 분류 없이 영상만)
- 동일 카메라+클래스 5초 Cooldown(조정 TBD), overflow의 Cooldown 기준은 별도 TBD
- 이미지/영상은 MongoDB GridFS
- 학습용 원본 이미지 저장 방식 TBD(GridFS 재사용 vs GPU 서버 로컬 디스크)

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

- `.env`의 `MONGO_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`를 팀원마다 다르게 설정
  - 팀 공유: `MONGO_HOST=192.168.0.30`
  - 로컬(`my-mongo`): `MONGO_HOST=localhost`
- `infra/checkEnv.py`, `debug/db/testDbConnection.py`, `debug/db/testCrud.py` 세 스크립트가 `.env` 키 공유 — 값 다르면 결과 엇갈림
- 디버그 스크립트는 Atlas → 로컬/자체 Docker로 전환(`mongodb+srv://` → `mongodb://`+포트)
- **팀 공유 서버 계정**: 공유 Mongo는 팀원별 계정(`user01`~`user05`, `sortMaster` DB에
  `readWrite` 권한만)으로 인증, root(관리자) 계정은 팀장만 보유. 계정 생성 절차는
  `gpuServerOps.md` 참고. 각 팀원은 자기 `.env`의 `DB_USER`/`DB_PASSWORD`를 배정받은
  계정으로 채우면 됨

## TBD

- `mixed`/`uncertain` 클래스 세부 정의
- Cooldown 5초 조정 여부, overflow의 Cooldown 기준
- 경고 전구 HW/GPIO 연동, 젯슨↔중앙 신호 전달 방식
- 학습용 원본 이미지 저장 방식
- 안면인식 레포 포함 여부
- **투기(misclassification) 판정에서 위/옆 카메라 역할 분담 미정** — 넘침 판정은 옆(감지)/위(위치
  특정)로 정해졌지만, 투기 판정 쪽은 YOLO26/LLM 어느 단계에 어느 카메라를 쓰는지 미정(위
  "탐지 파이프라인" 섹션 참고)
- **`CameraId`에 설치 위치 번호가 빠짐** — `ELEV-TOP`/`ELEV-SIDE`는 위/옆 각도만 구분하고
  설치 위치(엘리베이터) 번호가 없음. 기존엔 `ELEV-01`/`ELEV-02` 2곳을 동시 운영하는
  구도였는데, 이 이름으로는 두 곳을 구분 못 함 — 지점이 1곳으로 축소된 건지, 두 번째
  설치 위치는 나중에 다른 이름을 쓸 건지 확인 필요
- 최종 설치 지점 구성(엘리베이터 2대+4층 1대 유지 여부) 재확인 필요
- **GPU 서버 CPU/디스크/네트워크 병목 실측**: GPU(VRAM)는 팀별 카드 분리로 경합 없음
  확인됨(아래 "해결된 TBD" 참고). CPU(192스레드)/디스크(2.8GB/s)는 여유 있어 보이지만
  다른 팀과 공유라 완전히 보장은 안 됨. 특히 **네트워크는 미측정** — 젯슨 나노 여러 대가
  동시에 RTSP를 GPU 서버로 쏘는 상황에서 대역폭 병목이 생길 수 있음. 젯슨 나노 입고 후
  다수 스트림 동시 송출 상태로 재측정 필요

## 해결된 TBD

- Git 브랜치 전략 → `Docs/skills/github/README.md`
- IDE/AI 코딩 툴 → 개인별 사용
- 탐지 모델/프레임워크 → YOLO26(상시감시+투척판단, 기존 YOLOv8-Nano에서 변경) + Qwen3-VL-8B(정밀분류, LoRA/QLoRA 파인튜닝) 확정. YOLOv8-Medium은 Qwen3-VL-8B로 대체
- GPU 배분 → L40S 4장 중 팀당 1장 전용 할당(타 팀과 경합 없음)
- **손 감지 트리거 조건 폐지** → "손 O/X + 쓰레기 O" 조합 판정 대신 쓰레기 감지 자체가
  트리거로 확정. 투기/넘침 구분은 카메라 역할(옆=넘침 감지, 위=위치 특정)과 YOLO26↔LLM
  판정 로직으로 대체(위 "탐지 파이프라인" 참고)
- **카메라 지점 구성** → 위+옆 2개(=젯슨나노 2대)로 확정, `CameraId`는 `ELEV-TOP`/`ELEV-SIDE`로
  확정. "카메라 1대 = 지점 1개 = `CameraId` 1개 = 독립 젯슨나노 1대" 규칙 자체는 유지(안 깨짐).
  단, 설치 위치(엘리베이터) 번호 처리는 미확정 — 위 "TBD" 참고
