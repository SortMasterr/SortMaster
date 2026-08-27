# apiSpec.md

v0.2(MVP), 구현 기준일 2026-08-25. `DetectedClass`/`BinType`의 `general`→`normal`, `plasticCan`→`recyclables` 변경 반영(병합 전 CTO 검토 필요). 새 저장/API 응답은 새 값만 사용하고 기존 MongoDB 문서는 읽을 때 새 값으로 변환한다. Base URL `http://localhost:8047`(배포 시 로컬 배포 서버 `<LOCAL_BACKEND_IP>:8047`, 실제 IP는 Notion 참고 — 백엔드는 GPU 서버가 아니라 로컬에서 구동, `architecture.md` 참고). JSON camelCase. 인증 없음(내부망).

새 엔드포인트 추가 시 이 문서 형식(EP-번호, 표) 그대로 유지.

## 공통 Enum

| Enum | 값 |
|---|---|
| CameraId | ELEV-TOP / ELEV-SIDE / REST-4F-01 — 설치 위치 1곳뿐이라 번호 없음(`.agentfiles/architecture.md` 참고). ELEV-TOP=YOLO26(쓰레기 4종 분류+추적)+룰 베이스(통 위치, 고정 ROI) 조합, ELEV-SIDE=MobileNet_V3_Small(쓰레기통 넘침 여부, 로컬 백엔드 CPU 추론) |
| EventCategory | misclassification(투기, 위 카메라 단독 — **GPU 서버(`models/trashdetect/tracking2.py`)가 감지+추적+분류+정상/오분류 판정까지 자체적으로 끝내고 `POST /api/events/aiDisposal`로 결과를 로컬 백엔드에 직접 푸시**, 백엔드는 재판정 없이 저장. 실시간 경로엔 LLM 미사용 — Qwen3-VL-8B는 학습 준비 단계 자동 라벨링 검증에만 사용 중) / overflow(넘침, 옆 카메라 단독 — **MobileNet_V3_Small을 로컬 백엔드가 CPU로 직접 추론(GPU 서버 미사용)**, 물리 통 4개의 상태를 `BIN_STATES`로 지속 추적하다 `NORMAL`→`FULL` 전환 시점에만 생성) |
| BinType | normal / recyclables / coffeeCup / paper — 물리 쓰레기통 4개 고정. `DetectedClass`와 값 체계 1:1 일치 |
| DetectedClass | normal / paper / recyclables / coffeeCup — 총 4종, misclassification 이벤트에서만 사용. `mixed`/`uncertain`은 제외됨. 실제 YOLO26 모델이 plastic/can을 구분 못 해 `recyclables` 하나로 통합 |
| ActionTaken | lightAndSound / soundOnly / lightOnly / notificationOnly / none |
| Mode | MANAGE(기본값) / COLLECT |
| CameraStatus | ONLINE / OFFLINE — EP-19 응답에 사용(ELEV-TOP/ELEV-SIDE의 GPU 추론 스크립트 하트비트 기반) |
| WSEventType | MISCLASSIFICATION_DETECTED / BIN_OVERFLOW_DETECTED / MODE_CHANGED / CAMERA_DISCONNECTED / SYSTEM_ERROR |

상태 코드: 200 정상 / 400 요청 오류 / 404 이벤트·녹화 세션 없음 /
409 녹화 충돌 / 422 스키마 불일치 / 500 서버·이메일 설정 파일 오류 /
503 카메라 미설정·연결 실패

## JSON API

