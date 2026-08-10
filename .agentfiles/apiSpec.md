# API 명세서 — CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템

## 문서 정보

| 항목 | 내용 |
|---|---|
| 버전 | v0.1 (MVP / Mock 단계) |
| Base URL | `http://localhost:8047` (개발) → 배포 시 GPU 서버 주소로 대체 |
| 데이터 포맷 | JSON, 필드명 전부 camelCase |
| 인증 | 없음 (내부망 전용, MVP 범위 밖) |
| 담당 | 1팀 |

---

## 새 엔드포인트 추가 시 템플릿

앞으로 엔드포인트를 추가할 땐 아래 순서를 그대로 따라 작성한다. (ID는 EP- + 두 자리 숫자로 계속 이어서 부여)

개요 |
인증 |
Path Params | 표
Query Params | 표
Request Body | 표
Response | 표
상태 코드 | 표
부수 효과 |
관련 Enum |
비고/TBD |

---

## 1. 공통 Enum

| Enum | 값 |
|---|---|
| CameraId | ELEV-01 / ELEV-02 / REST-4F-01 |
| DetectedClass | general / paper / plastic / coffeeCup / mixed / uncertain |
| ActionTaken | lightAndSound / soundOnly / lightOnly / notificationOnly / none |
| Mode | MANAGE(기본값) / COLLECT |
| CameraStatus | ONLINE / OFFLINE |
| WSEventType | MISCLASSIFICATION_DETECTED / MODE_CHANGED / CAMERA_DISCONNECTED / SYSTEM_ERROR |

## 2. 공통 상태 코드

| 코드 | 상황 |
|---|---|
| 200 | 정상 처리 |
| 422 | 요청 body/query가 스키마(Enum 포함)와 불일치 |
| 500 | 서버 내부 오류 |

---

## 3. JSON API 엔드포인트

### EP-01. GET /api/stream/{cameraId} — 카메라 실시간 스트림

개요 | 지정한 카메라의 실시간 영상을 MJPEG로 스트리밍
인증 | 없음
Path Params | cameraId (CameraId, 필수)
Query Params | 없음
Request Body | 없음
Response | multipart/x-mixed-replace; boundary=frame (MJPEG 스트림, 스키마 없음)
상태 코드 | 200 정상 스트리밍
부수 효과 | 없음
관련 Enum | CameraId
비고/TBD | 개발 단계는 웹캠 1개를 3개 카메라ID에 복제 제공, 배포 후 카메라ID별 독립 RTSP 소스로 교체 예정

---

### EP-02. POST /api/events — 오분류 이벤트 생성

개요 | 오분류 판정 결과를 받아 이벤트를 생성하고 저장
인증 | 없음
Path Params | 없음
Query Params | 없음

Request Body (EventCreate)

필드 | 타입 | 필수 | 설명
cameraId | CameraId | 필수 |
detectedClass | DetectedClass | 필수 |
isMisclassified | boolean | 필수 |
confidenceScore | float | 필수 | 0.0 ~ 1.0

Response (Event, 200) — isMisclassified가 false이거나 5초 Cooldown 중이면 null 반환

필드 | 타입 | 설명
eventId | string(uuid) |
timestamp | string(ISO8601) |
cameraId | CameraId |
detectedClass | DetectedClass |
isMisclassified | boolean |
confidenceScore | float |
actionTaken | ActionTaken |
imageFileId | string 또는 null | GridFS 파일 ID, Mock 단계는 null
notes | string 또는 null |

상태 코드 | 200 정상(이벤트 생성 또는 조건 미충족으로 null) / 422 스키마 불일치

부수 효과 | mode=MANAGE면 RPA 트리거(전구+경고음)+WebSocket MISCLASSIFICATION_DETECTED 브로드캐스트, mode=COLLECT면 통계만 갱신. 동일 cameraId+detectedClass 조합 5초 이내 재호출 시 무시(Cooldown)

관련 Enum | CameraId, DetectedClass, ActionTaken, Mode

비고/TBD | 없음

---

### EP-03. GET /api/events — 이벤트 목록 조회

개요 | 저장된 이벤트를 기간별로 조회
인증 | 없음
Path Params | 없음
Query Params | from (ISO8601 datetime, 선택), to (ISO8601 datetime, 선택)
Request Body | 없음
Response | Event 배열, timestamp 내림차순(Mongo 연동 시)
상태 코드 | 200 정상
부수 효과 | 없음
관련 Enum | CameraId, DetectedClass, ActionTaken
비고/TBD | 페이지네이션(limit/offset) 미구현, 추가 여부 TBD

---

### EP-04. GET /api/events/{id} — 이벤트 상세 조회

