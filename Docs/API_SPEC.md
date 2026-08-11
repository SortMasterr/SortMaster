# API 명세서 — CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템

> 버전: MVP(Mock 단계) 기준. 엔드포인트 경로/이벤트 구조는 고정 — 임의 변경 금지.
> Base URL: `http://localhost:8047` (개발), 배포 시 GPU 서버(L40S) 주소로 대체
> AI 에이전트용 요약본: `.agentfiles/apiSpec.md` — 이 문서 수정 시 반드시 함께 업데이트할 것(둘 다 EP-ID 기준으로 대응)

---

## 탐지 파이프라인 개요 (2단계 모델)

- **상시 감시(경량)**: YOLOv8-Nano 상주, ROI(쓰레기통 위치 고정) 내 객체 분석
  - 손 O + 쓰레기 O → **투기 이벤트**(`misclassification`) → 정밀 분석 단계로
  - 손 X + 쓰레기 O → **넘침 이벤트**(`overflow`, 쓰레기통 포화) → 정밀 분석 없이 영상 녹화만
- **정밀 분석(투기 이벤트만)**: 트리거 즉시 10초 고화질 영상 녹화 + YOLOv8-Medium 로드해 캔/페트/종이/기타 정밀 분류
- 2단계 전부 중앙 GPU 서버에서 처리(젯슨 나노는 캡처+RTSP 송신+GPIO 알림 수신만 담당). 자세한 내용은 `.agentfiles/architecture.md` 참고

---

## 공통 사항

- **데이터 포맷**: JSON, 필드명은 모두 **camelCase**
- **인증**: 없음 (내부망 전용, MVP 범위 밖)
- **CORS**: 프론트/백엔드가 같은 origin이라 미들웨어 없음
- **에러 응답**: FastAPI 기본 형식 `{"detail": "..."}`, 스키마 검증 실패 시 HTTP 422

### 공통 Enum

| Enum | 값 |
|---|---|
| `CameraId` | `ELEV-01` \| `ELEV-02` \| `REST-4F-01` |
| `EventCategory` | `misclassification`(투기, 손+쓰레기 감지→정밀분류) \| `overflow`(넘침, 쓰레기만 감지→녹화만, 분류 없음) |
| `DetectedClass` | `general` \| `paper` \| `plastic` \| `coffeeCup` \| `mixed` \| `uncertain` — `misclassification` 이벤트에서만 사용 |
| `ActionTaken` | `lightAndSound` \| `soundOnly` \| `lightOnly` \| `notificationOnly` \| `none` |
| `Mode` | `MANAGE`(기본값) \| `COLLECT` |
| `CameraStatus` | `ONLINE` \| `OFFLINE` |
| `WSEventType` | `MISCLASSIFICATION_DETECTED` \| `BIN_OVERFLOW_DETECTED` \| `MODE_CHANGED` \| `CAMERA_DISCONNECTED` \| `SYSTEM_ERROR` |

---

## 1. JSON API (`controllers/api.py`)

### 1-1. `GET /api/stream/{cameraId}`

카메라별 실시간 영상 스트림. 지점당 위(Top)/옆(Side) 카메라 2대 중 하나를 선택해서 받음.

| 항목 | 내용 |
|---|---|
| Path Param | `cameraId` — `CameraId` Enum |
| Query Param | `role` — `"top"` \| `"side"`, 기본값 `"top"` |
| 응답 | `multipart/x-mixed-replace; boundary=frame` (MJPEG 스트림) |
| 상태 코드 | 200 정상 / 503 카메라 미설정·연결 실패 |
| 비고 | 개발 단계: `.env`의 `CAMERA_SOURCE`(top)/`CAMERA_SOURCE_SIDE`(side) 웹캠을 그대로 제공(`CAMERA_SOURCE_SIDE` 미설정 시 `role=side`는 503). 배포 후엔 각 카메라별 독립 RTSP 소스로 교체 예정 |

---

### 1-2. `POST /api/events`

이벤트 생성. 매 프레임이 아니라 **투기(오분류) 또는 넘침으로 판정된 시점에만** 호출됨(내부 로직 기준. 외부에서 호출 시에도 동일 규칙 적용).

