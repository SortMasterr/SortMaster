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
  확정(설치 위치 번호 불필요 — 위치가 1곳뿐이라서). 4층 휴게실(`REST-4F-01`) 추가는 고도화
  단계 스트레치 목표(진행 여부 미정, 시간 남으면 검토) |
| 메인보드 | **Jetson Nano 4GB 발주 무산 → Jetson Orin Nano Super Developer Kit로 확정**(icbanq 무료 렌탈). 8GB 유니파이드 메모리, JetPack 6.x(Ubuntu 22.04, Python 3.10) |
| 카메라 구성 | **"카메라 1대 = 지점 1개 = `CameraId` 1개 = 독립 젯슨 나노 1대" 규칙 유지**(안 깨짐). 설치 위치 1곳(12층 엘리베이터 앞)에 지점 2개(위+옆). `.env` 키는 기존 하이픈 제거 규칙 그대로 `CAMERA_SOURCE_ELEVTOP`/`CAMERA_SOURCE_ELEVSIDE` |
| 카메라 스펙 | 웹캠 실촬영 해상도 **640×480**(약 30만 화소). YOLO 입력 전처리는 **640×640**으로 통일(레터박스 패딩 방식 — 비율 유지, 단순 리사이즈 아님). 크롭 좌표를 LLM에 넘길 때 패딩 오프셋 보정 필요 |
| 배포 구조 | 지점별(카메라별) 독립 메인보드+카메라 1대 — 설치 위치 1곳에 지점(=메인보드+카메라 세트) 2개 |
| 클래스 | general, paper, plastic(coffeeCup 별도), mixed, uncertain |

## 탐지 파이프라인 (엣지 YOLO26 + 중앙 LLM 분류, 확정)

> **엣지-중앙 하이브리드로 확정**(과거 "전부 중앙 GPU 서버에서 처리" 결정을 뒤집음) — 이전
> TBD였던 "YOLO26을 엣지에서 직접 돌릴지"가 "돌린다"로 해결됨. GPU 서버(`training` 컨테이너)에서
> 학습한 YOLO26 가중치(`.pt`)를 젯슨(Orin Nano Super)에 배포해서 **엣지에서 YOLO26 상시 추론**,
> **중앙 GPU 서버는 LLM(Qwen3-VL-8B) 분류 전담**으로 역할이 나뉨. RTSP도 상시 송출이 아니라
> **엣지가 감지했을 때만 비동기로 전송**(네트워크 상시 부하 감소 — 아래 "TBD"의 병목 우려 완화).
> `.pt` 파일을 GPU→젯슨으로 배포하는 방식은 TBD(SCP 등 미정).

- **넘침(overflow) 판정**(**옆 카메라** 단독, 엣지):
  옆 카메라 젯슨에서 YOLO가 쓰레기통 넘침 상태를 감지하면 **바로 알림 + DB에 시간대 저장**.
  위 카메라의 위치 특정 단계는 폐지(투기 판정과 별개로, 굳이 어느 통인지 분류할 필요 없다고
  판단). LLM 호출 없음
- **투기(misclassification) 판정**(**위 카메라** 단독, 엣지+중앙 하이브리드):
  1. 위 카메라 젯슨에서 **YOLO26(엣지)**이 쓰레기 감지 → 이 시점부터 녹화 시작(DB 저장용)
  2. 감지된 영상을 **비동기로 RTSP를 통해 GPU 서버에 전달**
  3. GPU 서버의 **LLM(Qwen3-VL-8B)**이 영상 속 물체가 어떤 쓰레기인지 분류(쓰레기가 아니면
     "쓰레기 아님"으로 표기) → 결과를 다시 젯슨(엣지)으로 전송
  4. 엣지에서 **YOLO26이 계속 추적한 투척 결과(어느 통에 들어갔는지)**와 **LLM이 보내준 분류
     결과**를 종합해 오분류 여부 판단 → 결과 저장 → 불일치 시 RPA 트리거
  5. 투척 완료 후 **약 3초 텀**을 두고 녹화 종료(과거 "최대 30초 안전캡" 대신 이 값으로 구체화)
  - **기존 YOLOv8-Medium 정밀분류 단계는 Qwen3-VL-8B로 완전히 대체**(변경 없음, 유지)
  - 엣지→중앙 결과 저장 시 실제 신호 전달 방식(MQTT/HTTP/WS)은 여전히 TBD