| ID | Method/Path | 설명 | Params | 상태코드 | 부수효과 |
|---|---|---|---|---|---|
| EP-01 | GET /api/stream/{cameraId} | MJPEG 스트림 | Path: cameraId(CameraId) | 200/422/503 | 카메라 1대=지점 1개=1cameraId(role 파라미터 없음, 구조 불변). `CameraId`는 `ELEV-TOP`/`ELEV-SIDE`(설치 위치가 12층 엘리베이터 앞 1곳뿐이라 번호 불필요 — `.agentfiles/architecture.md` 참고). 카메라 미설정/연결 실패 시 503. 개발=`.env`의 `CAMERA_SOURCE_<ID>`(예: `CAMERA_SOURCE_ELEVTOP`) 웹캠, 배포=카메라별 독립 RTSP |
| EP-03 | GET /api/events | 이벤트 목록 | Query: from?, to?(ISO8601) | 200/422 | 없음. 페이지네이션 미구현(TBD) |
| EP-04 | GET /api/events/{id} | 이벤트 상세 | Path: id | 200/404 | 없음. not found 시 `{"detail":"이벤트를 찾을 수 없습니다."}` |
| EP-04-M | GET /api/events/{id}/media | 이벤트 GIF 조회 | Path: id | 200/404 | `imageFileId`가 참조하는 카메라별 GridFS GIF를 `image/gif`로 반환. 이벤트/ID/파일이 없으면 404, `Cache-Control: private, max-age=300` |
| EP-05 | GET /api/statistics | 클래스별·카테고리별 집계, 온디맨드(캐시없음) | Query: from?, to? | 200/422 | Response: `labels`, `counts`, `totalEventCount`, `misclassificationCount`, `overflowCount` |
| EP-06 | POST /api/mode | 모드 전환 | Body: mode(Mode) | 200/422 | 성공 시 전체 WS 클라이언트에 MODE_CHANGED 브로드캐스트 |
| EP-08 | POST /api/detection/start | 녹화 시작(탐지 시작 신호) | Body: cameraId(CameraId) | 200/422/503 | `recordingService.start` 호출, recordingId 반환. 카메라 미설정/연결 실패 시 503 |
| EP-09 | POST /api/detection/stop | 녹화 종료+GIF 업로드+이벤트 저장(탐지 종료 결과 신호) | Body: recordingId, cameraId, eventCategory(생략 시 misclassification), detectionId, binId, binType, modelVersion + 카테고리별 필드 | 200/400/404/422 | misclassification/overflow 공통. EP-02와 동일한 저장·Cooldown·WS 부수효과 적용. recordingId 없으면 404, 캡처된 프레임 없으면 400 |
| EP-10 | GET /api/binStates | BIN_STATES 전체 조회(binId당 최신 1행, 대시보드용) | 없음 | 200 | 없음 |
| EP-11 | POST /api/binStates | BIN_STATES 갱신(GPU 서버의 SIDE MobileNet_V3_Small 로직 `sideOverflow.py`가 주기 호출, TOP의 EP-12와 동일 방향) | Body: binId, cameraId(기본 ELEV-SIDE), binType, sessionId, currentState(NORMAL/FULL), confidenceScore, overflowDuration, overflowThreshold?, detectionId, modelVersion | 200/422 | `currentState`가 이전 저장값과 다를 때만 전환 처리. NORMAL→FULL: EP-02와 동일한 `eventService`로 overflow EVENT 생성(detectionId 중복 방지 포함)+`activeOverflowEventId` 기록+MANAGE 모드 시 WS 브로드캐스트. FULL→NORMAL: EVENT 생성 없이 `activeOverflowEventId`만 null로 리셋. 상태 유지 시 값만 갱신 |
| EP-12 | POST /api/events/aiDisposal | GPU 서버(`models/trashdetect/tracking2.py`)가 투척 완료 판정 시 직접 푸시하는 전용 엔드포인트 | Body: eventId, trackId, timestamp, cameraId("CAM-01" 등 GPU 쪽 값 그대로), detectedClass("normal"/"paper"/"recyclables"/"coffeecup"), binId(detectedClass와 동일 값 체계), result("correct"/"incorrect"/"unknown"), imagePath? | 200/422 | `eventService.createEventFromAiDisposal`이 GPU 쪽 값을 내부 `EventCreate`로 매핑 후 EP-02의 쿨다운/멱등성을 재사용. `incorrect`이면 GridFS/`visitClips`에 저장된 전체 방문 GIF에서 이벤트 직전 약 5초를 파생해 `imageFileId`에 연결한다. 대응 DB 영상이 아직 없으면 방문 종료 저장 단계에서 연결하고, 영상이 먼저 저장됐으면 `trackId` 또는 카메라/시각으로 찾아 즉시 연결한다. 원본이 없으면 이벤트만 저장한다. `imagePath`는 GPU 로컬 경로라 사용하지 않는다. 매핑 실패 또는 `unknown`은 이벤트 미생성 |
| EP-13 | GET/POST /api/reports/email | 자동 일일·주간 보고서 수신 이메일 조회/저장/해제(즉시 발송 없음) | GET: 없음 / POST Body: recipient(string\|null, 빈 값은 수신 해제) | 200/422/500 | `state/recipientSettings.json`에 주소 또는 명시적 해제 상태를 저장. 해제 상태에서는 환경변수 수신 주소도 폴백하지 않음. Docker에서는 backend와 별도 report-scheduler가 report-state 볼륨 공유. 스케줄러가 매일 09:00 일일, 월요일 09:10 주간 보고서를 자동 발송. 검증된 일일 이벤트 메타데이터를 최근 7일만 임시 저장하고 주간 보고서는 이를 합산하며, 누락 시 발송하지 않음. 전주 비교는 최근 2개 주간 합계만 보존. SMTP 비밀은 서버 설정에만 유지 |
| EP-14 | GET /api/collectionTasks, POST /api/collectionTasks/{collectionTaskId}/acknowledge, POST /api/collectionTasks/{collectionTaskId}/complete, GET /api/collectionAutomation/status | FULL 감지 기반 수거 작업 조회·확인·완료 및 RPA 상태 조회 | 목록: taskStatus?, limit? / 처리: collectionTaskId | 200/404/409/422 | `RPA_COLLECTION_ENABLED=true`일 때 NORMAL→FULL overflow 이벤트에 활성 수거 작업 1건 생성. 별도 collection-scheduler가 최초 담당자 알림→재알림→관리자 에스컬레이션 순으로 발송. 작업·발송 이력·heartbeat는 MongoDB에 영속화 |
| EP-17 | GET /api/visitClips | 방문 클립(presence 기반 녹화, 판정 여부 무관) 목록, 최신순 | Query: limit?(기본 60, 1~200) | 200/422 | 관리자 대시보드에는 노출하지 않음(사이드바/페이지 없음) — 필요 시 직접 호출하는 조회 전용 API. `imageFileId`는 응답에 노출하지 않고 EP-18 경로로만 접근 |
| EP-18 | GET /api/visitClips/{clipId}/media | 방문 클립 GIF 원본 스트리밍(GridFS) | Path: clipId | 200/404 | `clipId`가 유효한 ObjectId가 아니거나 문서가 없으면 404. `cameraId`에 따라 topMedia/sideMedia 버킷에서 읽음(`repositories/mongoClient.py`의 `getGridFsBucket`과 동일 규칙). `Content-Type: image/gif` |
| EP-19 | GET/POST /api/gpuHeartbeats | GPU 서버 추론 스크립트(`tracking2.py`/`sideOverflow.py`)의 생존 신호 조회/수신 | GET: 없음 / POST Body: cameraId(CameraId, ELEV-TOP 또는 ELEV-SIDE만) | 200/422 | POST는 두 스크립트가 판정 이벤트와 무관하게 30초~1분 주기로 호출(EP-12/EP-11과 같은 SSH 역터널 재사용, 별도 포트 불필요), 호출마다 `cameraId`의 `lastSeenAt`을 현재 시각으로 upsert. GET은 관리자 웹(PG-03)이 폴링해 ELEV-TOP/ELEV-SIDE 각각의 `CameraStatus`(ONLINE/OFFLINE)를 표시 — 저장은 `lastSeenAt`만 하고 상태는 조회 시점마다 임계값(90초)과 비교해 계산(`services/gpuHeartbeatService.py`). 하트비트를 한 번도 못 받은 카메라는 OFFLINE |

