# architecture.md — 색인

**이 파일은 색인입니다. 원본(source of truth)은 `Docs/ARCHITECTURE.md`입니다.**

매 세션 자동으로 읽히는 파일이라, 여기엔 **바꾸면 안 되는 확정 계약**과 **어디를 봐야
하는지**만 둡니다. 경위·검증 상태·미해결 사항 같은 상세는 전부 원본에 있습니다.

- **내용을 고칠 땐 `Docs/ARCHITECTURE.md`를 고칩니다.** 이 색인은 계약 자체(카메라 대수,
  클래스 종류, 포트, 판정 방향 등)가 바뀔 때만 함께 손댑니다
- **양쪽에 같은 서술을 중복해서 적지 않습니다.** 요약을 "줄여 쓴 사본"으로 만들면 반드시
  갈라집니다 — 실제로 그렇게 갈라진 문서들이 틀린 내용을 남긴 이력이 있습니다
  (`decisionLog.md` 참고). 아래 각 절은 사본이 아니라 **포인터**입니다
- 왜 그렇게 정했는지는 `decisionLog.md`, API는 `Docs/API_SPEC.md`, DB는 `Docs/ERD.md`

## 파이프라인

```
CCTV → 프레임분할 → 객체디텍팅 → 오분류 판정
  ├─ 탐지 시 → 현장알림(경고음, 전구는 제외)
  └─ 결과전송 → 백엔드(수신API) → 기록/통계
→ 관리자웹(스트리밍/기록/통계, 오분류 시 테두리 빨간색)
```

- 목적: 행정직원 분리수거 감독 부담 경감
- 알림: 스피커 경고음 트리거(전구/LED는 방향에서 제외 — 라즈베리파이 GPIO 제약)
- 안면인식(투기자 식별) 미포함, CTO 공통과제는 3팀 소관

## 설치 환경

| 항목 | 확정 값 |
|---|---|
| 위치 | 12층 엘리베이터 앞, 쓰레기통 1개. 카메라 지점 2개(위+옆) — 위치가 1곳뿐이라 지점 번호 없음. 4층 휴게실(`REST-4F-01`)은 사실상 제외 |
| `CameraId` | 운영 계약은 `ELEV-TOP` / `ELEV-SIDE` 2개. 단 `schemas/event.py`의 enum엔 `REST-4F-01`이 아직 남아 있어 API가 값 자체는 받는다(EP-19 조회 대상에선 제외) |
| 카메라 구성 | 카메라 1대 = 지점 1개 = `CameraId` 1개 = 독립 라즈베리파이 1대. `.env` 키는 하이픈 제거(`CAMERA_SOURCE_ELEVTOP`) |
| 메인보드 | 라즈베리파이(Jetson Orin 발주 취소). 추론 없음 — 캡처+RTSP 송신+스피커만(전구/LED는 GPIO 제약상 제외) |
| 카메라 스펙 | 실촬영 640×480, YOLO 입력은 640×640 레터박스 패딩(단순 리사이즈 아님) |
| 클래스 | `normal` / `paper` / `recyclables`(플라스틱+캔 통합) / `coffeeCup` 4종. `mixed`/`uncertain` 제외 확정 |

→ 상세(4층 휴게실 제외 경위, 배포 구조, `ELEV` 명칭 유래): `Docs/ARCHITECTURE.md`의 "설치 환경"

## 탐지 파이프라인

**확정 계약**:

- **판정 방향은 GPU → 로컬 백엔드 푸시.** 백엔드는 재판정하지 않고 받은 결과를 저장만 함
  (반대 방향이었던 옛 설계와 헷갈리지 말 것)
- TOP = YOLO26 + 룰 베이스 고정 ROI(`tracking2.py`) → `POST /api/events/aiDisposal`
- SIDE = MobileNet_V3_Small(`sideOverflow.py`) → `POST /api/binStates`
- 둘 다 GPU 서버에서 돌고, 로컬 백엔드가 서빙하는 MJPEG 스트림을 SSH 역터널로 구독
- **실시간 경로에 LLM 없음** (Qwen3-VL-8B는 학습 준비 단계 전용)

**역할 분담**:

