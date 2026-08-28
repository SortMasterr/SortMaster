# ERD — CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템

> 버전: 고도화 진행 중(MVP 데모 완료). `repositories/eventRepository.py`가 motor(비동기 MongoDB 드라이버) 기반으로 구현됨(in-memory Mock 제거 완료) — `WebApps/backend/schemas/event.py`의 Pydantic 모델을 근거로 작성. **`detectionId`/`trackingId`/`binId`/`binType`/`modelVersion`과 카메라별 GridFS 버킷, `BIN_STATES`(`repositories/binStateRepository.py`) 모두 코드 반영 완료.**
> 실제 영속화되는 것은 MongoDB `events`/`binStates`/`collectionTasks`/
> `collectionAutomationRuns`/`collectionAutomationState`/`gpuHeartbeats` 컬렉션 + GridFS다.
> `CAMERA`/`SystemState`는 현재 DB 컬렉션이 아니라 Enum·런타임 상태라 참고용으로만 표시.
> 손 감지 조합 판정은 폐지되고 쓰레기 감지 자체가 트리거로 바뀜 — 옆 카메라(`ELEV-SIDE`)는
> **GPU 서버의 `models/trashoverflow/sideOverflow.py`**가 **MobileNet_V3_Small** 경량
> 분류 모델로 넘침 상태를 자체 판정하고 `POST /api/binStates`로 로컬 백엔드에 결과를 직접
> 푸시한다(위 카메라와 완전히 동일한 구조 — 과거 룰 베이스 → 로컬 백엔드 CPU 추론(GPU
> 미사용) → 지금의 GPU 서버 방식까지 두 번 재전환됨, `decisionLog.md` 참고)해서 물리
> 쓰레기통 4개(일반/플라스틱·캔/커피컵/종이)의 상태를
> `BIN_STATES`로 지속 추적하다가 **NORMAL→FULL로 전환되는 순간에만** 넘침
> 이벤트 생성+알림. 위 카메라(`ELEV-TOP`)는 **GPU 서버의 YOLO26(`models/trashdetect/
> tracking2.py`)**이 투척 추적+쓰레기 종류 분류+정상/오분류 판정까지 자체적으로 끝내고,
> 결과를 로컬 백엔드로 직접 푸시(`POST /api/events/aiDisposal`) — 로컬 백엔드는 값을
> 그대로 저장할 뿐 재판정하지 않음(메인보드가 라즈베리파이로 바뀌면서 엣지가 아니라 GPU
> 서버가 추론 주체, TOP/SIDE 둘 다 동일). Qwen3-VL-8B(LLM)는 실시간
> 탐지 경로엔 없고 학습 준비 단계 자동 라벨링 검증에 이미 사용 중(`architecture.md`의
> "LLM 활용" 참고). 이벤트는 여전히
> `misclassification`(투기)/`overflow`(넘침) 두 카테고리로 나뉨. 상세는 `architecture.md`의
> "탐지 파이프라인" 참고.

## ER 다이어그램