### EP-02. POST /api/events — 이벤트 생성

Request(EventCreate): cameraId(CameraId), eventCategory(EventCategory), detectionId(str, **구현 완료** — 탐지 파이프라인이 부여하는 중복 저장 방지 키, DB 유니크), trackingId(int|null, misclassification만 — YOLO26 추적 ID), detectedClass(DetectedClass, misclassification일 때만 필수), binId(str, misclassification·overflow 공통 — 물리 통 4개 중 하나), binType(BinType), isMisclassified(bool, misclassification일 때만), confidenceScore(float 0~1, misclassification일 때만), overflowDuration/overflowThreshold(float|null, overflow만), modelVersion(str), imageFileId(str|null, 선택)

Response(Event, 200): eventId(uuid), timestamp(ISO8601), cameraId, eventCategory, detectionId, trackingId(null 가능), detectedClass(null 가능), binId, binType, isMisclassified(null 가능), confidenceScore(null 가능), overflowDuration/overflowThreshold(null 가능), actionTaken(ActionTaken), imageFileId(str|null, GridFS 파일 ID, 녹화 파이프라인 연동 전엔 null), modelVersion, notes(str|null)
- misclassification: isMisclassified=false 또는 5초 Cooldown 중이면 null 반환
- overflow: 현재 백엔드는 시간 Cooldown이나 `BIN_STATES` 전환 검증 없이, 스키마가 유효하고
  `detectionId`가 새 값이면 저장한다. `NORMAL`→`FULL` 전환 시점에만 호출하는 것은 확정 설계이자
  호출자 책임이며 `BIN_STATES`는 아직 코드 미반영(`Docs/ERD.md` 참고)
