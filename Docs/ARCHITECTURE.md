# ARCHITECTURE.md

**이 문서가 아키텍처의 원본(source of truth)입니다.** 다른 문서와 내용이 겹치면 이 문서를
우선합니다.

`.agentfiles/architecture.md`는 이 문서의 **색인**입니다 — 에이전트가 매 세션 자동으로
읽는 파일이라 확정된 계약과 포인터만 두고, 경위·검증 상태·미해결 사항 같은 상세는 전부
여기에 있습니다. **내용을 고칠 때는 이 문서를 고치고**, 색인은 계약 자체(카메라 대수,
클래스 종류, 포트, 판정 방향 등)가 바뀔 때만 함께 손댑니다. 양쪽에 같은 서술을 중복해서
적지 않습니다 — 과거 그렇게 갈라진 문서들이 실제로 틀린 내용을 남겼습니다.

과거 결정 이력("왜 이렇게 정했는지")은 `.agentfiles/decisionLog.md` 참고.
API 상세는 `Docs/API_SPEC.md`, DB 스키마는 `Docs/ERD.md` 참고.

## 목차

- [설치 환경](#설치-환경)
- [탐지 파이프라인](#탐지-파이프라인)
- [LLM 활용](#llm-활용)
- [추론 인프라](#추론-인프라)
- [배포 전략](#배포-전략)
- [웹캠 시뮬레이션 (메인보드 입고 전) — 구현됨](#웹캠-시뮬레이션-메인보드-입고-전--구현됨)
- [메인보드(라즈베리파이) 엣지 코드 (실기기 초기 셋업 완료, RTSP 송신 검증됨)](#메인보드라즈베리파이-엣지-코드-실기기-초기-셋업-완료-rtsp-송신-검증됨)
- [자동 통계 보고서](#자동-통계-보고서)
- [수거 업무 자동화 RPA](#수거-업무-자동화-rpa)
- [이벤트 적재](#이벤트-적재)
- [재학습용 미확정 방문 캡처 (백엔드·GPU 코드 구현 완료, 실기기 검증만 남음)](#재학습용-미확정-방문-캡처-백엔드gpu-코드-구현-완료-실기기-검증만-남음)
- [DB 접속 (팀 공유 vs 로컬)](#db-접속-팀-공유-vs-로컬)
- [TBD](#tbd)
- [해결된 TBD](#해결된-tbd)

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
| 클래스 | normal, paper, recyclables(플라스틱+캔 통합), coffeeCup — 총 4종. `mixed`/`uncertain`은 제외 확정 |

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

- **넘침(overflow) 판정**(**옆 카메라** 단독, **GPU 서버가 자체적으로 판정 결과를 로컬
  백엔드에 푸시 — TOP과 완전히 동일한 구조**): GPU 서버의 `models/trashoverflow/
  sideOverflow.py`가 로컬 백엔드의 `GET /api/stream/ELEV-SIDE` MJPEG 스트림을 TOP과 같은
  SSH 역터널(`-R 8299`)로 구독해서 **MobileNet_V3_Small** 경량 분류 모델로 쓰레기통 넘침
  상태를 자체 판정하고, `POST /api/binStates`(EP-11)로 로컬 백엔드에 직접 결과를 푸시한다
  (로컬 백엔드가 SIDE를 호출하는 게 아니라 **GPU가 로컬 백엔드를 호출**하는 방향, TOP의
  `POST /api/events/aiDisposal`과 동일 패턴). ROI로 크롭한 이미지를 모델에 넣어
  `normal`/`overflow` 분류 후, 연속 30초 이상 `overflow`가 유지되면(세션 상태로 추적) 최종
  판정 — `NORMAL`→`FULL` 전환 시점마다 바로 `BIN_STATES` 갱신+`EVENT` 생성(기존과 동일).
  **한때 "로컬 백엔드가 CPU로 직접 추론, GPU 서버 미사용"으로 확정했었으나(SIDE는 기술적으로
  GPU가 꼭 필요하진 않음), TOP과 아키텍처를 일관되게 맞추기 위해 재전환**(`decisionLog.md`
  참고) — GPU/터널이 끊기면 TOP처럼 SIDE 판정도 그동안 멈춤(폴백 없음, TOP과 동일한 리스크
  프로필로 통일)
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
     plastic/can을 구분 못 해서 `DetectedClass.RECYCLABLES` 하나로 통합(물리적으로도 같은
     통에 버려서 실용상 문제없다고 판단). `normal`/`paper`/`recyclables`/`coffeeCup` 총 4종
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
  - **로컬 백엔드**: TOP/SIDE 둘 다 RTSP 상시 수신(관리자 웹 송출 겸용) + `GET
    /api/stream/{cameraId}`로 MJPEG 재서빙(GPU가 이걸 구독) + `POST /api/events/aiDisposal`
    (TOP)/`POST /api/binStates`(SIDE)로 GPU가 보내는 판정 결과를 수신. 통 상태
    (`BIN_STATES`)/쿨다운/녹화 시작·종료 타이밍/RPA 트리거 신호 송신은 TOP/SIDE 공통으로
    백엔드가 맡음 — 지속 상태는 전부 백엔드(로컬 MongoDB) 소유, AI 추론 자체는 안 함
  - **GPU 서버**: `models/trashdetect/tracking2.py`(TOP)와 `models/trashoverflow/
    sideOverflow.py`(SIDE) 둘 다 같은 패턴 — 로컬 백엔드가 서빙하는 MJPEG 스트림을 각자
    구독해서 자체 판단(TOP은 YOLO26+BoT-SORT로 투입 확정, SIDE는 MobileNet_V3_Small로
    넘침 확정), 결과를 로컬 백엔드로 푸시(로컬 백엔드가 GPU를 호출하는 게 아니라 **GPU가
    로컬 백엔드를 호출**) — 둘 다 더 이상 RTSP를 로컬 백엔드로부터 받지 않고 자체 소스를
    봄(과거 "SSH 역터널로 RTSP 직접 받기"/"로컬 백엔드가 프레임 샘플링해서 세션 API 호출"
    두 설계 모두 폐기, `decisionLog.md` 참고. SIDE는 한때 "GPU 서버 미사용, 로컬 백엔드
    CPU 추론"으로 갔다가 TOP과 아키텍처 통일 목적으로 재전환됨, `decisionLog.md` 참고)
  - GPU 서버 컨테이너/프로세스는 `training`(전처리+자동 라벨링+학습)/`models/trashdetect/
    tracking2.py`(YOLO26 TOP 모델, 위 설명대로 자체 실행+결과 푸시)/`llm`(Qwen3-VL-8B,
    자동 라벨링 검증용으로 이미 사용 중 — 실시간 탐지 경로엔 여전히 없음) 3개

## LLM 활용

Qwen3-VL-8B는 실시간 탐지 경로엔 없음(위 "탐지 파이프라인" 참고) — **학습/데이터 준비
단계에서만** 사용:

1. **자동 라벨링 검증(진행 중, 역할 축소됨)**: 이미지 폴더 → 전처리+자동 라벨링 도구로 1차
   라벨 생성 → 자동 라벨링이 100% 정확하지 않아서, LLM이 그 결과를 검증하는 형태로 진행 중.
   `autoTraining/stages/reviewLabels.py`(GPU 서버 호스트에서 실행)가 `llm` 컨테이너의 vLLM
   API를 호출하며, 이 스크립트가 review 단계 시작 시 `llm` 서비스를 자동으로 기동하고 끝나면
   자동으로 내린다(상시 기동 아님 — `gpuServerOps.md` 참고). **베이스 Qwen3-VL-8B-Instruct +
   프롬프트만 사용**(파인튜닝 없음).
   - **LLM에게는 "박스별 닫힌 검증"만 시킨다 — 좌표(bbox)는 요구하지도, 쓰지도 않는다**
     (2026-08-28 확정). YOLO가 그린 박스마다 그 안에 실제로 무엇이 있는지 하나씩 답하게 하고
     (`boxVerdicts`, 배열 길이를 탐지 개수에 고정), 놓친 쓰레기 여부(`hasMissedTrash`)와
     `confidence`만 추가로 받는다. `issues`/`decision`은 모델에게 묻지 않고 백엔드가 YOLO
     라벨과 대조해 도출한다
   - 이 형태에 이르기까지 두 번 뒤집혔다: ①좌표를 요구했더니 **없는 물체를 confidence
     0.95로 만들어내는 환각**(정밀 로컬라이제이션은 VLM의 구조적 약점, IoU 중앙값 0.00)
     ②그래서 프레임 단위 `predictedClass` 하나로 줄였더니 **2,796건 전부 동일한 무의미
     출력**(`none`/`issues=[]`). 원인은 박스가 여럿인 프레임을 클래스 하나로 표현할 수 없었던
     것과, `decision`/`none`이 판단 보류 탈출구가 된 것. 별도 실측에서 **모델이 이미지 자체는
     정확히 묘사**하는 것과, 스키마를 빼도 같은 답이 나와 guided decoding은 원인이 아님을
     확인한 뒤 지금의 닫힌 검증 구조로 바꿨다(`decisionLog.md` 참고)
   - **`confidence`는 그 자체로 신뢰 신호가 아니다** — 환각에도 0.95가 붙었다.
     `minimumReviewConfidence` 임계값은 보조 장치일 뿐이며, LLM 판정은 참고용이고 최종
     결정은 항상 사람 검수가 내린다. 박스 작성도 사람 검수 UI의 드래그 기능이 전담한다
   - 상세 경위와 기각한 대안은 `decisionLog.md` 참고
2. **환경별 통 모양 인식 학습 데이터 생성**: 설치 환경이 달라지면 물리 통 4개의 실제 생김새도
   달라지므로, LLM을 이용해 그런 환경별 통 인식 초기 학습 데이터를 만드는 데 활용 예정(아직
   미착수, 정확한 방식은 TBD)

**LLM 파인튜닝(미착수, 조건은 이미 충족)**: "베이스 모델 정확도가 부족하면 착수"라는 원래
조건 자체는 2026-08-28 실측으로 충족됐다(위 환각 + `wrongClass` 남발). 다만 **파인튜닝보다
먼저 위 1번의 역할 축소(좌표 제거)를 적용**했고, 그래도 부족하면 다음 순서로 검토한다:
①**Grounding DINO**(텍스트 프롬프트 기반 정밀 박스 전용 모델 — 지금 문제에 더 맞음,
`decisionLog.md`의 미검증 후보) → ②**Qwen3-VL-8B LoRA/QLoRA**(Unsloth 또는 LLaMA-Factory)로
GPU 1장(48GB) 내 진행. 파인튜닝 후 4/8bit 양자화해 추론 시 VRAM 최소화(`training`과 같은
카드에서 동시 서빙 가능하도록). Full fine-tuning이나 32B/235B(MoE) 등 상위 사이즈는 단일
카드로 비현실적이라 배제. 데이터 규모에 따라 수시간~하루 내 소요 예상. 학습 작업과 실시간
서비스가 같은 카드를 쓰므로 트래픽 적은 시간대 학습 권장. 라이선스는 배포 전 해당 사이즈
조항 확인 필요

## 추론 인프라

- NVIDIA L40S 총 4장, **팀당 1장씩 전용 할당**(다른 팀과 경합 없음)
- 모델/역할 분담은 위 "탐지 파이프라인" 참고(YOLO26 TOP 모델은 GPU 서버의
  `models/trashdetect/tracking2.py`, SIDE(MobileNet_V3_Small)도 이제 GPU 서버의
  `models/trashoverflow/sideOverflow.py`가 담당, LLM은 자동 라벨링 검증용 — 실시간 탐지엔
  미사용)
- **GPU 서버에서 도는 것 4가지**: `training`(전처리+자동 라벨링+학습, 필요할 때만 기동,
  Docker 컨테이너) / `inference`(TOP, `models/trashdetect/tracking2.py` — YOLO26 모델
  추론+판정) / `side-overflow`(SIDE, `models/trashoverflow/sideOverflow.py` —
  MobileNet_V3_Small 넘침 판정, TOP과 같은 패턴) / `llm`(Qwen3-VL-8B 서빙, vLLM — 자동
  라벨링 검증용으로 **이미 사용 중**, `training`과 함께 필요할 때만 기동, Docker 컨테이너).
  `inference`/`side-overflow` 둘 다 `docker-compose.yml`에 정의 완료 — `training`/`llm`처럼
  온디맨드는 아니지만, `backend`/`mongo`/`report-scheduler`(로컬 전용, `local` profile)와 같은 파일을
  공유해서 실수로 같이 뜨는 걸 막기 위해 이쪽은 `gpu` profile로 묶어서 `docker compose
  --profile gpu up -d`로 한 번에 기동 — **2026-08-25에 GPU 서버에서 실제 컨테이너 기동을
  처음 시도**, `host.docker.internal`이 SSH `-R` 역터널의 루프백 리스닝에 닿지 못해 crash
  loop가 발생해서 `network_mode: host`로 수정 완료(커밋 `06f3d0d`) — **단, 수정 후 재기동해서
  정상 연결되는지 최종 재검증은 아직 안 됨**(그 전까지 확실히 검증된 건 venv+
  `python tracking2.py`/`sideOverflow.py` 직접 실행 기준 end-to-end, 아래 참고).
  `backend`/`mongo`/`report-scheduler`는 GPU 서버가 아니라 **로컬에서 구동**(아래 "배포 전략" 참고)
- `tracking2.py`/`sideOverflow.py`는 `training`과 같은 카드(`GPU_DEVICE_ID`)를 공유해서
  상시 돌게 될 예정이라, 학습을 돌리는 시간대엔 세 워크로드가 VRAM/연산을 나눠 써야 함 —
  `llm`처럼 GPU 메모리 사용량을 제한해두는 게 안전(실측 후 조정 필요, 아래 TBD 참고. 단,
  `sideOverflow.py`는 모델이 가벼워서 VRAM 부담은 크지 않을 것으로 예상)
- (과거 TBD였던) `training`에서 나온 `.pt` 가중치를 젯슨(엣지)에 배포하는 문제는 해소됨 —
  `training`/`tracking2.py` 둘 다 GPU 서버 안에 있어 로컬 파일/볼륨 공유로 충분(원격 배포
  불필요, 실제로 학습 산출물을 `autoTraining/promotedModels/current.pt`로 옮겨서 검증함)
- `training` 컨테이너는 JupyterLab을 띄워서 팀원이 브라우저로 같이 접속해 학습 코드 작성
  (`.env`의 `JUPYTER_PORT`/`JUPYTER_TOKEN`, 진짜 멀티유저 격리는 아니라 동시 실행 지양).
  GPU 서버 운영 실무(계정/rootless Docker/포트/SSH 터널 등)는 `gpuServerOps.md` 참고
- `tracking2.py`/`sideOverflow.py`를 GPU 서버 재부팅에도 자동으로 살아나는 상시 서비스로
  만드는 작업 — **systemd가 아니라 Docker화로 방향 확정**(`inference`/`side-overflow`
  서비스, `gpu` profile + `restart: unless-stopped`). GPU 서버가 이미 rootless Docker에
  `loginctl enable-linger`를 걸어둬서(`gpuServerOps.md` 참고) Docker 데몬 자체가 재부팅
  시 자동 기동되므로, 새 systemd 유닛 없이 있는 인프라(`training`/`llm`과 같은 방식)를
  재사용. 코드/compose 정의는 완료됐고, 2026-08-25에 GPU 서버에서 실제 기동을 처음 시도해
  `host.docker.internal` crash loop를 발견 → `network_mode: host`로 수정(`06f3d0d`)까지
  반영됨 — **단, 수정 후 재기동해서 정상 동작하는지 최종 재검증은 아직 안 됨**, 그 전까지는
  사람이 SSH 세션에서 직접 실행 중
- **GPU 하트비트(헬스체크) — 구현 완료**: 판정 이벤트(`aiDisposal`/`binStates`)만으로는
  "아무 일도 없어서 조용한 것"과 "스크립트 크래시/SSH 터널 끊김으로 판정 자체가 안 되는
  것"을 백엔드가 구분할 수 없었던 문제를 해결. `tracking2.py`/`sideOverflow.py` 둘 다
  판정 이벤트와 무관하게 30초 주기로 `POST /api/gpuHeartbeats`(EP-19, 기존 판정용
  역터널 그대로 재사용)를 호출하고, 백엔드는 `cameraId`당 마지막 수신 시각만 upsert
  저장(`gpuHeartbeats` 컬렉션, `Docs/ERD.md`의 `GPU_HEARTBEAT` 참고) — ONLINE/OFFLINE
  자체는 저장하지 않고 `GET /api/gpuHeartbeats` 조회 시점마다 임계값(90초)과 비교해
  계산한다(임계값 조정 시 재계산만 하면 되도록). `/statistics`는 실제로 고객(행정직원)이
  보는 화면이라 평소엔 아무것도 표시하지 않다가, 20초 주기 폴링에서 OFFLINE인 카메라가
  있을 때만 상단에 경고 배너를 띄운다 — "GPU"나 스크립트명 같은 내부 인프라 용어는 절대
  노출하지 않고 "오분류 자동 감지"/"쓰레기통 넘침 자동 감지" 기능이 중단됐다는 식으로만
  안내(항상 보이는 상태 카드로 갔다가 고객 화면에 안 맞다고 판단해 배너로 변경). 90초
  임계값은 README의 confidence threshold와 같은 성격의 실측 후 조정 대상(아래 TBD 참고)

## 배포 전략

> **배포 위치(확정)** — 과거 "백엔드+DB+LLM 추론+학습을 GPU 서버 안에 전부 통합 배포"였던
> 결정을 뒤집음. **백엔드+DB는 로컬**, **GPU 서버는 YOLO26 학습+추론+자동 라벨링 검증(LLM)**
> 담당(실시간 탐지 경로에 LLM은 여전히 안 씀 — 위 "탐지 파이프라인"/"LLM 활용" 참고). 이유:
> GPU 서버는 다른 팀과 공유하는 자원이라 학습·추론 외 부담(백엔드/DB)은 줄이고, 백엔드/DB는
> 애초에 GPU를 안 쓰므로 로컬에 둬도 기능상 문제없음.
>
> **메인보드를 Jetson Orin Nano Super → 라즈베리파이로 전환하며 TOP 카메라 YOLO26 추론도
> 엣지→GPU 서버로 이관** — 라즈베리파이는 추론 성능이 부족해 엣지 단독 추론이 불가능해짐.
> 이 결정으로 GPU 서버가 실시간 경로에 들어옴(단, LLM은 여전히 안 들어옴 — YOLO26
> `tracking2.py`와, TOP과 아키텍처를 통일하기 위해 이후 재전환된 SIDE `sideOverflow.py`만
> 실시간 경로에 있음, `decisionLog.md` 참고). **GPU 연동은 로컬 백엔드가 프레임을 보내는
> 방식이 아니라
> GPU가 결과를 로컬 백엔드로 푸시하는 방식으로 최종 확정**(아래 참고, `decisionLog.md`) —
> 라즈베리파이는 여전히 GPU 서버와 직접 연결되지 않고 로컬 백엔드로만 RTSP를 보내며,
> **GPU 쪽(`tracking2.py`)이 TOP 영상을 보는 경로는 "로컬 백엔드 중계"로 확정** — GPU가
> 라즈베리파이 RTSP를 직접 받는 방식은 채택 안 함(라즈베리파이가 GPU 서버와 직접 연결되지
> 않는다는 원칙 유지). 로컬 백엔드가 이미 상시 서빙 중인 MJPEG 스트림(`GET
> /api/stream/ELEV-TOP`)을 GPU가 기존 SSH 역터널(`-R 8299:localhost:8047`)로 그대로
> 구독(`tracking2.py`의 `SOURCE`, `gpuServerOps.md` 참고) — 오분류 결과 푸시용 터널을
> 그대로 재사용하므로 별도 포트 불필요. **SIDE(`sideOverflow.py`)도 같은 원칙·같은 터널**로
> `GET /api/stream/ELEV-SIDE`를 구독(별도 포트 불필요) — TOP과 아키텍처를 통일하기 위해
> 이후 재전환된 결정, `decisionLog.md` 참고. 상세는 위 "탐지 파이프라인" 참고

- 개발: Windows+Docker, 로컬 웹캠 테스트(기존과 동일)
- **배포**: `backend`+`mongo`+`report-scheduler`+`collection-scheduler`는 로컬 `<LOCAL_BACKEND_IP>`(확정, 실제 값은 Notion 참고)에서
  `docker compose --profile local up -d backend mongo report-scheduler collection-scheduler`로 실행. `training`/`llm`은 GPU 서버로 이전해서
  `docker compose --profile training up`/`--profile llm up`(둘 다 자동 라벨링 검증
  파이프라인 돌 때만 같이 기동). `tracking2.py`/`sideOverflow.py` 둘 다 아직 Docker화 안
  됨(TBD) — 지금은 GPU 서버에서 스크립트로 직접 실행
- **GPU(`tracking2.py`/`sideOverflow.py`) → 로컬 백엔드 연결이 상시 필요(반대로 뒤집힌
  방향)** — 예전엔 "로컬 백엔드 → GPU API 호출"을 상시 유지해야 한다고 봤는데, 실제로는
  **GPU가 판정 완료 시마다 로컬 백엔드의 `POST /api/events/aiDisposal`(TOP)/`POST
  /api/binStates`(SIDE)를 호출**하는 구조로 확정돼 방향이 반대가 됨. GPU 서버 SSH
  세션(`gpuServerOps.md`)에 로컬 백엔드 포트로의 **역방향 터널(`-R`)이 필요**(기존
  MongoDB용 `-R 27020`과 같은 세션에 포트만 추가하면 됨, TOP/SIDE가 같은 `-R 8299` 포트를
  공유) — 이 연결이 끊기면 그 동안 오분류/넘침 이벤트가 둘 다 유실되지만, 라이브뷰/녹화
  (별도 경로)는 영향 없음. 재연결/재시도 전략은 TBD
- **백엔드(로컬) → LLM(GPU 서버) 실시간 연결은 여전히 불필요** — 이건 향후 LLM을 실시간
  탐지 경로에 쓰게 될 때 얘기고, 지금 진행 중인 자동 라벨링 검증은 `training`↔`llm`이 둘 다
  GPU 서버 안에 있어 SSH 터널 없이 컨테이너 간 통신으로 충분함. 실시간 경로에 쓰게 되면 그때
  SSH 터널(예: `ssh -p 2222 -L 8099:localhost:8099 soma@<GPU_SERVER_IP>`)을 상시 유지해야 함
- **`training`(GPU 서버) → MongoDB(로컬) 연결은 상시 필요** — 학습용 원본 이미지를
  로컬 GridFS에서 그대로 가져다 쓰기로 확정(위 "이벤트 적재" 참고)해서, 학습/라벨링 돌릴
  때마다 역방향 터널(위 라즈베리파이 RTSP 터널과 같은 SSH 세션에 포트만 추가)이 필요함
- **GPU 연산 자체는 `training`/`tracking2.py`/`sideOverflow.py`/`llm`만 사용**(넷 다 실제로
  씀 — `llm`은 자동 라벨링 검증용, `tracking2.py`/`sideOverflow.py`는 아직 Docker 컨테이너가
  아니라 독립 스크립트) — DB/백엔드가 로컬로 빠지면서 이 구분은 자연히 유지됨
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
   스피커 검증용 리스너는 `debug/hardware/alertListener.py`에 구현되어 기존
   `/ws/events`의 `MISCLASSIFICATION_DETECTED` 수신 시 `aplay`로 경고음을 재생한다.
   실제 설치 환경 상시 서비스화와 GPIO 전구 연동은 아직 미착수.

라즈베리파이(Raspberry Pi OS)는 표준 최신 Python(3.11+)을 쓸 수 있어 `WebApps/backend`와
문법 호환성 문제 없음 — 과거 Jetson Nano 4GB의 Python 3.6 제약 이슈는 애초에 해당 없음.

## 자동 통계 보고서

- `/statistics`의 **이메일 설정**은 보고서를 즉시 보내지 않고 자동 보고서 수신 주소 한 개를
  `RPAs/reportAutomation/state/recipientSettings.json`에 저장한다. 빈 입력으로 확인하면 명시적
  수신 해제 상태를 저장하며, 이 상태에서는 `.env` 수신 주소도 폴백하지 않는다.
- 일일 보고서는 매일 09:00에 전날 KST 데이터를, 주간 보고서는 매주 월요일 09:10에 이전
  월~일 KST 데이터를 조회해 HTML 이메일과 UTF-8 CSV로 자동 발송한다.
- 예약 실행은 FastAPI 내부가 아닌 별도 `report-scheduler` 프로세스가 담당한다. Docker에서는
  `backend`와 `report-scheduler`가 `report-state` 볼륨으로 수신 설정·발송 이력·실행 잠금·
  보고서 임시 스냅샷을 공유한다.
- 보고서 프로세스는 MongoDB에 직접 접근하지 않고 `GET /api/statistics`와 `GET /api/events`만
  사용한다. SMTP 발신 계정과 앱 비밀번호는 `.env`에만 보관한다.
- 운영 DB의 7일 보존 경계에서 주간 첫날 데이터가 삭제되는 문제를 막기 위해 매일 검증된 이벤트
  메타데이터를 날짜별 JSON으로 저장하고 최근 7개 날짜만 유지한다. 주간 보고서는 이 7개를
  합산하며, 누락 시 불완전한 메일을 보내지 않는다. 전주 비교는 최근 2개의 주간 합계만 보존한다.

## 수거 업무 자동화 RPA

- `RPA_COLLECTION_ENABLED=true`일 때 `BIN_STATES`의 `NORMAL→FULL` 전환으로 생성된 overflow
  `EVENT`를 기준으로 `collectionTasks` 작업을 생성한다. 같은 `binId`에는 활성 작업을 최대 한 건만
  허용하며 완료된 뒤 다시 `NORMAL→FULL`로 전환되면 새 작업을 생성한다.
- 별도 `collection-scheduler` 프로세스가 담당자 최초 알림, 설정 시간 후 재알림, 관리자
  에스컬레이션을 순서대로 처리한다. FastAPI 개발용 reload나 다중 worker와 분리해 중복 이메일을
  방지하고, 작업·실행 이력·heartbeat는 MongoDB에 저장해 재시작 후에도 이어서 처리한다.
- `/statistics`에서 활성 작업을 확인·완료 처리하고 자동화 상태, 처리 지표, 최근 발송 이력을 본다.
  SMTP 설정은 보고서 RPA와 공유하지만 담당자·관리자 수신 주소는 별도 환경변수를 사용한다.
- 신규 API와 MongoDB 컬렉션을 포함하므로 실제 배포 전 CTO 검토가 필요하다.

## 이벤트 적재

- 매 프레임 Insert 금지, 판정 시점만 저장
- `eventCategory`로 구분: misclassification(투기, 분류 결과 포함) / overflow(넘침, 분류 없음).
  **현재 운영 경로에서 overflow `EVENT`에는 영상이 붙지 않는다** — GPU가 `POST /api/binStates`
  (EP-11)로 판정만 푸시하고 프레임을 보내지 않으며, presence 기반 방문 녹화는 TOP 전용
  (`presenceGateService`는 `CameraId.ELEVTOP` 하나만 돌린다)이라 SIDE 구간을 녹화하는 주체가
  없다. 그래서 `/events` 상세 모달도 overflow면 "사이드 카메라는 미리보기를 지원하지
  않습니다"를 띄운다. overflow에 GIF가 붙는 경로는 데모 스텁(EP-08/EP-09)뿐이며, SIDE 영상을
  실제로 남길지는 아직 정하지 않았다(아래 TBD 참고)
- **물리 쓰레기통 4개**(일반/플라스틱·캔/커피컵/종이, `binId`)가 옆 카메라(`ELEV-SIDE`) 시야
  안에 고정 설치. "플라스틱·캔" 통(`binType=recyclables`)은 캔과 플라스틱을 물리적으로 같이
  받는데, 실제 YOLO26 모델(`tracking2.py`)도 둘을 구분하지 못해 `DetectedClass.RECYCLABLES`
  하나로만 낸다 — `binType`과 값 체계가 완전히 1:1 일치(과거엔 `plastic`/`can`을 별도
  `DetectedClass`로 두고 공용 통에 다대일 매핑하기로 했었으나 번복됨, `decisionLog.md`
  참고, 상세는 `Docs/ERD.md` 참고). 각 통의 현재 상태(`NORMAL`/`FULL`)를 별도
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

## 재학습용 미확정 방문 캡처 (백엔드·GPU 코드 구현 완료, 실기기 검증만 남음)

> **2026-08-26 설계 확정** — LLM review 파이프라인 실제 검증 중(`autoTraining/README.md`
> 참고) "지금 구조로는 YOLO가 못 잡은 실패 사례 영상이 재학습 데이터로 하나도 안 남는다"는
> 문제가 발견돼서 나온 설계. 이유는 `decisionLog.md` 참고. **백엔드 쪽(`visitClips`
> 스키마/저장소/서비스/API, `autoTraining` Collect 단계 확장)은 구현 완료** — 아래 "아직 안
> 된 것" 참고, 남은 건 GPU(`tracking2.py`)에 `trackStarted`/`trackEnded` 신호를 추가하는
> 것 하나뿐.

**문제**: 사람 존재 감지(`presenceGateService.py`) 기반 녹화는 GPU 판정과 완전히 독립
동작하고, GPU(`tracking2.py`)의 `POST /api/events/aiDisposal`은 투입이 **확정된 순간에만**
온다. 이 둘이 지금 코드상 서로 연결이 안 돼 있어서 (1) 확정된 이벤트조차 영상이 안 붙고
(`imageFileId` 없이 저장되는 기존 TBD와 동일 원인), (2) **YOLO가 아예 인지를 못했거나 확정을
못 낸 방문은 영상 자체가 저장될 경로가 없어서** 재학습에 제일 필요한 실패 사례가 통째로
유실된다.

**설계**:

```
[로컬 백엔드, GPU 신호와 무관하게 항상 동작]
사람 감지 시작 → 녹화 시작
사람 이탈 → 녹화 종료 → GIF 인코딩 → GridFS 업로드(무조건, 판정 여부 무관)
  → visitClips 컬렉션에 문서 생성: {cameraId, startedAt, endedAt, imageFileId,
    trackIds: [], matchedEventIds: [], unresolvedTrackIds: []}

[GPU: tracking2.py, 신호 2종 구현 완료]
트랙을 새로 발견하는 즉시 → POST /api/events/trackStarted {trackId, cameraId, timestamp}
  → 백엔드가 activeTracks에 임시 저장(사람 등장 시점과 거의 동시라 시간 오차 작음)
트랙 종료 시 둘 중 하나:
  ├─ 통에 확정 투입됨 → POST /api/events/aiDisposal (기존과 동일, trackId 포함)
  │     → events 저장 + trackId로 visitClip 찾아 imageFileId 정밀 연결
  └─ 확정 못하고 사라짐(놓침/이탈) → POST /api/events/trackEnded {trackId, result: unresolved}
        → 해당 visitClip.unresolvedTrackIds에 trackId 추가
```

**핵심**: **저장 여부는 presence 감지만으로 결정되고 GPU 신호와 무관**하다 — YOLO가 트랙조차
시작 안 해도(완전히 못 잡은 케이스) 영상은 이미 저장돼 있다. trackId는 "이미 저장된 영상"을
확정/미확정으로 **분류(라벨링)**하는 데만 쓰인다. `autoTraining`의 Collect 단계가 가져갈
재학습 후보 조건은 `matchedEventIds`가 비어있는 모든 `visitClip`(trackIds 유무 무관 — 시도
후 실패한 것과 아예 인지 못 한 것 둘 다 포함).

**구현 완료**: `visitClips` 스키마(`schemas/visitClip.py`)/저장소
(`repositories/visitClipRepository.py`)/서비스(`services/visitClipService.py`)/API
(`POST /api/events/trackStarted`, `POST /api/events/trackEnded`, `controllers/api.py`)
전부 반영됨. `autoTraining/stages/collectEventMedia.py`도 `matchedEventIds`가 비어있는
`visitClip`을 재학습 후보(`eventCategory: unresolvedVisit`)로 수집하는 경로가 추가됨(진행
중 — 아래 참고). 상세 필드는 `Docs/ERD.md`의 `VISIT_CLIP`, API 형식은
`.agentfiles/apiSpec.md`의 EP-15/EP-16 참고. **`tracking2.py`(GPU)의 `trackStarted`/
`trackEnded` 전송도 구현 완료** — 새 트랙을 등록하는 즉시 `trackStarted`를, 어느 통에도
못 들어가고 만료(`TRACK_EXPIRE_FRAMES`)되면 `trackEnded(unresolved)`를 보낸다. 통에 확정
투입된 트랙은 기존 `aiDisposal`의 `trackId`로만 연결하고 별도 `trackEnded`는 보내지 않으며,
같은 통에 ID가 바뀐 것으로 판단해 이벤트를 스킵하는 fragment-duplicate 트랙(극히 드묾)도
실제로는 다른 trackId로 이미 확정됐으므로 `trackEnded`를 보내지 않는다 — 이 두 경우까지
`unresolved`로 보내면 정상 처리된 방문이 재학습 후보로 잘못 잡힌다.

**오분류 `EVENT`에 영상 연결 — 구현 완료(2026-08-27)**: 위 `visitClips`가 저장되기
시작하면서, 오분류 `EVENT`의 `imageFileId`가 계속 null이던 문제도 같이 해결됨. 원인은
`createEventFromAiDisposal`이 "직전 5초" 프레임을 활성 녹화 버퍼
(`recordingService.snapshotRecentFrames`)에서 꺼내려 했는데, presence 기반 녹화는 사람
이탈 직후 세션을 삭제하는 반면 GPU 판정은 그보다 늦게 도착해 꺼낼 세션이 이미 없었던 것.
검토했던 두 해법 중 **(2) 이벤트 시각과 겹치는 `visitClip` 영상을 재사용하는 쪽으로 확정**
(더 저렴) — 방문 종료 시 GridFS에 저장된 **전체 방문 GIF를 다시 읽어** 이벤트 직전 약 5초
구간만 별도 GIF로 파생하고 그 ID를 `imageFileId`에 연결한다
(`services/eventMediaService.py`의 `attachPreviewFromVisitClip`, 실제 파생은
`mediaService.saveStoredClipSegmentAsGif`). 이벤트가 방문 영상 저장보다 **늦게 도착해도**
`trackId`로, 그것도 없으면 `cameraId`+이벤트 시각으로 기존 `visitClip`을 찾아 같은 처리를
한다(`visitClipService`). 전체 방문 GIF는 재학습/방문 기록용으로 그대로 유지되며 파생
미리보기와는 별도 파일이다. 대응 방문 영상이나 원본을 못 찾으면 이벤트만 저장하고
`imageFileId`는 null로 남는다(파생 실패 시 만들다 만 GridFS 파일은 보상 삭제).
`recordingService.snapshotRecentFrames`는 이 전환으로 **제거됨** — 더 이상 호출부 없음.
API 형식은 `.agentfiles/apiSpec.md`의 EP-12 참고.

**아직 안 된 것**: 위 GPU 쪽 코드는 이번에 작성됐지만 **실제 GPU 서버에서 트랙 신호가
백엔드에 정상 도달하는지 실기기 검증은 아직 안 됨**(그 전까지 검증된 건 스키마 파싱 확인
수준). 실기기 검증 전까지는 `unresolvedTrackIds` 기반 재학습 후보 분류도 실측으로 확인된
상태는 아님.

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
  `README.md`의 "오탐 confidence threshold"와 같은 성격의 수치 튜닝 TBD.
  **단, 배경 모델 수렴 시간은 이미 실기기로 원인을 잡아 고정했다**(튜닝 대상 아님):
  `cv2.createBackgroundSubtractorMOG2`의 기본 `history=500`은 30fps 기준(약 16초)이라
  우리 폴링 주기(`PRESENCE_POLL_INTERVAL_SECONDS`, 기본 0.2초)로는 100초가 걸려서,
  백엔드를 재시작할 때마다 그동안 사람이 없어도 PRESENT로 붙어 있거나 나가도 ABSENT로
  안 돌아오는 오탐이 재현됐다. 지금은 `presenceGateService.py`의 `backgroundHistorySeconds`
  (20초)로 폴링 주기에 맞춰 `history`를 계산해 항상 그 정도 안에 수렴하게 한다
- **GPU 하트비트 주기(30초)/OFFLINE 임계값(90초) 실측 튜닝** — 구현 방식 자체는 확정+구현
  완료(위 "추론 인프라"의 "GPU 하트비트(헬스체크)" 참고). 단, 두 수치 자체는 실측 없이
  임의로 정한 값(위 "사람 존재 감지 임계값"과 같은 성격) — 정상 판정 지연(GPU가 바빠서
  하트비트가 늦어지는 경우)과 실제 장애를 구분하기에 90초가 충분한지 실측 필요
- **GPU→로컬 백엔드 연결 방식/재연결 전략** — SSH 역터널(`-R`)이 필요한 건 확정됐지만
  (위 "배포 전략" 참고), 끊겼을 때 자동 재연결(`autossh` 등) 필요 여부는 미정 — 끊기면
  그 동안 오분류(TOP)/넘침(SIDE) 이벤트가 둘 다 유실되지만 라이브뷰/녹화는 영향 없음
- **`tracking2.py`/`sideOverflow.py`를 GPU 서버 상시 서비스로 배포** — 실제 TOP/SIDE 스트림
  구독(로컬 백엔드 중계)+end-to-end 결과 푸시까지 둘 다 확인됨(위 "탐지 파이프라인" 참고,
  2026-08-25). Docker화(`inference`/`side-overflow` 서비스, `gpu` profile +
  `restart: unless-stopped`)로 방향 확정하고 `docker-compose.yml`/`Dockerfile` 작성
  완료 — 같은 날(2026-08-25) GPU 서버에서 실제 기동을 처음 시도해 `host.docker.internal`
  crash loop를 발견하고 `network_mode: host`로 수정(`06f3d0d`)까지 반영됨. **단, 수정 후
  재기동해서 정상 연결되는지 최종 재검증은 아직 안 됨**(그 전까지 검증은 전부 venv+수동
  `python` 실행 기준). SSH 역터널 자체의 상시 유지(`autossh`, 로컬 배포 서버 쪽에 필요 —
  아래 "GPU→로컬 백엔드 연결 방식" 항목과 동일 이슈)는 별개로 여전히 TBD — Docker화해도
  터널이 안 살아있으면 둘 다 그냥 재연결 대기 상태로 남음
- **GPU 카드 공유 시 `tracking2.py`/`sideOverflow.py`-`training` 동시 실행 지연/자원 경합
  실측 필요** — 둘 다 상시 도는 구조라 `training`을 돌리는 시간대엔 자원을 나눠 써야 함,
  정확한 부하는 실측 필요(단, `sideOverflow.py`는 모델이 가벼워 부담이 작을 것으로 예상)
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
  다른 팀과 공유라 완전히 보장은 안 됨. **네트워크**는 GPU가 SSH 역터널로 로컬 백엔드의
  MJPEG 스트림(TOP 카메라 1개 분량)을 구독하는 구조라 예전 우려("TOP 라즈베리파이→GPU
  서버 RTSP 상시 스트리밍을 GPU가 직접 수신")보다는 부담이 가벼울 것으로 예상 — 그래도
  실측은 메인보드 입고 후 필요
- **오분류 `EVENT`에 영상이 붙는지 실기기 확인 필요** — 위 "재학습용 미확정 방문 캡처"의
  "오분류 영상 연결"로 **코드는 구현 완료**(2026-08-27, `visitClip` 영상에서 직전 5초를
  파생). 단, 2026-08-27에 null 10건이 확인된 뒤의 구현이라 **실제 운영에서 `imageFileId`가
  채워지는지 재확인은 아직 안 됨** — 특히 지연 도착 이벤트의 `cameraId`+시각 폴백 경로는
  단위 테스트로만 검증됨. (`tracking2.py`가 자체 저장하는 `waste_events/*.jpg`를 GridFS와
  연동하는 위 항목은 여전히 **원인이 다른 별개 미착수 과제**)
- **GPU 판정 지연이 현장 알림 지연으로 이어지는 문제** — RPA 알림은 `EVENT` 생성 시점에
  트리거되는데 그 생성이 GPU의 `aiDisposal` 도착을 기다리므로, GPU가 느리면 전구/경고음도
  같이 늦어짐. 위 "RPA 정책"의 "오분류 시 즉시 자동 트리거"와 충돌. 2026-08-27 측정에서
  방문 종료 대비 평균 약 16.8초(최대 48.7초)가 나왔으나 **표본 8건이고 측정 시간대에
  학습·vLLM을 같은 카드에서 돌리고 있어 오염된 값** — GPU 유휴 시간대에 재측정해서 실제
  문제인지 먼저 확정할 것. (위 "추론 인프라"의 "GPU 하트비트(헬스체크)" 항목은
  "살아있는가"를 보는 것이고, 이건 "얼마나 느린가"라 별개)
- **overflow(SIDE) 이벤트에 영상을 남길지 여부** — 지금은 안 남는다(위 "이벤트 적재" 참고).
  GPU가 EP-11로 판정만 푸시하고 presence 녹화는 TOP 전용이라 `sideMedia` 버킷이 운영에서
  비어 있고, `/events` 모달도 overflow엔 미리보기 미지원 안내를 띄운다. 남기려면 (1) SIDE에도
  녹화 게이팅을 붙이거나 (2) `sideOverflow.py`가 판정 프레임을 같이 보내는 방식 중 하나를
  정해야 하는데, "넘침은 통 상태라 영상 증거의 가치가 낮다"는 판단이면 지금 상태를 확정으로
  두고 ERD의 `sideMedia` 버킷을 정리하는 선택지도 있다 — 아직 논의 안 됨
- **카메라 영상이 좌우 반전으로 들어오는지 확인 필요** — 저장된 TOP 프레임을 보면 쓰레기통에
  붙은 한글 라벨이 거울상으로 보임(2026-08-27 확인). 학습 데이터와 운영이 같은 반전 상태면
  일관되므로 문제없지만, 의도치 않은 설정이면 운영 `tracking2.py`에도 함께 영향을 줌.
  라즈베리파이 캡처 설정이나 웹캠 미러 옵션을 확인할 것

## 해결된 TBD

과거 결정 이력(왜 이렇게 정했는지)은 `decisionLog.md`로 옮김 — **자동 로드 안 함**, 필요할
때만 열어볼 것. 현재 상태는 위 본문 섹션들에 이미 다 반영돼 있음.