**Request Body** (`EventCreate`)

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `cameraId` | CameraId | ✅ | |
| `eventCategory` | EventCategory | ✅ | |
| `detectedClass` | DetectedClass \| null | `eventCategory=misclassification`일 때만 | `overflow`는 생략/null |
| `isMisclassified` | boolean \| null | `eventCategory=misclassification`일 때만 | `overflow`는 생략/null |
| `confidenceScore` | float \| null | `eventCategory=misclassification`일 때만 | 0.0 ~ 1.0, `overflow`는 생략/null |

**Response** (`Event`, 200)

| 필드 | 타입 | 설명 |
|---|---|---|
| `eventId` | string (uuid) | |
| `timestamp` | string (ISO8601) | |
| `cameraId` | CameraId | |
| `eventCategory` | EventCategory | |
| `detectedClass` | DetectedClass \| null | `overflow`면 null |
| `isMisclassified` | boolean \| null | `overflow`면 null |
| `confidenceScore` | float \| null | `overflow`면 null |
| `actionTaken` | ActionTaken | |
| `imageFileId` | string \| null | GridFS 파일 ID(이미지/영상 공용). Mock 단계는 null |
| `notes` | string \| null | |

- **misclassification**: `isMisclassified=false`이거나 5초 Cooldown 중이면 `null` 반환(이벤트 미생성)
- **overflow**: 감지 즉시 이벤트 생성(분류 단계 없음), 영상 녹화만 수행

**예시 (투기)**
```bash
curl -X POST http://localhost:8047/api/events \
  -H "Content-Type: application/json" \
  -d '{"cameraId":"ELEV-01","eventCategory":"misclassification","detectedClass":"mixed","isMisclassified":true,"confidenceScore":0.85}'
```

**예시 (넘침)**
```bash
curl -X POST http://localhost:8047/api/events \
  -H "Content-Type: application/json" \
  -d '{"cameraId":"ELEV-01","eventCategory":"overflow"}'
```

**부수 효과**
- `SystemState.mode == MANAGE`: RPA 트리거(전구+경고음) + WebSocket 브로드캐스트(카테고리별 `eventType`: `misclassification`→`MISCLASSIFICATION_DETECTED`, `overflow`→`BIN_OVERFLOW_DETECTED`)
- `SystemState.mode == COLLECT`: 통계만 갱신, 알림/브로드캐스트 스킵
- Cooldown(5초): `misclassification`은 동일 `cameraId`+`detectedClass` 조합, `overflow`는 동일 `cameraId` 기준으로 재호출 무시 (overflow Cooldown 기준은 TBD, 현재는 misclassification과 동일 5초로 가정)

---

### 1-3. `GET /api/events`

이벤트 목록 조회.

| Query Param | 타입 | 필수 | 설명 |
|---|---|---|---|
| `from` | ISO8601 datetime | ❌ | 시작 시각 |
| `to` | ISO8601 datetime | ❌ | 종료 시각 |

**Response**: `Event[]` — `timestamp` 내림차순(최신순, Mongo 연동 시). `misclassification`/`overflow` 혼합 반환

---

### 1-4. `GET /api/events/{id}`

이벤트 상세 조회.

| Path Param | 타입 | 설명 |
|---|---|---|
| `id` | string | `eventId` |

**Response**: `Event` 또는 404(현재 구현은 not found 시 `null` 반환, 404 처리는 TBD)

---

### 1-5. `GET /api/statistics`

클래스별 통계 집계. **캐시 없이 호출 시점마다 온디맨드 집계**.

| Query Param | 타입 | 필수 |
|---|---|---|
| `from` | ISO8601 datetime | ❌ |
| `to` | ISO8601 datetime | ❌ |

**Response**
```json
{ "labels": ["mixed", "uncertain"], "counts": [12, 3] }
```

> 프론트 Chart.js는 WebSocket 이벤트 수신 시 로컬 카운터만 낙관적으로 증가시키고, 새로고침 시 이 엔드포인트로 재동기화함.
> `overflow` 건수를 이 집계에 포함할지, `misclassification`과 분리 집계할지는 TBD.

---

### 1-6. `POST /api/mode`

관리모드/수거모드 전환. 전역 상태(`SystemState`)에 저장.

**Request Body**
```json
{ "mode": "MANAGE" }
```
`mode`: `"MANAGE"` \| `"COLLECT"`