- 동일 `detectionId`: 새 문서를 만들지 않고 기존 Event를 200으로 반환한다. 내부 생성 결과의
  `created` 상태를 구분하므로, 기존 이벤트를 반환하는 재전송에서는 WS 알림도 다시 보내지 않는다.
- `detectionId`는 비어 있지 않은 문자열, `binId`도 비어 있지 않은 문자열만 검증한다. UUID 형식,
  물리 통 ID 목록, `binId`와 `binType`의 일치는 아직 스키마에서 검증하지 않는다.

부수효과: mode=MANAGE → `actionTaken=lightAndSound` 저장+WS 브로드캐스트(카테고리별 eventType, 실제 RPA 장치는 미구현) / mode=COLLECT → `actionTaken=none` 저장, WS 이벤트 알림 없음. misclassification은 동일 cameraId+detectedClass 5초 내 재호출 무시(Cooldown), overflow는 `detectionId` 유니크 제약으로 저장 중복만 방지(시간 Cooldown 없음)

### EP-08/EP-09. POST /api/detection/start, stop — 녹화 파이프라인 진입점

`services/detectionService.py`: `recordingService`(녹화)→`mediaService`(GIF 인코딩+GridFS
업로드)→`eventService.createEvent`(EP-02와 동일 로직, Cooldown 포함)를 그대로 호출하는 HTTP
연결부. TOP은 `presenceGateService.py`(사람 존재 감지 게이팅)가 EP-08/EP-09를 내부적으로
  호출해 라이브뷰/DB 클립용 녹화를 시작·종료한다. 오분류 판정 자체는 EP-12로 별도 수신하며,
  EP-12의 직전 5초 GIF는 방문 종료 후 GridFS에 저장된 전체 GIF에서 파생한다. 수동
검증(`debug/detection/simulateEventPipeline.py`)도 이 두 엔드포인트를 직접 호출한다.
EP-09는 `eventCategory`에 따라 misclassification/overflow를 모두 처리하며, 기존 호출과의
호환성을 위해 `eventCategory`를 생략하면 misclassification으로 처리한다. misclassification은
`detectedClass`/`isMisclassified`/`confidenceScore`가 필수이고, overflow는 해당 필드를 보내지
않으며 `overflowDuration`/`overflowThreshold`를 선택적으로 보낸다. 두 카테고리 모두
`detectionId`/`binId`/`binType`/`modelVersion`이 필요하다.
`recordingId`가 없으면 404, 프레임이 없으면 400, 스키마/카메라 역할 오류는 422다. GIF 업로드가
이벤트의 `isMisclassified=false`, Cooldown, 중복 `detectionId` 판정보다 먼저 실행되므로 현재는
Event가 새로 저장되지 않아도 GridFS 파일이 먼저 생성될 수 있다.
현재 `recordingId`에 저장된 시작 카메라와 stop 요청의 `cameraId`가 같은지는 검증하지 않는다.
GPU→백엔드 오분류 판정 신호는 이 EP-08/09가 아니라 별도의 EP-12(`POST
/api/events/aiDisposal`)로 확정 수신한다 — 위 "EP-12" 참고.

### EP-17/EP-18. GET /api/visitClips, GET /api/visitClips/{clipId}/media — 방문 클립 조회

`services/visitClipService.py`/`repositories/visitClipRepository.py`(`listRecent`/`findMediaById`)가
`visitClips` 컬렉션을 직접 읽는다. EP-14/15(트랙 신호, 아래 TBD 참고)와 무관하게 이미 저장된
클립을 사람이 확인하기 위한 용도.

EP-17 Response(200, `VisitClipSummary[]`): id(str, Mongo `_id`), cameraId(CameraId),
startedAt/endedAt(ISO8601), trackIds(int[]), matchedEventIds(str[]), unresolvedTrackIds(int[]).
`imageFileId`는 응답에 포함하지 않는다(EP-18로만 접근).

상태 판단은 클라이언트 책임(백엔드가 별도 status 필드를 계산하지 않음):
- `matchedEventIds`가 비어있지 않음 → 판정 확정(EVENT 존재)
- 비어있고 `unresolvedTrackIds`가 비어있지 않음 → 미확정(트랙 시도 후 실패)
- `trackIds`까지 비어있음 → 감지 시도 자체가 없었음(YOLO가 아예 인지 못한 케이스)
- 위 셋 다 아니면 아직 트랙 진행 중(드묾 — 방문 종료 시점엔 보통 해결됨)

