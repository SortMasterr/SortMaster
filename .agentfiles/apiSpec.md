# apiSpec.md

v0.1(MVP). Base URL `http://localhost:8047`(배포 시 로컬 배포 서버 `192.168.0.40:8047` — 백엔드는 GPU 서버가 아니라 로컬에서 구동, `architecture.md` 참고). JSON camelCase. 인증 없음(내부망).

새 엔드포인트 추가 시 이 문서 형식(EP-번호, 표) 그대로 유지.

## 공통 Enum

| Enum | 값 |
|---|---|
| CameraId | ELEV-TOP / ELEV-SIDE / REST-4F-01 — 설치 위치 1곳뿐이라 번호 없음(`.agentfiles/architecture.md` 참고). ELEV-TOP=쓰레기 종류 분류+쓰레기통 감지+투척 감지 3기능 모델, ELEV-SIDE=쓰레기통 넘침 여부만 판정 |
| EventCategory | misclassification(투기, 위 카메라 단독 — **MVP는 엣지 YOLO26 단독**으로 투척 통(`binId`)과 쓰레기 종류(`detectedClass`)를 감지+분류+비교까지 전부 처리, 불일치 시 엣지가 판정. LLM/GPU 호출 없음 — Qwen3-VL-8B는 고도화 단계 학습 보조용으로 후순위) / overflow(넘침, 옆 카메라 단독 — 물리 통 4개의 상태를 `BIN_STATES`로 지속 추적하다 `NORMAL`→`FULL` 전환 시점에만 생성) |
| BinType | general / plasticCan / coffeeCup / paper — 물리 쓰레기통 4개 고정. `plasticCan` 통은 `DetectedClass`의 `plastic`/`can` 둘 다 받음(매핑 필요, `Docs/ERD.md` 참고) |
| DetectedClass | general / paper / plastic / can / coffeeCup — 총 5종, misclassification 이벤트에서만 사용. `mixed`/`uncertain`은 제외됨 |
| ActionTaken | lightAndSound / soundOnly / lightOnly / notificationOnly / none |
| Mode | MANAGE(기본값) / COLLECT |
| CameraStatus | ONLINE / OFFLINE |
| WSEventType | MISCLASSIFICATION_DETECTED / BIN_OVERFLOW_DETECTED / MODE_CHANGED / CAMERA_DISCONNECTED / SYSTEM_ERROR |

상태 코드: 200 정상 / 422 스키마 불일치 / 500 서버 오류

## JSON API

| ID | Method/Path | 설명 | Params | 상태코드 | 부수효과 |
|---|---|---|---|---|---|
| EP-01 | GET /api/stream/{cameraId} | MJPEG 스트림 | Path: cameraId(CameraId) | 200/503 | 카메라 1대=지점 1개=1cameraId(role 파라미터 없음, 구조 불변). `CameraId`는 `ELEV-TOP`/`ELEV-SIDE`(설치 위치가 12층 엘리베이터 앞 1곳뿐이라 번호 불필요 — `.agentfiles/architecture.md` 참고). 카메라 미설정/연결 실패 시 503. 개발=`.env`의 `CAMERA_SOURCE_<ID>`(예: `CAMERA_SOURCE_ELEVTOP`) 웹캠, 배포=카메라별 독립 RTSP |
| EP-03 | GET /api/events | 이벤트 목록 | Query: from?, to?(ISO8601) | 200 | 없음. 페이지네이션 미구현(TBD) |
| EP-04 | GET /api/events/{id} | 이벤트 상세 | Path: id | 200 | 없음. not found 시 404 vs null TBD |
| EP-05 | GET /api/statistics | 클래스별 집계, 온디맨드(캐시없음) | Query: from?, to? | 200 | 없음. Chart.js는 WS로 낙관적 증가, 새로고침 시 재동기화 |
| EP-06 | POST /api/mode | 모드 전환 | Body: mode(Mode) | 200/422 | 성공 시 전체 WS 클라이언트에 MODE_CHANGED 브로드캐스트 |
| EP-08 | POST /api/detection/start | 녹화 시작(탐지 시작 신호) | Body: cameraId(CameraId) | 200/503 | `recordingService.start` 호출, recordingId 반환. 카메라 미설정/연결 실패 시 503 |
| EP-09 | POST /api/detection/stop | 녹화 종료+GIF 업로드+이벤트 저장(탐지 종료 결과 신호) | Body: recordingId, cameraId, eventCategory(생략 시 misclassification), detectionId, binId, binType, modelVersion + 카테고리별 필드 | 200/400/404/422 | misclassification/overflow 공통. EP-02와 동일한 저장·Cooldown·WS 부수효과 적용. recordingId 없으면 404, 캡처된 프레임 없으면 400 |

### EP-02. POST /api/events — 이벤트 생성

Request(EventCreate): cameraId(CameraId), eventCategory(EventCategory), detectionId(str, **구현 완료** — 탐지 파이프라인이 부여하는 중복 저장 방지 키, DB 유니크), trackingId(int|null, misclassification만 — YOLO26 추적 ID), detectedClass(DetectedClass, misclassification일 때만 필수), binId(str, misclassification·overflow 공통 — 물리 통 4개 중 하나), binType(BinType), isMisclassified(bool, misclassification일 때만), confidenceScore(float 0~1, misclassification일 때만), overflowDuration/overflowThreshold(float|null, overflow만), modelVersion(str), imageFileId(str|null, 선택)