개요 | 특정 이벤트 1건 조회
인증 | 없음
Path Params | id (string, eventId, 필수)
Query Params | 없음
Request Body | 없음
Response | Event 1건
상태 코드 | 200 정상 / 조회 실패 시 처리 방식 TBD
부수 효과 | 없음
관련 Enum | CameraId, DetectedClass, ActionTaken
비고/TBD | 현재 구현은 not found 시 null 반환, 404 전환 여부 TBD

---

### EP-05. GET /api/statistics — 통계 집계

개요 | 클래스별 오분류 건수 집계, 캐시 없이 호출 시점마다 온디맨드 집계
인증 | 없음
Path Params | 없음
Query Params | from (ISO8601 datetime, 선택), to (ISO8601 datetime, 선택)
Request Body | 없음

Response

필드 | 타입 | 설명
labels | string 배열 | detectedClass 목록
counts | int 배열 | labels와 동일 순서의 건수

상태 코드 | 200 정상
부수 효과 | 없음
관련 Enum | DetectedClass
비고/TBD | 프론트 Chart.js는 WebSocket 수신 시 로컬 카운터만 낙관적 증가, 새로고침 시 이 엔드포인트로 재동기화. 세부 지표 확장 여부 TBD

---

### EP-06. POST /api/mode — 모드 전환

개요 | 관리모드(MANAGE)/수거모드(COLLECT) 전역 전환
인증 | 없음
Path Params | 없음
Query Params | 없음
Request Body | mode (Mode, 필수)
Response | mode (Mode)
상태 코드 | 200 정상 / 422 잘못된 값
부수 효과 | 성공 시 전체 WebSocket 클라이언트에 MODE_CHANGED 브로드캐스트
관련 Enum | Mode
비고/TBD | 없음

---

### EP-07. WS /ws/events — 실시간 이벤트 스트림

개요 | 관리자 웹 전용 WebSocket. 연결 즉시 현재 Mode를 담은 MODE_CHANGED 1회 전송, 이후 이벤트 발생 시마다 메시지 수신
인증 | 없음
Path Params | 없음
Query Params | 없음
Request Body | 없음(연결 후 서버→클라이언트 단방향 위주)

메시지 스키마 (eventType별)

eventType | payload 필드 | 설명
MISCLASSIFICATION_DETECTED | cameraId, timestamp, isMisclassified | 오분류 발생 시
MODE_CHANGED | mode, timestamp | 모드 전환 시(연결 시 1회 + 전환 성공 시 전체 브로드캐스트)
CAMERA_DISCONNECTED | cameraId, timestamp | 카메라 연결 끊김(30초 재시도 초과)
SYSTEM_ERROR | message, timestamp | 서버 내부 에러

상태 코드 | 해당 없음(WebSocket)
부수 효과 | 없음
관련 Enum | WSEventType, CameraId, Mode
비고/TBD | eventType은 대문자 스네이크케이스(camelCase 규칙의 유일한 예외). MISCLASSIFICATION_DETECTED에 detectedClass 필드 추가 여부 TBD. 새 eventType은 이 표에 먼저 추가 후 구현

---

## 4. 페이지(View) 라우트

JSON을 반환하지 않고 TemplateResponse만 반환. JSON API 컨트롤러(api.py)와 파일 자체가 분리되어 있음(views.py / api.py 혼용 금지).

### PG-01. GET / — 메인

템플릿 | index.html
설명 | 카메라 3대 스트리밍 + 사이드바(모드 토글, 최근 이벤트) + 통계 대시보드
컨텍스트 | mode(SystemState 현재 모드, 새로고침 시 상태 초기화 방지)

### PG-02. GET /events — 이벤트 목록

템플릿 | events_list.html
설명 | EP-03 결과를 표로 렌더링

### PG-03. GET /events/{id} — 이벤트 상세

템플릿 | event_detail.html
설명 | EP-04 결과를 상세 페이지로 렌더링

### PG-04. GET /statistics — 통계 대시보드

템플릿 | statistics.html
설명 | EP-05 결과를 Chart.js로 렌더링

---

## 5. 변경 이력

버전 | 날짜 | 내용
v0.1 | MVP 단계 | 최초 작성 (EP-01~07, PG-01~04)

## 6. 전체 TBD 요약

- GET /api/events/{id} not found 시 404 vs null 응답 방식 (EP-04)
- MISCLASSIFICATION_DETECTED 페이로드에 detectedClass 필드 추가 여부 (EP-07)
- 이벤트 목록/통계 조회 페이지네이션(limit/offset) 추가 여부 (EP-03, EP-05)
- 인증/권한 (P3 우선순위, 현재 없음)
