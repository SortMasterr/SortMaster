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
| 위치(MVP) | 12층 1곳만 우선 진행(카메라 2대). 고도화 단계에 4층(`REST-4F-01` 추정, 확정 아님) 위 카메라 1대 추가 예정 |
| 메인보드 | Jetson Nano, 입고 약 2주 소요 |
| 카메라 구성 | **지점당 위(Top)+옆(Side) 2대**. 위: 상시 ROI 모니터링(YOLO-Nano 트리거용). 옆: 정밀 캡처(LLM 분류용)+투척 동작/투입 위치 판단(YOLO) |
| 카메라 스펙 | 웹캠 실촬영 해상도 **640×480**(약 30만 화소). YOLO 입력 전처리는 **640×640**으로 통일(레터박스 패딩 방식 — 비율 유지, 단순 리사이즈 아님). 크롭 좌표를 LLM에 넘길 때 패딩 오프셋 보정 필요 |
| 배포 구조 | 지점별 독립 메인보드, 지점당 웹캠 2대(위+옆) |
| 클래스 | general, paper, plastic(coffeeCup 별도), mixed, uncertain |

## 탐지 파이프라인 (YOLO 2단계 + LLM 분류, 확정)

- **상시 감시(경량, 위 카메라)**: YOLOv8-Nano 상주, ROI(쓰레기통 위치 고정) 내 객체 분석, 실시간 프레임 스캔, 메모리 ~300MB
- **트리거 조건**(ROI 내 객체 조합으로 즉시 판단):
  - 손 O + 쓰레기 O → **투기 이벤트**(=기존 오분류 탐지) → 아래 비동기 처리로
  - 손 X + 쓰레기 O → **넘침 이벤트**(쓰레기통 포화) → LLM 호출 없이 영상 녹화만
- **투기 이벤트 처리(비동기 2갈래 병행, LLM 응답 대기로 실시간 추적 블로킹 금지)**:
  1. **YOLO(실시간, 옆 카메라 위주)**: 투척 동작 감지 + 어느 위치/통에 들어갔는지 계속 추적·판단. LLM 응답을 기다리지 않고 진행
  2. **LLM/VLM(비동기 호출, 분류 전담)**: 옆 카메라가 캡처한 크롭 이미지(YOLO가 이미 위치 특정해서 넘김, LLM은 재탐지 안 함)를 받아 물체 종류만 분류. **Qwen3-VL-8B(dense)** 사용(API 비용 없음)
  - 두 결과가 모두 도착하면 백엔드가 합쳐서 최종 오분류 여부 판정 → RPA 트리거
  - **기존 YOLOv8-Medium 정밀분류 단계는 Qwen3-VL-8B로 완전히 대체**(확정)
- **LLM 파인튜닝**: **Qwen3-VL-8B** + LoRA/QLoRA(Unsloth 또는 LLaMA-Factory)로 GPU 1장(48GB) 내 진행. 파인튜닝 후 4/8bit 양자화해 추론 시 VRAM 최소화(backend+YOLO-Nano와 같은 카드에서 동시 서빙 가능하도록). Full fine-tuning이나 32B/235B(MoE) 등 상위 사이즈는 단일 카드로 비현실적이라 배제. 데이터 규모에 따라 수시간~하루 내 소요 예상. 학습 작업과 실시간 서비스가 같은 카드를 쓰므로 트래픽 적은 시간대 학습 권장. 라이선스는 배포 전 해당 사이즈 조항 확인 필요
- 전부 **중앙 GPU 서버에서 처리 확정** — 어차피 RTSP가 계속 중앙으로 들어오므로 엣지에서 중복 처리할 이유 없음. 젯슨 나노는 캡처+RTSP 송신+GPIO 알림 수신만 담당(모델 미탑재)

## 추론 인프라

- NVIDIA L40S 총 4장, **팀당 1장씩 전용 할당**(다른 팀과 경합 없음 — VRAM 경합은 팀 내부 backend/DB/학습/추론 컨테이너 사이에서만 고려하면 됨)
- 메인보드 → RTSP → 중앙(GPU 1장)에서 탐지+분류 수행 (엣지 추론 아님)
- 탐지 모델 확정: YOLOv8-Nano(상시감시+투척판단) + **Qwen3-VL-8B(정밀분류, YOLOv8-Medium 대체)** — 상세는 위 "탐지 파이프라인" 참고
- **컨테이너 3개**: `backend` / `mongo` / `training`(GPU). `training`은 라벨링·학습(YOLO 재학습+LLM 파인튜닝) 때만 기동 → `best.pt` 등 산출물 나오면 내리고 평소엔 `backend`+`mongo`만 상시 구동