- **LLM 파인튜닝**: **Qwen3-VL-8B** + LoRA/QLoRA(Unsloth 또는 LLaMA-Factory)로 GPU 1장(48GB) 내 진행. 파인튜닝 후 4/8bit 양자화해 추론 시 VRAM 최소화(backend와 같은 카드에서 동시 서빙 가능하도록). Full fine-tuning이나 32B/235B(MoE) 등 상위 사이즈는 단일 카드로 비현실적이라 배제. 데이터 규모에 따라 수시간~하루 내 소요 예상. 학습 작업과 실시간 서비스가 같은 카드를 쓰므로 트래픽 적은 시간대 학습 권장. 라이선스는 배포 전 해당 사이즈 조항 확인 필요
- **역할 분담**: 젯슨(엣지)은 이제 캡처+RTSP 송신+GPIO뿐 아니라 **YOLO26 추론까지 담당**(모델
  탑재). GPU 서버는 YOLO26 **학습**(`training` 컨테이너) + **Qwen3-VL-8B 분류 추론**만 담당(YOLO26
  상시 추론은 더 이상 GPU 서버 몫이 아님)

## 추론 인프라

- NVIDIA L40S 총 4장, **팀당 1장씩 전용 할당**(다른 팀과 경합 없음 — VRAM 경합은 팀 내부 backend/DB/학습/추론 컨테이너 사이에서만 고려하면 됨)
- 메인보드(젯슨)에서 **YOLO26 엣지 추론**, 감지 시에만 RTSP로 중앙(GPU 1장)에 영상 전송해
  **Qwen3-VL-8B 분류**만 수행(엣지-중앙 하이브리드로 확정 — 상세는 위 "탐지 파이프라인" 참고)
- 탐지 모델 확정: YOLO26(엣지 상시감시+투척판단) + **Qwen3-VL-8B(중앙 정밀분류, YOLOv8-Medium 대체)**
- **컨테이너 3개**: `backend` / `mongo` / `training`(GPU). `training`은 라벨링·학습(YOLO 재학습+LLM 파인튜닝) 때만 기동 → `best.pt` 등 산출물 나오면 내리고 평소엔 `backend`+`mongo`만 상시 구동
- `training` 컨테이너는 JupyterLab을 띄워서 팀원이 브라우저로 같이 접속해 학습 코드 작성
  (`.env`의 `JUPYTER_PORT`/`JUPYTER_TOKEN`, 진짜 멀티유저 격리는 아니라 동시 실행 지양).
  GPU 서버 운영 실무(계정/rootless Docker/포트/SSH 터널 등)는 `gpuServerOps.md` 참고

## 배포 전략

- 개발: Windows+Docker, 로컬 웹캠 테스트
- 배포: 동일 이미지를 할당받은 GPU 1장으로 이전
- MVP: 백엔드+DB+**Qwen3-VL-8B 분류 추론+YOLO26 학습**을 GPU 서버 안에 전부 배포(YOLO26
  상시 추론 자체는 엣지/젯슨 담당이라 GPU 서버 몫이 아님 — 위 "탐지 파이프라인" 참고). 단
  **GPU 연산 자체는 학습/추론 컨테이너만 사용**, DB/백엔드는 GPU 미사용(CPU/RAM만) — VRAM은
  학습·추론 몫으로 남겨둠 (`docker run --gpus`는 `training` 컨테이너에만 적용)
- 서버 CPU/RAM이 팀별로 분리되는지(GPU만 분리되는지)는 서버 관리자 확인 필요(TBD)
- GPU 패스스루: nvidia-docker 필요
- **GPU 서버는 다인 공유 환경**(팀 5명뿐 아니라 다른 수강생들도 같은 호스트 공유) — 계정 격리,
  rootless Docker, GPU 카드 지정, 포트포워딩(SSH 터널) 등 실무 절차는 `gpuServerOps.md` 참고
- 영상 소스는 `.env`의 `CAMERA_SOURCE_<CameraId>`(예: `CAMERA_SOURCE_ELEV01`)만 환경별로 교체, 코드 불변

## 웹캠 시뮬레이션 (메인보드 입고 전) — 구현됨(신규 `CameraId` 반영 전)

> ⚠️ "카메라 1대=지점 1개=1`CameraId`" 구조 자체는 안 바뀜(위 "설치 환경" 참고) — 실제
> 코드는 아직 옛 가정("엘리베이터 2대", `ELEV-01`/`ELEV-02`) 기준 `CameraId`를 씀. 확정된
> `ELEV-TOP`/`ELEV-SIDE`로 `schemas/event.py`의 `CameraId` Enum과 `.env` 키 교체 필요
> (아직 코드 미반영).