```mermaid
erDiagram
    CAMERA ||--o{ EVENT : "탐지"
    BIN_STATES ||--o{ EVENT : "binId 기준 이벤트 발생"
    BIN_STATES |o--o| EVENT : "activeOverflowEventId(현재 FULL 유발 이벤트)"
    EVENT ||--o| COLLECTION_TASK : "FULL 전환 시 수거 작업"
    COLLECTION_TASK ||--o{ COLLECTION_AUTOMATION_RUN : "알림 실행 이력"
    EVENT |o--|| MEDIA_FILE : "참조(선택)"
    CAMERA ||--o| GPU_HEARTBEAT : "생존 신호(cameraId 기준, 구현 완료)"
    CAMERA ||--o{ VISIT_CLIP : "presence 감지 기반 방문 녹화(구현 완료)"
    VISIT_CLIP |o--o{ EVENT : "matchedEventIds(trackId로 정밀 매칭, 구현 완료, 실기기 검증 TBD)"
    VISIT_CLIP |o--|| MEDIA_FILE : "imageFileId 참조(구현 완료)"

    CAMERA {
        string cameraId PK "ELEV-TOP/ELEV-SIDE/REST-4F-01(설치 위치는 12층 엘리베이터 앞 1곳뿐). ELEV-TOP=투기 판정 담당, ELEV-SIDE=넘침 감지 담당"
        string status "ONLINE/OFFLINE. 실제 영속화는 GPU_HEARTBEAT가 담당(아래 참고) — 이 필드 자체는 여전히 개념적 표시일 뿐 CAMERA가 실제 컬렉션은 아님"
    }

    GPU_HEARTBEAT {
        string cameraId PK "ELEV-TOP 또는 ELEV-SIDE만(GPU 추론을 실제로 담당하는 카메라, architecture.md 참고)"
        datetime lastSeenAt "GPU 서버(tracking2.py/sideOverflow.py)가 POST /api/gpuHeartbeats(EP-19)를 보낸 마지막 시각. cameraId당 최신 1행만 유지(upsert, BIN_STATES와 동일 패턴)"
    }

    BIN_STATES {
        string binId PK "물리 쓰레기통 4개 중 하나(일반/플라스틱·캔/커피컵/종이). ELEV-SIDE 시야 안에 고정 설치"
        string cameraId "현재 구조상 항상 ELEV-SIDE(넘침 감지는 옆 카메라 전담이라 다른 값 없음)"
        string binType "normal/recyclables/coffeeCup/paper(플라스틱·캔 통은 캔+플라스틱 둘 다 받으며 DetectedClass도 recyclables 하나로 통합). binId와 사실상 1:1, 조인 없이 필터링하려는 비정규화 필드"
        string sessionId "넘침 감지(로컬 백엔드, MobileNet_V3_Small) 프로세스 시작 시 새 UUID 생성 — 재시작/재연결마다 갱신(확정)"
        string currentState "NORMAL / FULL"
        float confidenceScore "최근 판정 신뢰도"
        float overflowDuration "현재 FULL 상태로 유지된 시간(초), 실시간 갱신"
        datetime lastChangedAt "상태(NORMAL↔FULL) 마지막 전환 시각"
        string activeOverflowEventId FK "nullable. NORMAL→FULL 전환 시 생성된 EVENT.eventId, FULL→NORMAL 복귀 시 null로 리셋(확정 — 아래 참고). binId당 최신 상태 1행만 유지하는 upsert 컬렉션(이력은 EVENT가 담당, 확정)"
    }

    EVENT {
        string eventId PK "uuid, 백엔드 생성"
        string detectionId UK "신규 — 감지 시점에 UUID로 생성(eventId와 동일 방식, 확정) — misclassification은 GPU 서버(models/trashdetect/tracking2.py)가, overflow는 GPU 서버(models/trashoverflow/sideOverflow.py)가 자체 생성한 값을 그대로 사용(TOP/SIDE 동일 패턴). trackingId 조합 방식은 세션 종속이라 배제. 유니크 인덱스로 중복 저장 방지 — GPU→백엔드 HTTP POST가 at-least-once일 가능성 대비(TOP/SIDE 둘 다 해당)"
        int trackingId "nullable, misclassification만. YOLO26 트래커가 부여한 추적 ID — 세션 리셋 시 재사용될 수 있어 전역 유니크 아님(그래서 detectionId가 따로 필요), 디버깅/추적용"
        datetime timestamp
        string cameraId FK "CameraId enum(ELEV-TOP/ELEV-SIDE)"
        string eventCategory "misclassification(투기, ELEV-TOP 단독) / overflow(넘침, ELEV-SIDE 단독 — BIN_STATES가 NORMAL→FULL로 전환되는 순간에만 생성)"
        string detectedClass "nullable, misclassification만. YOLO26(GPU 서버 tracking2.py)이 직접 분류. normal/paper/recyclables(모델이 plastic/can을 구분 못 해서 통합)/coffeeCup — 총 4종. mixed/uncertain은 제외 확정"
        string binId FK "물리 통 4개 중 하나 — misclassification: GPU(tracking2.py)가 추적한 실제 투척 통 / overflow: 어느 통이 가득 찼는지. 과거 초안의 thrownBinId를 대체, 두 카테고리 모두 사용"
        string binType "normal/recyclables/coffeeCup/paper — BIN_STATES.binType과 동일 값 비정규화 저장, detectedClass와 값 체계 1:1 일치"
        boolean isMisclassified "nullable, misclassification만. GPU(tracking2.py)가 자체적으로 detectedClass vs 투입된 통을 비교해 판정한 결과(result: correct/incorrect)를 로컬 백엔드가 그대로 boolean으로 변환해 저장 — 백엔드가 재계산하지 않음(아래 참고)"
        float confidenceScore "nullable, misclassification만, 0.0~1.0. tracking2.py 응답에 값이 없어 현재는 고정값 저장(TBD, 아래 참고)"
        float overflowDuration "nullable, overflow만. 전환 확정 시점의 BIN_STATES.overflowDuration 스냅샷"
        float overflowThreshold "nullable, overflow만. FULL 판정 기준 시간(모델/설정값)"
        string actionTaken "lightAndSound/soundOnly/lightOnly/notificationOnly/none"
        datetime acknowledgedAt "nullable, 오분류 알림 공용 확인 시각. 필드가 없는 기존 문서는 미확인"
        string imageFileId FK "nullable, detection start/stop 녹화 사용 시 카메라별 GridFS GIF ID"
        string modelVersion "신규 — YOLO26/Qwen3-VL-8B 등 모델 버전. 재학습 이후 이벤트 비교/추적용"
        string notes "nullable"
    }

    COLLECTION_TASK {
        string collectionTaskId PK "uuid"
        string binId UK "활성 작업에 한해 통별 1건"
        string binType "normal/recyclables/coffeeCup/paper"
        string cameraId "현재 ELEV-SIDE"
        string relatedEventId FK "원인이 된 overflow EVENT"
        string taskStatus "OPEN/ACKNOWLEDGED/COMPLETED/CANCELLED"
        datetime detectedAt
        datetime createdAt
        datetime acknowledgedAt "nullable"
        datetime completedAt "nullable"
        float processingSeconds "nullable"
        int escalationLevel "0 최초/1 재알림/2 관리자"
        datetime lastNotificationAt "nullable"
        int notificationAttemptCount
        string lastFailureReason "nullable, 오류 타입만 저장"
    }

    COLLECTION_AUTOMATION_RUN {
        string runId PK "uuid"
        string collectionTaskId FK
        string actionType "TASK_CREATED/ACKNOWLEDGED/COMPLETED/INITIAL/REMINDER/ESCALATION"
        string status "SUCCESS/FAILED"
        datetime attemptedAt
        string recipientRole "assignee/manager"
        string errorType "nullable"
    }

    MEDIA_FILE {
        ObjectId fileId PK "GridFS _id, 버킷은 카메라별로 분리(topMedia.files/sideMedia.files) — 아래 참고"
        string filename
        string mediaType "GIF(misclassification/overflow 공통, 애니메이션). misclassification은 감지 시작~투척 후 약 3초 텀까지, overflow는 감지 즉시(트리거 시작~종료 실제 구간, 고정 10초 아님)"
        datetime uploadDate
        int length
        int chunkSize
    }

    VISIT_CLIP {
        string cameraId FK "현재는 ELEV-TOP 전용(재학습 대상이 TOP 투기 판정이라서). presence 감지가 GPU 판정과 무관하게 항상 녹화하므로 EVENT 유무와 상관없이 생성됨"
        datetime startedAt "presence 진입(녹화 시작) 시각"
        datetime endedAt "presence 이탈(녹화 종료) 시각"
        string imageFileId FK "GridFS(topMedia) GIF — 판정 여부와 무관하게 항상 채워짐(EVENT.imageFileId와 달리 null 없음)"
        array trackIds "이 구간에 GPU가 trackStarted로 알려온 trackId 목록(YOLO가 아예 인지 못했으면 빈 배열)"
        array matchedEventIds "trackId가 aiDisposal로 확정돼 EVENT가 된 것들의 eventId 목록"
        array unresolvedTrackIds "trackStarted는 왔지만 확정 못 하고 trackEnded(unresolved)로 끝난 trackId 목록"
    }
```