| 주체 | 하는 일 |
|---|---|
| 라즈베리파이 | 캡처 + RTSP 송신 + 스피커(전구/LED는 GPIO 제약상 제외). **추론 없음**, RTSP는 로컬 백엔드로만(GPU와 직접 연결 안 함) |
| 로컬 백엔드 | RTSP 수신 + MJPEG 재서빙 + 판정 결과 수신 + 통 상태/쿨다운/녹화 타이밍/RPA 신호. **AI 추론 안 함** |
| GPU 서버 | `tracking2.py`(TOP)/`sideOverflow.py`(SIDE)가 MJPEG 구독 → 자체 판정 → 백엔드로 POST |

→ 상세(투입 확정 조건, ROI, 검증 상태, 미해결): `Docs/ARCHITECTURE.md`의 "탐지 파이프라인"

## LLM 활용

Qwen3-VL-8B는 **실시간 경로에 없음.** 학습 준비 단계의 자동 라벨링 검증에만 사용하며,
**박스별 닫힌 검증만 시키고 좌표(bbox)는 요구하지도 쓰지도 않음**(환각 확인, 2026-08-28 확정).
`confidence`는 그 자체로 신뢰 신호가 아니고, 최종 결정은 항상 사람 검수가 내림.

→ 상세(스키마 변천 경위, 파인튜닝 조건): `Docs/ARCHITECTURE.md`의 "LLM 활용"
→ 모델 선택·서빙 런타임(vLLM)·설정 근거: `Docs/LLM.md`

## 추론 인프라

NVIDIA L40S 4장 중 **팀당 1장 전용 할당**. GPU 서버에서 도는 것 4가지 —
`training` / `inference`(TOP) / `side-overflow`(SIDE) / `llm`(온디맨드).
`backend`/`mongo`/스케줄러는 GPU 서버가 아니라 **로컬**에서 구동.

GPU 하트비트(헬스체크) 구현 완료 — 30초 주기 `POST /api/gpuHeartbeats`, 조회 시점에 90초
임계값으로 ONLINE/OFFLINE 계산.

→ 상세(profile 구성, VRAM 경합, 하트비트 설계): `Docs/ARCHITECTURE.md`의 "추론 인프라"

## 배포 전략

**백엔드+DB는 로컬(`<LOCAL_BACKEND_IP>`, 실제 값은 Notion), GPU 서버는 추론+학습+LLM 검증.**
GPU → 로컬 백엔드 방향의 SSH 역터널(`-R`)이 상시 필요(끊기면 그동안 오분류·넘침 이벤트가
유실되지만 라이브뷰/녹화는 영향 없음).

→ 상세(profile별 기동 명령, 터널 포트, 미검증 항목): `Docs/ARCHITECTURE.md`의 "배포 전략"

## 웹캠 시뮬레이션 (메인보드 입고 전) — 구현됨

지점별 `CameraManager` + `GET /api/stream/{cameraId}` MJPEG. RTSP는 진짜 `ffmpeg`
서브프로세스로 격리(OpenCV 내장 ffmpeg 네이티브 크래시 이력).

→ 상세: `Docs/ARCHITECTURE.md`의 "웹캠 시뮬레이션", 로컬 RTSP 테스트는 `debug/streaming/README.md`

## 메인보드(라즈베리파이) 엣지 코드 (실기기 초기 셋업 완료, RTSP 송신 검증됨)

추론 없음 — 캡처+RTSP 송신+스피커만(전구/LED는 GPIO 제약상 방향에서 제외). RTSP는
**TOP/SIDE 둘 다 로컬 백엔드로만** 보냄. systemd 자동 기동까지 검증 완료, 스피커 상시
서비스화는 미착수.

→ 상세: `Docs/ARCHITECTURE.md`의 "메인보드(라즈베리파이) 엣지 코드",
실전 셋업 절차는 `piSetupOps.md`

## RPA 정책

- 오분류 시 경고음(스피커) 즉시 자동 트리거(재전파 없음). 전구(LED)는 방향에서 제외
- `COLLECT` 모드: 알림 전부 Mute, 탐지 로직은 계속 동작(통계만 갱신)
- **구현 상태: 스피커 프로토타입 존재, 상시 서비스화 미착수**(`services/rpaService.py` 없음) — 이 절은 목표 설계

→ 상세: `Docs/ARCHITECTURE.md`의 "RPA 정책"

## 자동 통계 보고서

별도 `report-scheduler` 프로세스가 일일(매일 09:00)·주간(월 09:10) 자동 발송.
FastAPI 내부 스케줄러 미사용.

→ 상세: `Docs/ARCHITECTURE.md`의 "자동 통계 보고서"

## 수거 업무 자동화 RPA