**Response**
```json
{ "mode": "MANAGE" }
```

**부수 효과**: 성공 시 전체 WebSocket 클라이언트에 `MODE_CHANGED` 브로드캐스트

---

### 1-7. `WS /ws/events`

실시간 이벤트 스트림 (관리자 웹 전용).

- 연결(accept) 즉시 서버가 현재 Mode를 담은 `MODE_CHANGED` 메시지 1회 전송
- 이후 아래 `eventType`별 메시지를 비동기로 수신

#### WebSocket 메시지 규격 (고정)

| `eventType` | payload 필드 | 설명 |
|---|---|---|
| `MISCLASSIFICATION_DETECTED` | `cameraId`, `timestamp`, `isMisclassified` | 투기(오분류) 발생 시. `detectedClass` 필드 추가 여부 TBD |
| `BIN_OVERFLOW_DETECTED` | `cameraId`, `timestamp` | 쓰레기통 포화(넘침) 감지 시 |
| `MODE_CHANGED` | `mode`, `timestamp` | 모드 전환 시(연결 시 1회 + `POST /api/mode` 성공 시 전체 브로드캐스트) |
| `CAMERA_DISCONNECTED` | `cameraId`, `timestamp` | 카메라 연결 끊김(30초 재시도 초과) |
| `SYSTEM_ERROR` | `message`, `timestamp` | 서버 내부 에러 |

**예시 (투기 발생)**
```json
{
  "eventType": "MISCLASSIFICATION_DETECTED",
  "cameraId": "ELEV-01",
  "timestamp": "2026-08-06T10:15:30.123Z",
  "isMisclassified": true
}
```

**예시 (넘침 발생)**
```json
{
  "eventType": "BIN_OVERFLOW_DETECTED",
  "cameraId": "ELEV-01",
  "timestamp": "2026-08-06T10:15:30.123Z"
}
```

> `eventType`은 대문자 스네이크케이스(camelCase 규칙의 유일한 예외). 새 타입/필드는 이 표에 먼저 추가 후 구현 — 임의 문자열 금지.

---

## 2. 페이지(View) 라우트 (`controllers/views.py`)

JSON을 반환하지 않고 `TemplateResponse`만 반환. JSON API와 컨트롤러 파일 자체가 분리되어 있음(`views.py` / `api.py` 혼용 금지).

| Method | Path | 템플릿 | 설명 |
|---|---|---|---|
| GET | `/` | `index.html` | 메인 — 지점 1곳의 위/옆 카메라 2대 스트리밍(2분할) + 모니터링 현황 |
| GET | `/events` | `history.html` | 이전기록(이벤트 목록) |
| GET | `/events/{id}` | (미정) | 이벤트 상세 — 템플릿 아직 없음, 구현 전 |
| GET | `/statistics` | `dashboard.html` | 통계 대시보드 |

> `sidebar.html`은 라우트가 아니라 각 페이지에 공통으로 포함되는 사이드바 partial(모드 토글, 페이지 네비게이션).
> `GET /`는 `SystemState`의 현재 모드를 템플릿 컨텍스트로 함께 전달 — 새로고침 시 프론트 상태 초기화 방지.

---

## 3. 상태 코드 요약

| 코드 | 상황 |
|---|---|
| 200 | 정상 처리 |
| 422 | 요청 body/query가 스키마(Enum 포함)와 불일치 — 예: `cameraId`가 허용 목록 외 값 |
| 500 | 서버 내부 오류 (DB 저장 실패 등) |

---

## 4. 아직 미확정 (TBD) — API에 영향 줄 수 있는 항목

- `GET /api/events/{id}` not found 시 404 vs null 응답 방식
- `MISCLASSIFICATION_DETECTED` 페이로드에 `detectedClass` 필드 추가 여부
- 이벤트 목록/통계 조회 시 페이지네이션(limit/offset) 추가 여부 (현재 미구현)
- 인증/권한 (P3 우선순위, 현재 없음)
- `overflow` 이벤트의 Cooldown 기준(현재는 `misclassification`과 동일 5초로 가정, 재검토 필요)
- 통계(`GET /api/statistics`)에 `overflow` 건수도 포함할지, `misclassification`과 분리 집계할지
- `GET /events/{id}` 템플릿(이벤트 상세 페이지) 미구현