## 참고

- **EVENT**: 실제 MongoDB 컬렉션(`repositories/eventRepository.py`, motor 기반으로 완전 전환 — in-memory Mock 제거). 매 프레임이 아니라 판정 시점에만 Insert됨.
  - 저장소 코드에는 EVENT TTL 인덱스나 자동 삭제 로직이 없다. 운영 환경에서는 외부 DB 정책으로
    7일만 보존된다는 운영 전제를 사용하며, 주간 메일용 메타데이터는 DB 엔티티를 추가하지 않고
    RPA의 `report-state` 파일 볼륨에 최근 7일만 별도 임시 저장한다.
  - `misclassification`: 동일 `cameraId`+`detectedClass` 5초 Cooldown(기존과 동일, 유지)
  - `overflow`: 더 이상 시간 기반 Cooldown이 아님 — `BIN_STATES.currentState`가 `NORMAL`→`FULL`로
    전환되는 순간에만 1건 생성. `FULL` 상태가 계속 유지되는 동안은 재알림 없음(현재 상태는
    `BIN_STATES`로 실시간 조회 가능)
  - `detectionId`(신규, UK)로 DB 레벨 중복 저장 방지 — 시간 기반 Cooldown(스팸성 재감지 방지)과는
    별개 문제(네트워크 재전송 등으로 인한 중복 방지)라 둘 다 유지