세 조건 모두 재학습 후보(`autoTraining/stages/collectEventMedia.py`가 `matchedEventIds` 빈
클립을 `unresolvedVisit`로 수집)이므로, 목록에서 재학습 후보만 보고 싶으면 클라이언트에서
`matchedEventIds.length === 0`으로 필터링한다.

EP-18은 Response Body가 GIF 바이너리이고 JSON이 아니다.

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
| PG-01 | GET / | index.html | 카메라 지점 2개(위+옆, `ELEV-TOP`/`ELEV-SIDE`) 스트리밍(분할 그리드)+모니터링 현황. 템플릿 컨텍스트의 `currentMode`는 현재 `MANAGE` 고정이며 실제 런타임 모드는 WS 연결 직후 동기화. 관리 모드에서 EP-10 응답 중 하나라도 `currentState=FULL`이면 수거 작업 생성 여부와 무관하게 사이드바에 `쓰레기통 가득참` 표시 |
| PG-02 | GET /events | eventsList.html | EP-03 결과 표 렌더링(이전기록), EP-04/EP-04-M 상세 모달과 GIF 썸네일·확대 보기 |
| PG-03 | GET /statistics | statistics.html | EP-05 요약·클래스별 집계와 EP-03 최근 이벤트 렌더링. EP-19를 20초 주기로 폴링하되, 평소엔 아무것도 표시하지 않다가 OFFLINE인 카메라가 있을 때만 상단에 경고 배너 노출(고객이 보는 화면이라 GPU/스크립트명 등 내부 인프라 용어 대신 "오분류 자동 감지"/"쓰레기통 넘침 자동 감지" 기능명으로 표시) |

`GET /events/{id}` 페이지 라우트는 없다. 상세 정보는 `/events`의 모달이 EP-04를 호출하고,
GIF가 있는 이벤트는 EP-04-M으로 썸네일과 확대 이미지를 표시한다.

sidebar.html은 라우트 아님 — 각 페이지에 공통 포함되는 사이드바 partial(모드토글, 네비게이션).

## TBD

- EP-07 detectedClass 필드 추가 여부
- EP-03/EP-05 페이지네이션(limit/offset) 여부
- 인증/권한 (P3, 현재 없음)

## 해결된 TBD

- **`trackStarted`/`trackEnded` 및 방문 클립 연결** → `visitClipService`의 active track과
  `visitClips` 저장소로 구현. EP-12의 오분류 이벤트는 GridFS에 저장된 전체 방문 GIF에서
  직전 약 5초 GIF를 파생하며, 전체 방문 GIF는 재학습/방문 기록으로 분리 유지. GPU 쪽
  (`models/trashdetect/tracking2.py`)도 새 트랙 등록 시 EP-14, 미확정 만료 시 EP-15를
  실제로 호출하도록 구현 완료 — 실기기(GPU 서버) 검증은 아직 TBD(`architecture.md` 참고)

- **GPU↔백엔드 오분류 판정 신호 전달 방식 확정** → 로컬 백엔드가 프레임을 GPU로 보내는
  방향이 아니라, GPU(`models/trashdetect/tracking2.py`)가 자체 판정 후 `POST
  /api/events/aiDisposal`(EP-12)로 결과를 직접 푸시하는 방향으로 확정(`decisionLog.md`
  참고). `DetectedClass`도 5종→4종(plastic/can 통합)으로 축소
- `BIN_STATES` 조회/갱신 API → EP-10(`GET /api/binStates`)/EP-11(`POST /api/binStates`)로 구현
  완료(`schemas/binState.py`, `repositories/binStateRepository.py`, `services/binStateService.py`).
  EP-02/EP-09로 직접 만드는 overflow 이벤트는 여전히 상태 전환 검증 없는 수동/디버그 경로로 남음
- **PG-03 "이벤트 상세 페이지 미구현"** → PG 번호가 재배치되면서(PG-03은 현재 통계 페이지)
  안 지워지고 남아있던 흔적이었음. 상세 페이지 자체는 애초에 별도 라우트를 안 만들기로
  확정된 설계(`GET /events/{id}` 라우트 없음, `/events`의 모달이 EP-04 호출해 표시) —
  "미구현"이 아니라 처음부터 이 방식으로 확정된 것이라 TBD에서 제거
