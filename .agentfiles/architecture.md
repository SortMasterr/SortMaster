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
> (감지+추적+분류+판정)은 GPU 서버의 `models/trashdetect/tracking2.py`가 전담**.
>
> **GPU 연동 방식은 "로컬 백엔드가 프레임을 샘플링해 GPU API를 호출·폴링"이 아니라
> "GPU가 TOP 카메라를 직접 보고 자체 판단한 뒤 결과를 로컬 백엔드로 푸시"로 최종
> 확정됨**(모델팀이 이미 작성한 `tracking2.py`를 실제로 확인한 뒤 뒤집힌 결정 — 과거
> "GPU가 SSH 역터널로 RTSP를 직접 당겨받는" 설계와 "로컬 백엔드가 사람 존재 감지로
> 게이팅해 프레임을 GPU에 세션 단위로 전송" 설계 둘 다 폐기, 이유는 `decisionLog.md`
> 참고). TOP 카메라 RTSP는 여전히 SIDE처럼 **로컬 백엔드로 들어와서 라이브뷰/녹화에
> 쓰이지만**, 이건 GPU 판정과는 **완전히 별개 경로**다 — 로컬 백엔드의 사람 존재 감지
> 게이팅(`presenceGateService.py`)은 녹화 시작/종료 타이밍만 결정하고, GPU에 프레임을
> 보내거나 GPU 응답을 기다리지 않는다. GPU 쪽(`tracking2.py`)은 별도로 TOP 카메라 영상을
> 직접 열어서(현재는 RTSP 소스로 전환 필요, 아래 참고) 상시 감지+추적하다가 투입이
> 확정되면 `POST /api/events/aiDisposal`로 로컬 백엔드에 결과를 전송한다(구현 완료,
> `services/eventService.py`의 `createEventFromAiDisposal`). LLM(Qwen3-VL-8B)은 여전히
> 이 실시간 경로엔 없음(고도화 전용, 아래 "LLM 활용" 참고).

- **넘침(overflow) 판정**(**옆 카메라** 단독, **로컬 백엔드, 룰 베이스 — GPU 미사용**): 옆
  카메라 라즈베리파이가 보낸 RTSP를 로컬 백엔드가 LAN으로 그대로 받아(관리자 웹 송출과
  같은 스트림) **딥러닝 모델이 아니라 룰 베이스**로 쓰레기통 넘침 상태를 판정. GPU 서버는
  전혀 관여하지 않음 — `NORMAL`→`FULL` 전환 시점마다 바로 `BIN_STATES` 갱신+`EVENT`
  생성(기존과 동일). SIDE 카메라는 GPU 서버와 아예 연결되지 않음(TOP도 이제 RTSP가 아니라
  API로만 GPU와 통신하므로, 어느 카메라든 GPU 서버로 RTSP를 직접 보내는 경우 자체가 없음)