- **BIN_STATES**(신규): 물리 쓰레기통 4개(일반/플라스틱·캔/커피컵/종이) 각각의 현재 상태를
  지속 추적하는 컬렉션 — 기존엔 없던 개념. `EVENT`처럼 시점성 로그가 아니라 **각 `binId`당
  최신 상태 1행만 유지**(upsert, 확정 — 이력은 `EVENT`가 담당). `currentState`가
  `NORMAL`→`FULL`로 바뀌는 순간 `EVENT`(overflow)를 생성하고 그 `eventId`를
  `activeOverflowEventId`에 기록, `FULL`→`NORMAL` 복귀 시 `activeOverflowEventId`만 `null`로
  리셋(`EVENT` 생성 없음). `schemas/binState.py`/`repositories/binStateRepository.py`/
  `services/binStateService.py`로 코드 반영 완료 — 조회는 `GET /api/binStates`(EP-10), 갱신은
  `POST /api/binStates`(EP-11, `Docs/API_SPEC.md` 참고)
- **GPU_HEARTBEAT**(신규): GPU 서버 추론 스크립트(`tracking2.py`/`sideOverflow.py`)가
  판정 이벤트와 무관하게 보내는 생존 신호. `BIN_STATES`와 동일하게 `cameraId`당
  `lastSeenAt` 1행만 upsert로 유지하고, ONLINE/OFFLINE 자체는 저장하지 않고 조회
  시점마다 임계값(90초, `services/gpuHeartbeatService.py`)과 비교해 계산한다 — 임계값을
  나중에 조정해도 재계산만 하면 되도록 하기 위함. 대상은 GPU 추론을 실제로 담당하는
  `ELEV-TOP`/`ELEV-SIDE` 둘뿐(`REST-4F-01`은 미설치). `GET`/`POST /api/gpuHeartbeats`
  (EP-19, `.agentfiles/apiSpec.md` 참고)로 코드 반영 완료 — 설계는 `Docs/ARCHITECTURE.md`의
  "추론 인프라" > "GPU 하트비트(헬스체크)" 참고
