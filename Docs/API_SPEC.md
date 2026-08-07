# API 명세서 — CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템

> 버전: MVP(Mock 단계) 기준. 엔드포인트 경로/이벤트 구조는 고정 — 임의 변경 금지.
> Base URL: `http://localhost:8000` (개발), 배포 시 H100 서버 주소로 대체

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
| `DetectedClass` | `general` \| `paper` \| `plastic` \| `coffeeCup` \| `mixed` \| `uncertain` |
| `ActionTaken` | `lightAndSound` \| `soundOnly` \| `lightOnly` \| `notificationOnly` \| `none` |
| `Mode` | `MANAGE`(기본값) \| `COLLECT` |
| `CameraStatus` | `ONLINE` \| `OFFLINE` |

---

## 1. JSON API (`controllers/api.py`)

### 1-1. `GET /api/stream/{cameraId}`

카메라별 실시간 영상 스트림.

| 항목 | 내용 |
|---|---|
| Path Param | `cameraId` — `CameraId` Enum |
| 응답 | `multipart/x-mixed-replace; boundary=frame` (MJPEG 스트림) |
| 비고 | 개발 단계는 웹캠 1개를 3개 카메라ID에 복제해서 제공. 배포 후엔 각 카메라ID별 독립 RTSP 소스로 교체 예정 |

---

### 1-2. `POST /api/events`

오분류 이벤트 생성. 매 프레임이 아니라 **오분류로 판정된 시점에만** 호출됨(내부 로직 기준. 외부에서 호출 시에도 동일 규칙 적용).

**Request Body** (`EventCreate`)

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `cameraId` | CameraId | ✅ | |
| `detectedClass` | DetectedClass | ✅ | |
| `isMisclassified` | boolean | ✅ | |
| `confidenceScore` | float | ✅ | 0.0 ~ 1.0 |

**Response** (`Event`, 200) — `isMisclassified=false`이거나 5초 Cooldown 중이면 `null` 반환(이벤트 미생성)

| 필드 | 타입 | 설명 |
|---|---|---|
| `eventId` | string (uuid) | |
| `timestamp` | string (ISO8601) | |
| `cameraId` | CameraId | |
| `detectedClass` | DetectedClass | |
| `isMisclassified` | boolean | |
| `confidenceScore` | float | |
| `actionTaken` | ActionTaken | |
| `imageFileId` | string \| null | GridFS 파일 ID (Mock 단계는 null) |
| `notes` | string \| null | |

**예시**
```bash
curl -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{"cameraId":"ELEV-01","detectedClass":"mixed","isMisclassified":true,"confidenceScore":0.85}'
```

**부수 효과**
- `SystemState.mode == MANAGE`: RPA 트리거(전구+경고음) + WebSocket `MISCLASSIFICATION_DETECTED` 브로드캐스트
- `SystemState.mode == COLLECT`: 통계만 갱신, 알림/브로드캐스트 스킵
- 동일 `cameraId`+`detectedClass` 조합 5초 이내 재호출 시 무시(Cooldown)

---

### 1-3. `GET /api/events`

이벤트 목록 조회.

| Query Param | 타입 | 필수 | 설명 |
|---|---|---|---|
| `from` | ISO8601 datetime | ❌ | 시작 시각 |
| `to` | ISO8601 datetime | ❌ | 종료 시각 |

**Response**: `Event[]` — `timestamp` 내림차순(최신순, Mongo 연동 시)

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
| `MISCLASSIFICATION_DETECTED` | `cameraId`, `timestamp`, `isMisclassified` | 오분류 발생 시. `detectedClass` 필드 추가 여부 TBD |
| `MODE_CHANGED` | `mode`, `timestamp` | 모드 전환 시(연결 시 1회 + `POST /api/mode` 성공 시 전체 브로드캐스트) |
| `CAMERA_DISCONNECTED` | `cameraId`, `timestamp` | 카메라 연결 끊김(30초 재시도 초과) |
| `SYSTEM_ERROR` | `message`, `timestamp` | 서버 내부 에러 |

**예시 (오분류 발생)**
```json
{
  "eventType": "MISCLASSIFICATION_DETECTED",
  "cameraId": "ELEV-01",
  "timestamp": "2026-08-06T10:15:30.123Z",
  "isMisclassified": true
}
```

> `eventType`은 대문자 스네이크케이스(camelCase 규칙의 유일한 예외). 새 타입/필드는 이 표에 먼저 추가 후 구현 — 임의 문자열 금지.

---

## 2. 페이지(View) 라우트 (`controllers/views.py`)

JSON을 반환하지 않고 `TemplateResponse`만 반환. JSON API와 컨트롤러 파일 자체가 분리되어 있음(`views.py` / `api.py` 혼용 금지).

| Method | Path | 템플릿 | 설명 |
|---|---|---|---|
| GET | `/` | `index.html` | 메인 — 카메라 3대 스트리밍 + 사이드바(모드 토글, 최근 이벤트) + 통계 |
| GET | `/events` | `events_list.html` | 이벤트 목록 |
| GET | `/events/{id}` | `event_detail.html` | 이벤트 상세 |
| GET | `/statistics` | `statistics.html` | 통계 대시보드 |

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