- **투기(misclassification) 판정**(**위 카메라** 단독, **GPU 서버가 자체적으로 판정 결과를
  로컬 백엔드에 푸시하는 방식으로 확정** — 과거 "로컬 백엔드가 프레임을 샘플링해서 GPU
  세션 API를 호출·폴링" 설계는 실제 모델팀 코드(`models/trashdetect/tracking2.py`)를
  확인한 뒤 폐기됨, `decisionLog.md` 참고):
  1. **녹화(라이브뷰/DB 클립)는 오분류 판정과 완전히 독립적으로 동작** — 위 카메라
     라즈베리파이가 보낸 RTSP를 로컬 백엔드가 상시 수신(SIDE와 동일한 경로,
     `cameraManager.py`), **사람이 통 근처에 감지되면** 녹화 시작, 이탈(약 3초 유예 후)
     녹화 종료. 사람 존재 감지는 YOLO 없이 로컬에서 가벼운 방식으로 구현됨(**구현
     완료**) — `cv2.createBackgroundSubtractorMOG2` 배경 차분으로 프레임별 전경 픽셀
     비율을 구하고(`detection/presenceDetector.py`), 임계값+디바운스를 적용한 상태
     머신(`services/presenceGateService.py`, ABSENT/PRESENT 2상태)으로 게이팅. 이
     녹화 흐름은 GPU 판정과 신호를 주고받지 않음(**구현 완료**)
  2. **오분류 판정은 GPU 서버의 `models/trashdetect/tracking2.py`가 전담** — 이 스크립트가
     TOP 카메라 RTSP(또는 영상 소스)를 **직접 열어서** YOLO26(**쓰레기 4종만** — 통은
     아래 참고)으로 쓰레기를 감지, BoT-SORT로 트래킹하면서 **쓰레기 bbox 하단 중앙점이
     특정 통 영역 안에 일정 프레임 이상 머물다 사라지면 투입 확정**으로 판단(로컬 백엔드의
     존재 감지 게이팅과 무관하게 독립적으로 상시 동작). **통 위치는 YOLO가 아니라 화면 고정
     비율 ROI(룰 베이스)로 판정** — SIDE 카메라의 `roi.json`(단일 영역)과 같은 패턴을 통
     4개로 확장한 것(`tracking2.py`의 `RULE_BASED_BIN_ROIS`, 정규화 좌표 0~1). 처음엔
     "쓰레기 4종+통 4종을 한 YOLO 모델이 같이 인식"하는 8클래스 설계로 오인했으나(모델팀이
     넘긴 실제 코드에 모델 호출 흔적이 있었음), 실기기 테스트로 모델이 4클래스만 알고 있는
     걸 확인한 뒤 모델팀 확인 결과 **통은 애초에 룰 베이스가 맞는 설계**였음이 드러남
     (`decisionLog.md` 참고). `detectedClass`/`binId`/정상·오분류 판정(`result:
     correct/incorrect`)까지 **전부 GPU 쪽에서 직접 계산**(백엔드는 재계산 안 함) —
     커피컵→재활용통도 정상으로 인정하는 등 배출 규칙도 스크립트 안에 있음
  3. 투입이 확정되면 이 스크립트가 **`POST /api/events/aiDisposal`로 로컬 백엔드에 결과를
     직접 전송**(로컬 백엔드가 GPU를 호출하는 게 아니라 **GPU가 로컬 백엔드를 호출**하는
     방향 — 반대 방향이었던 옛 설계와 헷갈리지 말 것). 백엔드는 이 값을 내부 `EventCreate`로
     매핑해 기존 `eventService.createEventWithStatus`(쿨다운/멱등성 포함)를 그대로
     재사용해 `EVENT` 저장(**구현 완료**, `services/eventService.py`의
     `createEventFromAiDisposal`). `result: unknown`이나 매핑 안 되는 값은 방어적으로
     무시(로그만 남김)
  4. **쓰레기 종류는 4종(normal/paper/recyclables/coffeecup)으로 축소 확정** — 모델이
     plastic/can을 구분 못 해서 `DetectedClass.PLASTIC_CAN` 하나로 통합(물리적으로도 같은
     통에 버려서 실용상 문제없다고 판단, `decisionLog.md` 참고). 기존 `general`/`paper`/
     `coffeeCup` + 통합된 `plasticCan` 총 4종
  - **GPU 서버 → 로컬 백엔드 실제 푸시 검증 완료**(데모 영상 기준 + **실제 TOP MJPEG
    스트림 기준 둘 다**) — GPU 서버에서 `tracking2.py` 실행 → 로컬 백엔드가 상시 서빙 중인
    `GET /api/stream/ELEV-TOP`을 SSH 역터널(포트는 팀 공유 규칙상 99로 끝나야 해서 `8299`
    사용, `gpuServerOps.md` 참고)로 실시간 구독 → 투입 확정 → 같은 터널로 `POST
    /api/events/aiDisposal` 호출까지 end-to-end 확인됨(2026-08-25, 웹캠 앞에서 쓰레기를
    직접 흔들어 트리거하는 방식으로 연결성만 검증 — 통 없이 테스트해서 `result` 판정 자체는
    무의미, `RULE_BASED_BIN_ROIS`는 여전히 실제 설치 후 재보정 필요). 백엔드가 이
    엔드포인트를 반영 안 한 배포본이면 405(경로는 `GET /api/events/{id}`와 우연히 매칭되지만
    메서드가 안 맞음)가 뜸 — 코드 배포(재시작/재빌드) 필요
  - GPU가 라즈베리파이 RTSP를 직접 받는 방식 대신 **로컬 백엔드 중계**로 확정(아래 "배포
    전략"의 "별도 경로" TBD 해결) — 끊김 대비 재연결 로직도 추가함(`IS_LIVE_STREAM_SOURCE`)
  - **아직 안 된 것**: GPU 서버에서 상시 서비스로 도는 형태(예: systemd)로 배포 필요(지금은
    사람이 직접 실행). `CAMERA_ID="CAM-01"`→실제 값 확인(백엔드는 `CAM-01`을 `ELEV-TOP`으로
    매핑해서 받아둔 상태라 스크립트 수정 없이도 동작은 함). `RULE_BASED_BIN_ROIS` 좌표는
    실제 통 위치가 아니라 임시값 그대로라(위 검증도 통 없이 웹캠 앞에서 흔드는 방식으로만
    함), 실제 설치 후 카메라 구도에 맞게 재보정 필요. 이 스크립트가 자체 저장하는 이미지
    (`waste_events/*.jpg`)는 아직 백엔드의 GridFS와 연동 안 됨 — `imageFileId` 없이 저장됨
- **역할 분담**:
  - **라즈베리파이(엣지, TOP+SIDE 공통)**: 캡처+RTSP 송신+GPIO(전구 릴레이)+스피커(경고음) —
    **추론 없음, RTSP는 로컬 백엔드로만 전송**(TOP/SIDE 둘 다 GPU 서버와 직접 연결 안 함)
  - **로컬 백엔드**: TOP/SIDE 둘 다 RTSP 상시 수신(관리자 웹 송출 겸용) + `POST
    /api/events/aiDisposal`로 GPU가 보내는 오분류 판정 결과를 수신. 통 상태
    (`BIN_STATES`)/쿨다운/녹화 시작·종료 타이밍/RPA 트리거 신호 송신은 TOP/SIDE 공통으로
    백엔드가 맡고, SIDE는 룰 베이스 판정 자체(딥러닝 미사용)까지 전부 백엔드가 직접 수행 —
    지속 상태는 전부 백엔드(로컬 MongoDB) 소유
  - **GPU 서버(`models/trashdetect/tracking2.py`, TOP 전용)**: TOP 카메라 영상을 직접 열어
    YOLO26(감지+통 인식)+BoT-SORT(추적)로 투입 확정까지 자체 판단, 결과를 로컬 백엔드로
    푸시(로컬 백엔드가 GPU를 호출하는 게 아니라 **GPU가 로컬 백엔드를 호출**) — 더 이상
    RTSP를 로컬 백엔드로부터 받지 않고 자체 소스를 봄(과거 "SSH 역터널로 RTSP 직접 받기"/
    "로컬 백엔드가 프레임 샘플링해서 세션 API 호출" 두 설계 모두 폐기, `decisionLog.md` 참고)
  - GPU 서버 컨테이너/프로세스는 `training`(전처리+자동 라벨링+학습)/`models/trashdetect/
    tracking2.py`(YOLO26 TOP 모델, 위 설명대로 자체 실행+결과 푸시)/`llm`(Qwen3-VL-8B,
    자동 라벨링 검증용으로 이미 사용 중 — 실시간 탐지 경로엔 여전히 없음) 3개

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
- 모델/역할 분담은 위 "탐지 파이프라인" 참고(YOLO26 TOP 모델은 GPU 서버의
  `models/trashdetect/tracking2.py`, SIDE는 로컬 백엔드 룰 베이스, LLM은 자동 라벨링
  검증용 — 실시간 탐지엔 미사용)
- **GPU 서버에서 도는 것 3가지**: `training`(전처리+자동 라벨링+학습, 필요할 때만 기동,
  Docker 컨테이너) / `models/trashdetect/tracking2.py`(YOLO26 TOP 모델 추론+판정,
  **아직 Docker 컨테이너가 아니라 독립 실행 Python 스크립트** — 상시 서비스화는 TBD, 아래
  참고) / `llm`(Qwen3-VL-8B 서빙, vLLM — 자동 라벨링 검증용으로 **이미 사용 중**,
  `training`과 함께 필요할 때만 기동, Docker 컨테이너). `backend`/`mongo`는 GPU 서버가
  아니라 **로컬에서 구동**(아래 "배포 전략" 참고)
- `tracking2.py`는 `training`과 같은 카드(`GPU_DEVICE_ID`)를 공유해서 상시 돌게 될 예정이라,
  학습을 돌리는 시간대엔 두 워크로드가 VRAM/연산을 나눠 써야 함 — `llm`처럼 GPU 메모리
  사용량을 제한해두는 게 안전(실측 후 조정 필요, 아래 TBD 참고)
- (과거 TBD였던) `training`에서 나온 `.pt` 가중치를 젯슨(엣지)에 배포하는 문제는 해소됨 —
  `training`/`tracking2.py` 둘 다 GPU 서버 안에 있어 로컬 파일/볼륨 공유로 충분(원격 배포
  불필요, 실제로 학습 산출물을 `autoTraining/promotedModels/current.pt`로 옮겨서 검증함)
- `training` 컨테이너는 JupyterLab을 띄워서 팀원이 브라우저로 같이 접속해 학습 코드 작성
  (`.env`의 `JUPYTER_PORT`/`JUPYTER_TOKEN`, 진짜 멀티유저 격리는 아니라 동시 실행 지양).
  GPU 서버 운영 실무(계정/rootless Docker/포트/SSH 터널 등)는 `gpuServerOps.md` 참고
- `tracking2.py`를 GPU 서버에서 재부팅해도 자동으로 도는 상시 서비스(systemd 등, 라즈베리파이
  RTSP 송신에 적용한 것과 같은 패턴)로 만드는 작업은 **아직 미착수** — 지금은 사람이 직접
  실행해야 함

## 배포 전략

> **배포 위치(확정)** — 과거 "백엔드+DB+LLM 추론+학습을 GPU 서버 안에 전부 통합 배포"였던
> 결정을 뒤집음. **백엔드+DB는 로컬**, **GPU 서버는 YOLO26 학습+추론+자동 라벨링 검증(LLM)**
> 담당(실시간 탐지 경로에 LLM은 여전히 안 씀 — 위 "탐지 파이프라인"/"LLM 활용" 참고). 이유:
> GPU 서버는 다른 팀과 공유하는 자원이라 학습·추론 외 부담(백엔드/DB)은 줄이고, 백엔드/DB는
> 애초에 GPU를 안 쓰므로 로컬에 둬도 기능상 문제없음.
>
> **메인보드를 Jetson Orin Nano Super → 라즈베리파이로 전환하며 TOP 카메라 YOLO26 추론도
> 엣지→GPU 서버로 이관** — 라즈베리파이는 추론 성능이 부족해 엣지 단독 추론이 불가능해짐.
> 이 결정으로 GPU 서버가 실시간 경로에 들어옴(단, LLM이 아니라 YOLO26 `tracking2.py`만,
> SIDE는 애초에 GPU 미사용). **GPU 연동은 로컬 백엔드가 프레임을 보내는 방식이 아니라
> GPU가 결과를 로컬 백엔드로 푸시하는 방식으로 최종 확정**(아래 참고, `decisionLog.md`) —
> 라즈베리파이는 여전히 GPU 서버와 직접 연결되지 않고 로컬 백엔드로만 RTSP를 보내며,
> **GPU 쪽(`tracking2.py`)이 TOP 영상을 보는 경로는 "로컬 백엔드 중계"로 확정** — GPU가
> 라즈베리파이 RTSP를 직접 받는 방식은 채택 안 함(라즈베리파이가 GPU 서버와 직접 연결되지
> 않는다는 원칙 유지). 로컬 백엔드가 이미 상시 서빙 중인 MJPEG 스트림(`GET
> /api/stream/ELEV-TOP`)을 GPU가 기존 SSH 역터널(`-R 8299:localhost:8047`)로 그대로
> 구독(`tracking2.py`의 `SOURCE`, `gpuServerOps.md` 참고) — 오분류 결과 푸시용 터널을
> 그대로 재사용하므로 별도 포트 불필요. 상세는 위 "탐지 파이프라인" 참고

- 개발: Windows+Docker, 로컬 웹캠 테스트(기존과 동일)
- **배포**: `backend`+`mongo`는 로컬 `<LOCAL_BACKEND_IP>`(확정, 실제 값은 Notion 참고)에서
  `docker compose up backend mongo`로 실행. `training`/`llm`은 GPU 서버로 이전해서
  `docker compose --profile training up`/`--profile llm up`(둘 다 자동 라벨링 검증
  파이프라인 돌 때만 같이 기동). `tracking2.py`는 아직 Docker화 안 됨(TBD) — 지금은 GPU
  서버에서 스크립트로 직접 실행
- **GPU(`tracking2.py`) → 로컬 백엔드 연결이 상시 필요(반대로 뒤집힌 방향)** — 예전엔
  "로컬 백엔드 → GPU API 호출"을 상시 유지해야 한다고 봤는데, 실제로는 **GPU가 판정 완료
  시마다 로컬 백엔드의 `POST /api/events/aiDisposal`을 호출**하는 구조로 확정돼 방향이
  반대가 됨. GPU 서버 SSH 세션(`gpuServerOps.md`)에 로컬 백엔드 포트로의 **역방향 터널
  (`-R`)이 필요**(기존 MongoDB용 `-R 27020`과 같은 세션에 포트만 추가하면 됨) — 이 연결이
  끊기면 그 동안 오분류 이벤트가 유실되지만, 라이브뷰/녹화(별도 경로)는 영향 없음. 재연결/
  재시도 전략은 TBD
- **백엔드(로컬) → LLM(GPU 서버) 실시간 연결은 여전히 불필요** — 이건 향후 LLM을 실시간
  탐지 경로에 쓰게 될 때 얘기고, 지금 진행 중인 자동 라벨링 검증은 `training`↔`llm`이 둘 다
  GPU 서버 안에 있어 SSH 터널 없이 컨테이너 간 통신으로 충분함. 실시간 경로에 쓰게 되면 그때
  SSH 터널(예: `ssh -p 2222 -L 8099:localhost:8099 soma@<GPU_SERVER_IP>`)을 상시 유지해야 함
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
- RTSP 소스는 진짜 `ffmpeg` 바이너리를 서브프로세스로 띄워 MJPEG로 재인코딩한 stdout을
  읽는 방식(적용 완료) — OpenCV에 내장된 소형 ffmpeg가 손상된 H264 프레임에서 파이썬이
  못 잡는 네이티브 크래시(백엔드 전체 다운)를 낸 적이 있어서, 크래시 나도 그 서브프로세스만
  죽고 자동 재연결되도록 격리함. 로컬 웹캠(정수 인덱스) 경로는 크래시 이력이 없어 기존
  `cv2.VideoCapture()` 동기 블로킹 → `asyncio.to_thread()` 방식 그대로 유지
- **로컬에서 RTSP 경로 미리 테스트**: `debug/streaming/startRtspSim.py` — 이 PC의 웹캠 여러 대를
  각각 다른 지점(`CameraId`)에 할당해서, 지점별로 독립된 라즈베리파이 역할(FFmpeg+MediaMTX로
  RTSP 송신)을 동시에 흉내냄. `infra/checkEnv.py`처럼 필요한 것 자동 설치하지만, RTSP
  테스트하는 사람만 필요해서 `checkEnv.py`와는 별도 유지(`debug/db/`와 같은 패턴).
  WebApps/backend·docker-compose.yml과 무관 — 백엔드는 수정 없이 그대로 RTSP 수신

## 메인보드(라즈베리파이) 엣지 코드 (실기기 초기 셋업 완료, RTSP 송신 검증됨)

> **Jetson Orin Nano Super 발주 건은 완전히 취소, 라즈베리파이로 확정 대체.** 이유: 애초
> Orin을 쓰려던 목적(YOLO26 엣지 상시 추론)이 라즈베리파이로는 성능상 불가능해서, YOLO26을
> GPU 서버(`inference`)로 이관(위 "탐지 파이프라인" 참고)하기로 하면서 메인보드에 고성능
> NPU/GPU가 더 이상 필요 없어짐 — 캡처+RTSP 송신+GPIO/스피커만 하면 되는 역할이라 라즈베리
> 파이로 충분.

**추론 없음, 캡처+송신+RPA 출력만 담당**(위 "탐지 파이프라인"의 "역할 분담" 참고):

1. **웹캠(테스트용, USB)→RTSP 송신: 실기기(`elev-top`)에서 ffmpeg+MediaMTX 조합으로 검증
   완료** — Windows 로컬 시뮬레이터(`debug/streaming/startRtspSim.py`)와 동일한 패턴(캡처
   백엔드만 dshow→v4l2로 차이), 노트북에서 VLC로 수신 확인함. **systemd 서비스로 등록
   완료**(재부팅 시 자동 기동, 실제 재부팅 테스트로 검증됨) — 실전 절차/트러블슈팅
   (cloud-init 설정, Wi-Fi 대역 이슈 등)은 `piSetupOps.md` 참고. 카메라 모듈(CSI) 연동은
   미착수(지금은 USB 웹캠으로만 검증)
2. **TOP/SIDE 둘 다 로컬 백엔드로만** RTSP 전송(LAN, 관리자 웹 송출과 겸용) — GPU 서버와
   직접 연결되는 라즈베리파이는 없음(과거 "TOP만 SSH 역터널로 GPU에도 노출" 방식 폐기,
   `decisionLog.md` 참고). TOP 카메라의 GPU 연동은 로컬 백엔드가 상시 서빙 중인 MJPEG
   스트림(`GET /api/stream/ELEV-TOP`)을 GPU(`tracking2.py`)가 SSH 역터널로 구독하는 방식(위
   "탐지 파이프라인" 참고) — 과거 "로컬 백엔드가 프레임 샘플링해서 GPU API 호출" 설계는
   폐기됨(`decisionLog.md` 참고). **단, 로컬 백엔드와 라즈베리파이가 서로 다른 네트워크 세그먼트에 있으면 mDNS
   (`.local`)도 안 통하고 이 RTSP 수신 자체가 안 됨 — 실제 설치 위치의 네트워크가 로컬
   백엔드와 같은 세그먼트인지 확인 필요(아래 TBD 참고)**
3. 로컬 백엔드로부터 RPA 트리거 신호 수신 → **GPIO(릴레이 경유 전구 점등)** + **스피커
   (USB 또는 3.5mm 오디오잭, Python에서 `aplay` 서브프로세스 등으로 경고음 재생)** 출력.
   `RPAs/alertController.py`는 현재 중앙에서 Mock 처리 중, 라즈베리파이 쪽으로 이전 예정.
   신호 전달 방식(MQTT/HTTP/WS) TBD — **아직 미착수**

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

- **로컬 백엔드와 라즈베리파이의 네트워크 세그먼트 일치 여부** — RTSP 수신(로컬 백엔드↔
  라즈베리파이)은 mDNS(`.local`) 이름 해석에 의존 중인데, 이건 **같은 네트워크 세그먼트
  안에서만** 동작함(멀티캐스트가 세그먼트를 못 넘어감). 실제 설치 위치(12층 엘리베이터
  앞)의 라즈베리파이가 로컬 백엔드(`<LOCAL_BACKEND_IP>`)와 같은 세그먼트에 붙는지 미확인 —
  다르면 `.local` 접속 자체가 안 되고 라우팅(양쪽 네트워크 관리자 권한 필요) 또는 터널
  (GPU 서버처럼 SSH 터널 등) 방식을 추가로 정해야 함. **추가로, 배포 전략상 로컬 백엔드는
  `docker compose`로 뜨는데 mDNS는 Docker 컨테이너 안에서 기본적으로 안 통함**(실전 확인:
  `.env`를 호스트이름으로 바꾸고 Docker에서 빌드하니 스트림이 안 뜸, IP로는 정상) — 세그먼트가
  같아도 이 문제는 별개로 발생하므로, **정식 배포 땐 호스트이름 대신 라즈베리파이 자체에
  고정 IP를 설정하는 쪽으로 사실상 확정**(공유기 관리자 권한 불필요, 방법은 `piSetupOps.md`
  참고, TOP/SIDE 둘 다 재부팅 검증 완료). 실전 셋업 중 발견, 상세는 `piSetupOps.md` 참고
- **사람 존재 감지 임계값/디바운스 타이밍 실측 튜닝** — 구현 방식 자체는 확정+구현
  완료(배경 차분 기반 전경 비율 + 진입 확인/이탈 유예 디바운스, 위 "탐지 파이프라인"
  참고). 단, 전경 비율 임계값(`PRESENCE_FOREGROUND_RATIO_THRESHOLD`)/진입 확인 시간
  (`PRESENCE_ENTRY_CONFIRM_SECONDS`)/이탈 유예 시간(`PRESENCE_EXIT_GRACE_SECONDS`,
  스펙상 3초) 수치 자체는 실제 TOP 카메라 설치 위치/거리 기준 실측 후 조정 필요 —
  `README.md`의 "오탐 confidence threshold"와 같은 성격의 수치 튜닝 TBD
- **GPU→로컬 백엔드 연결 방식/재연결 전략** — SSH 역터널(`-R`)이 필요한 건 확정됐지만
  (위 "배포 전략" 참고), 끊겼을 때 자동 재연결(`autossh` 등) 필요 여부는 미정 — 끊기면
  그 동안 오분류 이벤트가 유실되지만 라이브뷰/녹화는 영향 없음
- **`tracking2.py`를 GPU 서버 상시 서비스로 배포** — 지금은 로컬 데모 스크립트 상태(mp4/
  웹캠 대상), 실제 TOP RTSP를 보도록 `SOURCE` 변경 + systemd 등으로 상시 기동 + Docker화
  여부(GPU 카드 공유 방식은 `training`/`llm` 패턴 재사용 예정) 전부 TBD
- **GPU 카드 공유 시 `tracking2.py`-`training` 동시 실행 지연/자원 경합 실측 필요** —
  `tracking2.py`가 상시 도는 구조라 `training`을 돌리는 시간대엔 자원을 나눠 써야 함,
  정확한 부하는 실측 필요
- LLM 자동 라벨링 검증의 세부 프롬프트/자동 라벨링 도구 구현(진행 중), "환경별 통 모양 인식
  데이터 생성"의 구체적 방식(아직 미착수)
- `tracking2.py`가 자체 저장하는 이미지(`waste_events/*.jpg`)를 백엔드 GridFS(`imageFileId`)와
  연동할지, 한다면 어떻게 전송할지(GPU→로컬 파일 전송 필요) — 아직 미착수, 지금은
  `imageFileId` 없이 이벤트만 저장됨
- misclassification Cooldown 5초 조정 여부(overflow는 상태 전환 기반으로 확정돼 별도
  Cooldown 없음 — 해결된 TBD 참고)
- 경고 전구 HW/GPIO 연동 상세, 라즈베리파이↔중앙 백엔드(RPA 트리거) 신호 전달 방식
  (MQTT/HTTP/WS 중 미정, GPU 서버↔백엔드는 HTTP POST로 확정됨 — 위 "탐지 파이프라인" 참고)
- 안면인식 레포 포함 여부
- **GPU 서버 CPU/디스크/네트워크 병목 실측**: GPU(VRAM)는 팀별 카드 분리로 경합 없음
  확인됨(아래 "해결된 TBD" 참고). CPU(192스레드)/디스크(2.8GB/s)는 여유 있어 보이지만
  다른 팀과 공유라 완전히 보장은 안 됨. **네트워크**는 RTSP 상시 전송이 아니라 로컬
  백엔드가 5~10fps로 샘플링한 프레임(이미지)만 API로 보내는 구조라 예전 우려("TOP
  라즈베리파이→GPU 서버 RTSP 상시 스트리밍")보다는 부담이 가벼울 것으로 예상 — 그래도
  실측은 메인보드 입고 후 필요

## 해결된 TBD

과거 결정 이력(왜 이렇게 정했는지)은 `decisionLog.md`로 옮김 — **자동 로드 안 함**, 필요할
때만 열어볼 것. 현재 상태는 위 본문 섹션들에 이미 다 반영돼 있음.