- **MEDIA_FILE**: MongoDB GridFS 구조, **버킷을 카메라별로 2개 분리**(`topMedia`/`sideMedia` —
  각각 `<bucket>.files`+`<bucket>.chunks`, 기본 버킷명 `fs` 하나만 쓰던 걸 카메라별로 나눔).
  저장 시 `EVENT.cameraId`(위 카메라→`topMedia`, 옆 카메라→`sideMedia`) 기준으로 버킷 선택,
  조회 시에도 동일 기준으로 버킷을 찾아야 함(`imageFileId`만으로는 버킷 특정 불가). 순수
  저장 구조 관리 편의 목적 — 보관 기간 등 정책 차이는 없음(TTL/보관정책 분리는 미정,
  필요해지면 별도 논의). `misclassification`/`overflow` 둘 다 GIF로 저장(`services/mediaService.py`가
  OpenCV 프레임을 Pillow로 인코딩, `repositories/mediaRepository.py`가 업로드), 필드명은
  `imageFileId`로 공용. 녹화 길이는 고정 10초가 아니라 `services/recordingService.py`가
  시작~종료 신호 사이 실제 구간을 캡처(신호 유실 대비 최대 30초 안전 캡) — `misclassification`은
  투척 완료 후 약 3초 텀을 두고 종료 신호가 옴(`architecture.md`).
  **다만 현재 운영 경로에서 실제로 채워지는 건 `topMedia`뿐이다** — presence 기반 방문 녹화가
  TOP 전용(`presenceGateService`가 `CameraId.ELEVTOP` 하나만 돌림)이고, SIDE는 GPU가 EP-11로
  판정만 푸시해 프레임이 백엔드로 오지 않는다. 즉 overflow `EVENT`의 `imageFileId`는 계속
  `null`이고 `/events` 모달도 미리보기 대신 미지원 안내를 띄운다. `sideMedia` 버킷에 쓰는
  경로는 데모 스텁(EP-08/EP-09)으로 `cameraId=ELEV-SIDE` 녹화를 돌릴 때뿐이다.
- **VISIT_CLIP**(신규, **구현 완료, 실기기 검증 TBD** — 백엔드+GPU 쪽 신호 전송 코드 모두
  반영됐으나 실제 GPU 서버에서 신호가 정상 도달하는지는 아직 검증 안 됨): `EVENT`처럼 판정이 확정된
  것만 저장하는 게 아니라, **presence 감지로 "누가 통 근처에 왔다 갔다"는 사실 자체를 판정
  여부와 무관하게 항상 기록**하는 컬렉션. 재학습(`autoTraining`)에 YOLO가 놓친 실패 사례를
  공급하기 위한 용도 — 상세 배경/설계는 `architecture.md`의 "재학습용 미확정 방문 캡처",
  결정 이유는 `decisionLog.md` 참고. `EVENT`와 분리한 이유는 `EVENT`가 대시보드
  통계/알림의 근거 컬렉션이라 미확정 방문까지 섞이면 통계가 오염되기 때문 — `VISIT_CLIP`은
  순수 재학습 데이터 소스 용도로만 쓰고 대시보드에 노출 안 함(TBD: 관리자 웹에서 이걸 볼
  필요가 생기면 별도 화면 검토)
- **CAMERA**: 별도 컬렉션 없음. `CameraId` Enum + 설정값으로만 존재하는 개념적 엔티티. 현재 코드는 3개 고정(`ELEV-TOP`, `ELEV-SIDE`, `REST-4F-01`) — `.agentfiles/architecture.md` 참고.
- **통계(`GET /api/statistics`)**: 저장 없이 매 요청마다 `EVENT`에서 온디맨드 집계 — 별도 엔티티 아님. `overflow`는 `detectedClass`별 집계에 안 섞고(애초에 `detectedClass`가 없음), `overflowCount` 같은 별도 필드로 분리 집계(확정 — 성격이 다른 카테고리를 같은 막대그래프에 억지로 합치면 오히려 헷갈림).
- **SystemState.mode**(`MANAGE`/`COLLECT`): 전역 상태로만 언급되고 영속화 계층(DB/파일) 명시 없어 ERD에서 제외.
- 탐지 모델(TOP=YOLO26/GPU 서버 `models/trashdetect/tracking2.py` 상시 추론, SIDE=MobileNet_V3_Small/GPU 서버 `models/trashoverflow/sideOverflow.py` 상시 추론, Qwen3-VL-8B=GPU 서버 학습용 자동 라벨링 검증) 자체는 DB에 영속화되는 대상이 아니라 ERD 범위 밖.
- **DB 실행 위치**: MongoDB는 **로컬**(`<LOCAL_BACKEND_IP>`, 실제 값은 Notion 참고)에서 `backend`와 같이 구동(배포
  위치 재조정 확정 — GPU 서버로 이전했던 건 보류됨, `.agentfiles/architecture.md` 참고).
  `training`(GPU 서버)이 학습용 이미지를 가져올 때만 역방향 SSH 터널로 이 DB에 접속 —
  ERD의 엔티티 구조 자체엔 영향 없음.