`RPA_COLLECTION_ENABLED=true`일 때 `NORMAL→FULL` 전환으로 수거 작업 생성, 별도
`collection-scheduler`가 알림→재알림→에스컬레이션 처리.

→ 상세: `Docs/ARCHITECTURE.md`의 "수거 업무 자동화 RPA"

## 이벤트 적재

- 매 프레임 Insert 금지, **판정 시점만** 저장
- `eventCategory`: `misclassification`(투기, 분류 결과 포함) / `overflow`(넘침, 분류 없음)
- misclassification은 동일 카메라+클래스 **5초 Cooldown**, overflow는 `NORMAL→FULL`
  **전환 시점에만** 생성(Cooldown 없음)
- GridFS 버킷은 카메라별 2개(`topMedia`/`sideMedia`) — 단, **운영에서 실제로 채워지는 건
  `topMedia`뿐**(overflow에는 영상이 안 붙음)

→ 상세(통 4개 매핑, 학습용 원본 재사용): `Docs/ARCHITECTURE.md`의 "이벤트 적재"

## 재학습용 미확정 방문 캡처 (백엔드·GPU 코드 구현 완료, 실기기 검증만 남음)

**저장 여부는 presence 감지만으로 결정되고 GPU 신호와 무관하다** — YOLO가 트랙조차 시작
못 한 방문도 영상은 이미 저장돼 있음. `trackId`는 이미 저장된 영상을 확정/미확정으로
**분류**하는 데만 씀. 재학습 후보 = `matchedEventIds`가 빈 모든 `visitClip`.

→ 상세(신호 흐름, 오분류 영상 연결, 미검증 항목): `Docs/ARCHITECTURE.md`의
"재학습용 미확정 방문 캡처", API는 `apiSpec.md`의 EP-15/EP-16/EP-17

## Event Flow

```
Detect → Create Event → Save Event → Check mode
  ├─ COLLECT: 통계만 갱신
  └─ MANAGE: WS Broadcast + RPA 트리거 → 통계 갱신
```

→ 상세: `Docs/ARCHITECTURE.md`의 "Event Flow"

## 포트

| 항목 | 값 |
|---|---|
| 백엔드 | 8047 |
| MongoDB 호스트 | 27020 (컨테이너 내부 27017) |

## DB 접속 (팀 공유 vs 로컬)

`.env`의 `MONGO_HOST`를 팀 배포(`<LOCAL_BACKEND_IP>`, 실제 값은 Notion) 또는 `localhost`로
전환. 팀 공유 Mongo는 팀원별 계정(`user01`~`user05`) 인증.

→ 상세: `Docs/ARCHITECTURE.md`의 "DB 접속"

## TBD

제목만 둡니다 — 각 항목의 배경·현재까지 확인된 것·다음 할 일은
**`Docs/ARCHITECTURE.md`의 "TBD"** 참고.

- 로컬 백엔드와 라즈베리파이의 네트워크 세그먼트 일치 여부
- 사람 존재 감지 임계값/디바운스 타이밍 실측 튜닝
- GPU 하트비트 주기(30초)/OFFLINE 임계값(90초) 실측 튜닝
- GPU→로컬 백엔드 연결 방식/재연결 전략(`autossh` 등)
- `tracking2.py`/`sideOverflow.py`를 GPU 서버 상시 서비스로 배포(재기동 최종 재검증)
- GPU 카드 공유 시 추론-학습 동시 실행 자원 경합 실측
- LLM 자동 라벨링 검증 세부 프롬프트, 환경별 통 모양 인식 데이터 생성 방식
- `waste_events/*.jpg`를 백엔드 GridFS(`imageFileId`)와 연동할지
- misclassification Cooldown 5초 조정 여부
- 스피커 상시 서비스화 방식, 라즈베리파이↔백엔드 신호 전달 방식
- 안면인식 레포 포함 여부
- 오탐 confidence threshold(GPU 스크립트 안의 상수, `.env` 아님)
- 통계 대시보드 세부 지표
- GPU 서버 CPU/디스크/네트워크 병목 실측
- 오분류 `EVENT`에 영상이 붙는지 실기기 확인
- GPU 판정 지연이 현장 알림 지연으로 이어지는 문제
- 카메라 영상 좌우 반전 여부 확인
- overflow(SIDE) 이벤트에 영상을 남길지 여부

## 해결된 TBD

`Docs/ARCHITECTURE.md`의 "해결된 TBD" 참고. 과거 결정 이력은 `decisionLog.md`.