Response(Event, 200): eventId(uuid), timestamp(ISO8601), cameraId, eventCategory, detectionId, trackingId(null 가능), detectedClass(null 가능), binId(null 가능), isMisclassified(null 가능), confidenceScore(null 가능), overflowDuration/overflowThreshold(null 가능), actionTaken(ActionTaken), imageFileId(str|null, GridFS 파일 ID, 녹화 파이프라인 연동 전엔 null), modelVersion, notes(str|null)
- misclassification: isMisclassified=false 또는 5초 Cooldown 중이면 null 반환
- overflow: `BIN_STATES.currentState`가 `NORMAL`→`FULL`로 전환되는 순간에만 생성(시간 기반 Cooldown 아님, `Docs/ERD.md` 참고), 분류 단계 없이 영상 녹화만 수행

부수효과: mode=MANAGE → RPA트리거+WS 브로드캐스트(카테고리별 eventType) / mode=COLLECT → 통계만 갱신. misclassification은 동일 cameraId+detectedClass 5초 내 재호출 무시(Cooldown), overflow는 `detectionId` 유니크 제약으로 중복만 방지(시간 Cooldown 없음)

### EP-08/EP-09. POST /api/detection/start, stop — 탐지 파이프라인 임시 스텁

`services/detectionService.py`: 실제 YOLO26 모델(젯슨 엣지) 완성 전까지, 시작/종료 신호를
API로 직접 받아 `recordingService`(녹화)→`mediaService`(GIF 인코딩+GridFS 업로드)→
`eventService.createEvent`(EP-02와 동일 로직, Cooldown 포함)를 그대로 호출하는 HTTP 연결부.
EP-09는 `eventCategory`에 따라 misclassification/overflow를 모두 처리하며, 기존 호출과의
호환성을 위해 `eventCategory`를 생략하면 misclassification으로 처리한다. misclassification은
`detectedClass`/`isMisclassified`/`confidenceScore`가 필수이고, overflow는 해당 필드를 보내지
않으며 `overflowDuration`/`overflowThreshold`를 선택적으로 보낸다. 두 카테고리 모두
`detectionId`/`binId`/`binType`/`modelVersion`이 필요하다.
엣지→백엔드 신호 전달 방식(MQTT/HTTP/WS, `architecture.md` 기준 TBD)이 확정되면 진입점만
그쪽으로 바꾸고 `detectionService` 내부 로직은 재사용 예정.

### EP-07. WS /ws/events — 실시간 스트림

연결 즉시 현재 Mode를 MODE_CHANGED로 1회 전송, 이후 이벤트 발생마다 수신.

| eventType | payload | 설명 |
|---|---|---|
| MISCLASSIFICATION_DETECTED | cameraId, timestamp, isMisclassified | 투기(오분류) 발생 시. detectedClass 필드 추가 여부 TBD |
| BIN_OVERFLOW_DETECTED | cameraId, timestamp | 쓰레기통 포화(넘침) 감지 시 |
| MODE_CHANGED | mode, timestamp | 연결 시 1회 + 전환 성공 시 전체 브로드캐스트 |
| CAMERA_DISCONNECTED | cameraId, timestamp | 30초 재시도 초과 |
| SYSTEM_ERROR | message, timestamp | 서버 내부 에러 |

eventType은 대문자 스네이크케이스(camelCase 규칙 유일 예외). 새 타입은 이 표에 먼저 추가 후 구현.

## 페이지 라우트

TemplateResponse만 반환, views.py/api.py 혼용 금지.

| ID | Path | 템플릿 | 설명 |
|---|---|---|---|
| PG-01 | GET / | index.html | 카메라 지점 2개(위+옆, `ELEV-TOP`/`ELEV-SIDE`) 스트리밍(분할 그리드)+모니터링 현황. mode를 컨텍스트로 전달(새로고침 시 상태유지) |
| PG-02 | GET /events | history.html | EP-03 결과 표 렌더링(이전기록) |
| PG-03 | GET /events/{id} | (미정) | EP-04 결과 렌더링 — 템플릿 아직 없음, 구현 전 |
| PG-04 | GET /statistics | dashboard.html | EP-05 결과 Chart.js 렌더링 |

sidebar.html은 라우트 아님 — 각 페이지에 공통 포함되는 사이드바 partial(모드토글, 네비게이션).

## TBD

- EP-04 not found 시 404 vs null
- EP-07 detectedClass 필드 추가 여부
- EP-03/EP-05 페이지네이션(limit/offset) 여부
- 인증/권한 (P3, 현재 없음)
- PG-03 템플릿(이벤트 상세 페이지) 미구현
- `BIN_STATES` 조회용 엔드포인트 필요 여부(현재 통별 실시간 상태를 노출하는 API 없음, `Docs/ERD.md` 참고)
- `BIN_STATES` 상태 변경 API 및 조회 API 형태(CTO 검토 필요)