## 해결된 TBD

- **`GET /api/events`/`/api/events/{id}` 및 이전기록 화면에 `binId` 반영 완료** →
  Event 스키마·MongoDB 문서·`eventsList.js`가 모두 실제 `binId`를 사용
- **물리 쓰레기통 구성 확정** → 카메라에 4개(일반/플라스틱·캔/커피컵/종이)가 잡히며
  `binId`가 이 4개 중 하나를 가리킨다 — 이전에 고민했던 "카메라 위치 특정 폐지"와는
  다른 층위(카메라 역할 분담 vs 개별 통 식별)라 서로 모순 아님
- **`EVENT`에 "배출 위치" 필드 추가 확정, 필드명은 `binId`로 정리** → 과거 초안에서
  `thrownBinId`로 불렀던 걸 `binId`로 통일(overflow 이벤트에도 쓰이게 되면서 "투척"이라는
  이름이 misclassification 전용처럼 보여서 변경). 대시보드가 "위치"(cameraId)와 "배출
  위치"(어느 통에 들어갔는지)를 별도 컬럼으로 요구했고, 프론트(`eventsList.js`)에 이미 이
  갭의 흔적(cameraId로 임시 대체하던 주석)이 있어서 확정
- **`isMisclassified` 판정 시 "원래 어떤 클래스용 통인지" 매핑 방식 확정** → 별도
  `expectedClass` 필드 없이, `binType`(= binId가 가리키는 통의 고정 종류)을 `detectedClass`와
  비교해서 판정. `binType`이 사실상 정적 매핑 역할을 함
- **넘침(overflow) 이벤트 생성 기준을 시간 Cooldown → 상태 전환으로 확정** → `BIN_STATES`로
  통별 `NORMAL`/`FULL` 상태를 지속 추적하다가 `NORMAL`→`FULL`로 바뀌는 순간에만 `EVENT` 생성.
  기존 "동일 카메라 기준 5초 Cooldown(가정)" 방식 폐기
- **`detectionId`(중복 방지)/`trackingId`(YOLO 추적 ID)/`modelVersion` 필드 추가 확정** →
  `detectionId`는 DB 유니크 인덱스로 중복 저장 방지(misclassification은 GPU 서버↔중앙
  백엔드 신호 전달이 at-least-once일 가능성 대비, overflow는 로컬 백엔드 내부 생성이라
  해당 없음 — 시간 기반 Cooldown과는 별개 목적). `trackingId`는 디버깅/추적용(전역
  유니크 아님). `modelVersion`은 재학습 이후 이벤트 비교용
- **`EVENT` 컬렉션은 카메라별로 물리 분리하지 않기로 확정** → `GET /api/events`가 `cameraId`
  필터 없이 전 카테고리를 한 컬렉션에서 조회하는 구조(`services/eventService.py`의
  `getEvents()`)라, 물리 DB를 나누면 매번 여러 DB를 쿼리해서 합쳐야 함. `cameraId` 필드
  하나로 이미 카메라별 구분이 가능해서 컬렉션 하나로 유지
- **영상(GridFS) 저장은 카메라별로 버킷 2개(`topMedia`/`sideMedia`)로 분리 확정** → 위
  `EVENT`와는 별개 결정. 물리 DB가 아니라 같은 DB 안 GridFS 버킷만 나누는 거라 연결/인증
  추가 없이 저장 구조만 정리됨. 목적은 순수 관리 편의(보관정책 차이 아님) — `EVENT`를
  한 컬렉션으로 유지하기로 한 결정과 모순 아님(조회 시 카메라 통합이 필요 없는 미디어
  블롭 저장소라 나눠도 조회 편의성 손해가 없음)