## 배포 전략

- 개발: Windows+Docker, 로컬 웹캠 테스트
- 배포: 동일 이미지를 할당받은 GPU 1장으로 이전
- MVP: 백엔드+DB+추론(학습 포함)을 GPU 서버 안에 전부 배포. 단 **GPU 연산 자체는
  탐지/추론 컨테이너만 사용**, DB/백엔드는 GPU 미사용(CPU/RAM만) — VRAM은
  탐지 모델 몫으로 남겨둠 (`docker run --gpus`는 추론 컨테이너에만 적용)
- 서버 CPU/RAM이 팀별로 분리되는지(GPU만 분리되는지)는 서버 관리자 확인 필요(TBD)
- GPU 패스스루: nvidia-docker 필요
- 영상 소스는 `.env`의 `CAMERA_SOURCE`(위)/`CAMERA_SOURCE_SIDE`(옆)만 환경별로 교체, 코드 불변

## 웹캠 시뮬레이션 (메인보드 입고 전) — 구현됨

- `streaming/cameraManager.py`: 지점당 위(top)/옆(side) 카메라 각각 별도 `CameraManager` 인스턴스로 관리(`GET /api/stream/{cameraId}?role=top|side`). 웹캠이 1대뿐이면 `CAMERA_SOURCE_SIDE`를 비워두면 되고, 그 경우 `role=side` 요청만 503(다른 기능엔 영향 없음)
- 입고 후 CameraId별 독립 RTSP로 교체(소스 문자열만 RTSP URL로 교체, 로직 불변)
- `cv2.VideoCapture().read()` 동기 블로킹 → `asyncio.to_thread()`로 감쌈(적용 완료)
- **로컬에서 RTSP 경로 미리 테스트**: `debug/streaming/startRtspSim.py` — 이 PC 웹캠 2대로
  젯슨 나노 역할(FFmpeg+MediaMTX로 RTSP 송신)을 흉내냄. `infra/checkEnv.py`처럼 필요한 것
  자동 설치하지만, RTSP 테스트하는 사람만 필요해서 `checkEnv.py`와는 별도 유지(`debug/db/`와
  같은 패턴). WebApps/backend·docker-compose.yml과 무관 — 백엔드는 수정 없이 그대로 RTSP 수신

## 젯슨 나노 엣지 코드 (미착수)

역할은 캡처+RTSP 송신+GPIO뿐, 탐지 모델(Nano/Medium) 미탑재(전부 중앙 GPU 처리).

1. 웹캠→RTSP 송신: GStreamer(JetPack 포함) 예정. 1단계 웹캠 뷰어(Py 3.11)는 노트북 테스트 완료
2. 중앙 신호 수신→GPIO 트리거: 설계 전. `RPAs/alertController.py`는 현재 중앙에서 Mock 처리 중, 젯슨 쪽으로 이전 가능성. 전달 방식(MQTT/HTTP/WS) TBD

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

## TBD

- `mixed`/`uncertain` 클래스 세부 정의
- Cooldown 5초 조정 여부, overflow의 Cooldown 기준
- 경고 전구 HW/GPIO 연동, 젯슨↔중앙 신호 전달 방식
- 학습용 원본 이미지 저장 방식
- 안면인식 레포 포함 여부
- **지점당 카메라 2대(위+옆) 체계에서 CameraId 스키마 미정** — `.agentfiles/apiSpec.md`의 `CameraId` enum(`ELEV-01/ELEV-02/REST-4F-01`)은 카메라 1대=1지점 가정으로 작성됨. 지점 1개 ID로 통합(내부에서 위/옆 2개 스트림 처리)할지, 카메라별 별도 ID로 나눌지 결정 필요. `GET /api/stream/{cameraId}`(단일 스트림 반환) 스펙에도 영향
- 최종 설치 지점 구성(엘리베이터 2대+4층 1대 유지 여부, MVP의 "12층"과의 관계) 재확인 필요

## 해결된 TBD

- Git 브랜치 전략 → `Docs/skills/github/README.md`
- IDE/AI 코딩 툴 → 개인별 사용
- 탐지 모델/프레임워크 → YOLOv8-Nano(상시감시+투척판단) + Qwen3-VL-8B(정밀분류, LoRA/QLoRA 파인튜닝) 확정. YOLOv8-Medium은 Qwen3-VL-8B로 대체
- GPU 배분 → L40S 4장 중 팀당 1장 전용 할당(타 팀과 경합 없음)