- `streaming/cameraManager.py`: `CameraId`(`schemas/event.py`)마다 별도 `CameraManager` 인스턴스로 관리
  (`GET /api/stream/{cameraId}`, role 파라미터 없음 — 카메라 1대=지점 1개=1`CameraId`). 현재 코드의 `.env`
  키는 옛 가정 기준 `CAMERA_SOURCE_ELEV01`/`CAMERA_SOURCE_ELEV02`/`CAMERA_SOURCE_REST4F01`(하이픈 제거+대문자).
  `ELEV-01`만 기본값 `0`이라 로컬 웹캠 1대짜리 개발 환경에서 바로 동작. 나머지는 미설정 시
  해당 `cameraId` 요청만 503(다른 지점엔 영향 없음)
- 입고 후 CameraId별 독립 RTSP로 교체(소스 문자열만 RTSP URL로 교체, 로직 불변)
- `cv2.VideoCapture().read()` 동기 블로킹 → `asyncio.to_thread()`로 감쌈(적용 완료)
- **로컬에서 RTSP 경로 미리 테스트**: `debug/streaming/startRtspSim.py` — 이 PC의 웹캠 여러 대를
  각각 다른 지점(`CameraId`)에 할당해서, 지점별로 독립된 젯슨 나노 역할(FFmpeg+MediaMTX로
  RTSP 송신)을 동시에 흉내냄. `infra/checkEnv.py`처럼 필요한 것 자동 설치하지만, RTSP
  테스트하는 사람만 필요해서 `checkEnv.py`와는 별도 유지(`debug/db/`와 같은 패턴).
  WebApps/backend·docker-compose.yml과 무관 — 백엔드는 수정 없이 그대로 RTSP 수신

## 메인보드(Jetson Orin Nano Super) 엣지 코드 (미착수)

**엣지-중앙 하이브리드로 확정**(위 "탐지 파이프라인" 참고) — 캡처+RTSP 송신+GPIO뿐 아니라
**YOLO26 상시 추론까지 젯슨이 담당**. Orin Nano Super(8GB, 67 TOPS)라 YOLO26 엣지 추론 여력은
충분. GPU 서버(`training`)에서 학습한 `.pt` 가중치를 젯슨에 배포해야 하는데, 배포 방식(SCP 등)은
TBD.

1. 웹캠→RTSP 송신: GStreamer(JetPack 포함) 예정. 1단계 웹캠 뷰어(Py 3.11)는 노트북 테스트 완료
2. **YOLO26 엣지 추론**: 상시감시(위/옆 카메라 공통) + 위 카메라는 투척 위치 추적까지. 미착수
3. **GPU 서버 LLM 결과 수신→투척 결과 판정**(위 카메라만): YOLO26 추적 결과와 Qwen3-VL-8B
   분류 결과를 엣지에서 종합. 설계 전
4. 중앙 신호 수신→GPIO 트리거: 설계 전. `RPAs/alertController.py`는 현재 중앙에서 Mock 처리 중, 젯슨 쪽으로 이전 가능성. 전달 방식(MQTT/HTTP/WS) TBD(2, 3번의 젯슨↔GPU 서버 통신도 동일하게 미정)

> Jetson Nano 4GB(Python 3.6 제약)는 발주 무산으로 더 이상 해당 없음 — Orin Nano Super는
> JetPack 6.x/Python 3.10이라 `WebApps/backend`와 문법 호환성 문제 없음.

## RPA 정책

- 오분류 시 전구+경고음 즉시 자동 트리거(재전파 없음)
- `COLLECT` 모드: 알림 전부 Mute, 탐지 로직은 계속 동작(통계만 갱신)

## 이벤트 적재