- 이미지/영상 필드 공용 여부 → `imageFileId` 하나로 공용 확정. `misclassification`/`overflow`
  둘 다 GIF로 저장(별도 `videoFileId` 안 둠). 녹화 길이도 고정 10초가 아니라 트리거
  시작~종료 신호 사이 실제 구간으로 계산(`services/recordingService.py`)
- ~~**`binType`은 `plasticCan` 유지, `DetectedClass`에 `can` 추가하는 걸로 확정**~~ →
  **번복됨(`decisionLog.md` 참고)**. 실제 YOLO26 모델(`models/trashdetect/tracking2.py`)이
  plastic/can을 구분 못 하고 `recyclables` 하나로만 내놓는다는 게 확인돼, `can`을 다시
  제거하고 현재는 `DetectedClass.RECYCLABLES`(`"recyclables"`) 하나로 통합함. 아래 남은 문단은
  당시 맥락 기록용으로 남겨둠 — 지금은 `DetectedClass`와 `binType`이 값 체계까지 완전히
  1:1이라 다대일 매핑 자체가 필요 없음
- **`DetectedClass`에서 `mixed`/`uncertain` 제외 확정** → 라벨링 기준을 정하려다가, 팀
  자체 라벨링 시엔 어차피 모든 대상을 4종(normal/paper/recyclables/coffeeCup) 중
  하나로 분류할 수 있다고 판단해서 아예 클래스에서 뺌. `DetectedClass`가 `binType`(4종)에
  1:1로 완전히 매핑되는 닫힌 집합이 되어, "매핑 없는 값" 예외 처리 자체가 불필요해짐
  (예전에 검토했던 "mixed/uncertain은 매핑 없어서 자동 오분류" 로직도 같이 폐기)
- **`BIN_STATES`는 `binId`당 최신 상태 1행만 유지(upsert) 확정** → 상태 변경 이력은
  `EVENT`(overflow 카테고리)가 이미 담당해서 중복 보관 불필요. `sessionId`는 로컬 백엔드의
  넘침 감지 프로세스 시작 시 새 UUID 생성으로 확정(판정 방식 자체는 룰 베이스→
  MobileNet_V3_Small로 이후 재전환됨, `decisionLog.md` 참고 — `sessionId` 생성 시점 규칙은
  영향 없음)
- **`FULL`→`NORMAL` 복귀 시 별도 `EVENT` 생성 안 함 확정** → "매 프레임 Insert 금지, 판정
  시점만 저장"(`architecture.md`) 원칙 유지 — 복귀는 문제 상황이 아니라 정상 회복이라
  `BIN_STATES.currentState`만 갱신, `activeOverflowEventId`는 이때 `null`로 리셋
- **`detectionId` 생성 방식 확정** → 감지 시점에 UUID 생성(`eventId`와 동일 방식) —
  misclassification은 GPU 서버 `tracking2.py`, overflow는 로컬 백엔드(현재는
  MobileNet_V3_Small, 판정 방식 재전환 이력은 `decisionLog.md` 참고)가 생성.
  `cameraId`+`trackingId` 조합안은 `trackingId`가 세션 종속이라 배제
- **통계에서 `overflow`는 별도 필드로 분리 집계 확정** → `detectedClass`별 집계와 안 섞음
  (`overflow`엔 애초에 `detectedClass`가 없어서)

## 자동 재학습 데이터 저장소

`autoTraining`은 이벤트 저장 구조와 분리된 `trainingSamples` 컬렉션과 `trainingImages`
GridFS 버킷을 사용한다. `trainingSamples.imageFileId`가 GridFS 객체를 참조하며
`imageSha256`은 unique index, `status`+`createdAt`은 동기화 조회 index를 사용한다.
Publish는 사람 승인 샘플만 추가하고 메타데이터 저장 실패 시 먼저 올린 GridFS 파일을 보상
삭제한다. 코드 구현은 완료됐으나 운영 DB 적용·검증은 아직 수행하지 않았다.
