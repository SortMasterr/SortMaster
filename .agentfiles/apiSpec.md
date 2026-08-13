# apiSpec.md

v0.1(MVP/Mock). Base URL `http://localhost:8047`(배포 시 GPU 서버 주소). JSON camelCase. 인증 없음(내부망).

새 엔드포인트 추가 시 이 문서 형식(EP-번호, 표) 그대로 유지.

## 공통 Enum

| Enum | 값 |
|---|---|
| CameraId | (현재 코드 기준, 마이그레이션 전) ELEV-01 / ELEV-02 / REST-4F-01 — 확정된 목표는 `ELEV-TOP`/`ELEV-SIDE`(설치 위치 1곳뿐이라 번호 없음, `.agentfiles/architecture.md` 참고, 아직 코드 미반영) |
| EventCategory | misclassification(투기, 위 카메라의 YOLO26 감지+Qwen3-VL-8B 비동기 분류 결과가 투척 위치와 불일치) / overflow(넘침, 옆 카메라 감지→위 카메라 위치 특정, 분류 없이 녹화만) |
| DetectedClass | general / paper / plastic / coffeeCup / mixed / uncertain — misclassification 이벤트에서만 사용 |
| ActionTaken | lightAndSound / soundOnly / lightOnly / notificationOnly / none |
| Mode | MANAGE(기본값) / COLLECT |
| CameraStatus | ONLINE / OFFLINE |
| WSEventType | MISCLASSIFICATION_DETECTED / BIN_OVERFLOW_DETECTED / MODE_CHANGED / CAMERA_DISCONNECTED / SYSTEM_ERROR |

상태 코드: 200 정상 / 422 스키마 불일치 / 500 서버 오류

## JSON API

| ID | Method/Path | 설명 | Params | 상태코드 | 부수효과 |
|---|---|---|---|---|---|
| EP-01 | GET /api/stream/{cameraId} | MJPEG 스트림 | Path: cameraId(CameraId) | 200/503 | 카메라 1대=지점 1개=1cameraId(role 파라미터 없음, 구조 불변). 위+옆 카메라 지점 도입으로 `CameraId`가 `ELEV-TOP`/`ELEV-SIDE`로 확정(설치 위치가 12층 엘리베이터 앞 1곳뿐이라 번호 불필요, 아직 코드 미반영 — `.agentfiles/architecture.md` 참고). 카메라 미설정/연결 실패 시 503. 개발=`.env`의 `CAMERA_SOURCE_<ID>`(예: `CAMERA_SOURCE_ELEV01`, 현재 코드 기준) 웹캠, 배포=카메라별 독립 RTSP |
| EP-03 | GET /api/events | 이벤트 목록 | Query: from?, to?(ISO8601) | 200 | 없음. 페이지네이션 미구현(TBD) |
| EP-04 | GET /api/events/{id} | 이벤트 상세 | Path: id | 200 | 없음. not found 시 404 vs null TBD |
| EP-05 | GET /api/statistics | 클래스별 집계, 온디맨드(캐시없음) | Query: from?, to? | 200 | 없음. Chart.js는 WS로 낙관적 증가, 새로고침 시 재동기화 |
| EP-06 | POST /api/mode | 모드 전환 | Body: mode(Mode) | 200/422 | 성공 시 전체 WS 클라이언트에 MODE_CHANGED 브로드캐스트 |

### EP-02. POST /api/events — 이벤트 생성

Request(EventCreate): cameraId(CameraId), eventCategory(EventCategory), detectedClass(DetectedClass, misclassification일 때만 필수), isMisclassified(bool, misclassification일 때만), confidenceScore(float 0~1, misclassification일 때만), imageFileId(str|null, 선택 — 녹화 파이프라인이 GridFS 업로드 후 채워서 전달, 생략 시 null) — overflow는 cameraId+eventCategory(+imageFileId)만

Response(Event, 200): eventId(uuid), timestamp(ISO8601), cameraId, eventCategory, detectedClass(null 가능), isMisclassified(null 가능), confidenceScore(null 가능), actionTaken(ActionTaken), imageFileId(str|null, GridFS 파일 ID, 녹화 파이프라인 연동 전엔 null), notes(str|null)
- misclassification: isMisclassified=false 또는 5초 Cooldown 중이면 null 반환
- overflow: 감지 즉시 이벤트 생성(분류 단계 없음), 영상 녹화만 수행

부수효과: mode=MANAGE → RPA트리거+WS 브로드캐스트(카테고리별 eventType) / mode=COLLECT → 통계만 갱신. 동일 cameraId+detectedClass(또는 overflow는 cameraId) 5초 내 재호출 무시(Cooldown)

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
| PG-01 | GET / | index.html | 카메라 지점 2개(위+옆, 목표 `ELEV-TOP`/`ELEV-SIDE`. 현재 코드는 ELEV-01/ELEV-02) 스트리밍(분할 그리드)+모니터링 현황. mode를 컨텍스트로 전달(새로고침 시 상태유지) |
| PG-02 | GET /events | history.html | EP-03 결과 표 렌더링(이전기록) |
| PG-03 | GET /events/{id} | (미정) | EP-04 결과 렌더링 — 템플릿 아직 없음, 구현 전 |
| PG-04 | GET /statistics | dashboard.html | EP-05 결과 Chart.js 렌더링 |

sidebar.html은 라우트 아님 — 각 페이지에 공통 포함되는 사이드바 partial(모드토글, 네비게이션).

## TBD

- EP-04 not found 시 404 vs null
- EP-07 detectedClass 필드 추가 여부
- EP-03/EP-05 페이지네이션(limit/offset) 여부
- 인증/권한 (P3, 현재 없음)
- overflow 이벤트의 Cooldown 기준(현재는 misclassification과 동일 5초로 가정, 재검토 필요)
- PG-03 템플릿(이벤트 상세 페이지) 미구현
- 통계(EP-05)에 overflow 건수도 포함할지, misclassification과 분리 집계할지