- 매 프레임 Insert 금지, 이벤트 시점만 저장
- `eventCategory`로 구분: misclassification(투기, 정밀분류 결과 포함) / overflow(넘침, 분류 없이 영상만)
- 동일 카메라+클래스 5초 Cooldown(조정 TBD), overflow의 Cooldown 기준은 별도 TBD
- 이미지/영상은 MongoDB GridFS, **버킷을 카메라별로 2개 분리**(`topMedia`=위 카메라/투기,
  `sideMedia`=옆 카메라/넘침) — 물리 DB 분리 아니고 같은 DB 안 GridFS 버킷만 나눈 것(연결/인증
  추가 불필요). 순수 저장 구조 관리 편의 목적, 보관정책 차이는 없음(`EVENT` 컬렉션 자체는
  카메라별로 안 나누고 하나로 유지 — 상세는 `Docs/ERD.md` 참고)
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
- 4층 휴게실(`REST-4F-01`) 설치 진행 여부 — 고도화 단계 스트레치 목표, 시간 남으면 진행(불확실)
- **GPU 서버 CPU/디스크/네트워크 병목 실측**: GPU(VRAM)는 팀별 카드 분리로 경합 없음
  확인됨(아래 "해결된 TBD" 참고). CPU(192스레드)/디스크(2.8GB/s)는 여유 있어 보이지만
  다른 팀과 공유라 완전히 보장은 안 됨. **네트워크**는 엣지 YOLO26 확정으로 RTSP가 상시
  송출이 아니라 감지 시에만 전송되는 구조로 바뀌어서 우려가 줄었지만, 여전히 미측정 —
  메인보드 입고 후 실측 필요
- **YOLO26 `.pt` 가중치를 GPU 서버(`training`)에서 젯슨(엣지)으로 배포하는 방식**: SCP 등
  구체적 방법 미정

## 해결된 TBD

- Git 브랜치 전략 → `Docs/skills/github/README.md`
- IDE/AI 코딩 툴 → 개인별 사용
- 탐지 모델/프레임워크 → YOLO26(상시감시+투척판단, 기존 YOLOv8-Nano에서 변경) + Qwen3-VL-8B(정밀분류, LoRA/QLoRA 파인튜닝) 확정. YOLOv8-Medium은 Qwen3-VL-8B로 대체
- GPU 배분 → L40S 4장 중 팀당 1장 전용 할당(타 팀과 경합 없음)
- **손 감지 트리거 조건 폐지** → "손 O/X + 쓰레기 O" 조합 판정 대신 쓰레기 감지 자체가
  트리거로 확정. 투기(위 카메라 단독, YOLO26↔LLM 판정)/넘침(옆 카메라 단독, 위치 특정 없이
  즉시 알림) 두 카테고리로 완전히 분리(위 "탐지 파이프라인" 참고)
- **엣지-중앙 하이브리드 구조로 확정** → 과거 "전부 중앙 GPU 서버에서 처리" 결정을 뒤집음.
  YOLO26은 젯슨(엣지)에서 상시 추론(학습은 GPU `training` 컨테이너), RTSP는 감지 시에만
  비동기 전송, GPU 서버는 Qwen3-VL-8B 분류만 전담. 젯슨↔GPU 서버 간 결과 송수신 방식은
  여전히 TBD
- **넘침 판정에서 위 카메라 위치 특정 단계 폐지** → 옆 카메라 단독으로 넘침 감지 시 바로
  알림+DB 저장. 어느 통인지 분류할 필요 없다고 판단됨
- **설치 위치** → "엘리베이터 2대" 계획은 착오였던 것으로 정정, 실제로는 12층 엘리베이터 앞
  쓰레기통 1개뿐(`ELEV` 명칭 유래). 카메라 지점 2개(위+옆), `CameraId`는 `ELEV-TOP`/`ELEV-SIDE`로
  확정 — 설치 위치가 1곳이라 번호 불필요. "카메라 1대 = 지점 1개 = `CameraId` 1개 = 독립
  젯슨나노 1대" 규칙 자체는 유지(안 깨짐)
- **투기(misclassification) 판정 담당 카메라** → 위 카메라로 확정(넘침 판정은 옆=감지/위=위치
  특정으로 기존과 동일하게 역할 분담)
- **메인보드 하드웨어** → Jetson Nano 4GB 발주 무산, Jetson Orin Nano Super Developer Kit로
  확정(icbanq 무료 렌탈). Python 3.6 제약 문제 자체가 해소됨(JetPack 6.x/Python 3.10)
- **`EVENT`는 카메라별 물리 분리 안 함, GridFS 영상만 카메라별 버킷 2개로 분리** → `EVENT`
  컬렉션은 하나로 유지(`GET /api/events`가 카메라 구분 없이 한 번에 조회하는 구조라 나누면
  손해만 큼). 영상 저장은 물리 DB가 아니라 같은 DB 안 GridFS 버킷만 `topMedia`(위 카메라)/
  `sideMedia`(옆 카메라)로 나눔 — 저장 구조 관리 편의 목적, 보관정책 차이는 없음(상세는
  `Docs/ERD.md` 참고)
