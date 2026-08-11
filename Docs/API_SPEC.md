# API 명세서 — CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템

> **버전**: v0.1 MVP / In-memory Mock
> **기준일**: 2026-08-11
> **Base URL**: `http://localhost:8047`
> **배포 환경**: GPU 서버(L40S) 주소로 대체 예정
> **Swagger UI**: `http://localhost:8047/docs`
> **OpenAPI JSON**: `http://localhost:8047/openapi.json`
>
> 엔드포인트 경로와 응답 구조를 변경하거나 새로운 엔드포인트를 추가할 경우 CTO 검토 후 이 문서와 `.agentfiles/apiSpec.md`를 함께 수정한다. 두 문서는 동일한 EP-ID를 사용한다.

---

## 0. 현재 구현 범위

### 구현 완료

* 카메라 MJPEG 스트리밍 API
* 이벤트 생성 API
* 이벤트 목록 및 기간 조회 API
* 이벤트 상세 조회 API
* 클래스별 통계 조회 API
* 관리/수거 모드 전환 API
* WebSocket 연결 및 실시간 모드 변경 알림
* 관리 모드에서 오분류 이벤트 WebSocket 알림
* Jinja2 기반 모니터링, 이전기록, 통계 페이지
* 프론트엔드와 실제 API 연동
* 5초 중복 이벤트 방지 Cooldown
* 요청 스키마 및 Enum 검증
* 이벤트 미존재 시 HTTP 404 처리

### 현재 Mock 또는 미구현

* 이벤트 저장소는 In-memory Mock
* 서버 재시작 시 생성된 이벤트와 모드 상태 초기화
* MongoDB 및 GridFS 연동 미구현
* 실제 RPA 전구·경고음 장치 연동 미구현
* AI 탐지 모델 연동 미구현
* `overflow` 이벤트 미구현
* 카메라 연결 해제 및 시스템 오류 WebSocket 이벤트 미구현
* 이벤트 상세 페이지 미구현
* 인증 및 권한 미구현

---

## 탐지 파이프라인 개요 — 향후 구현 예정

> 아래 파이프라인은 설계가 진행 중인 향후 구현 범위이며, 현재 v0.1 Mock API에는 AI 탐지 모델이 연결되어 있지 않다.

* **상시 감시 모델**

  * YOLOv8-Nano 사용 예정
  * ROI 내부 손과 쓰레기 객체 분석
  * 손과 쓰레기가 함께 감지되면 투기 이벤트 후보로 판단
  * 쓰레기만 감지되면 넘침 이벤트 후보로 판단

* **정밀 분석 모델**

  * 투기 이벤트 후보 발생 시 실행
  * 고화질 영상 녹화 및 정밀 클래스 분류
  * 적용 모델과 녹화 시간은 아키텍처 문서를 기준으로 확정

* **처리 위치**

  * 탐지 및 정밀 분석은 중앙 GPU 서버에서 처리 예정
  * 젯슨 나노는 영상 캡처, RTSP 송신 및 GPIO 알림 수신 담당 예정

자세한 설계는 `.agentfiles/architecture.md`를 참고한다.

---

## 공통 사항

* **데이터 포맷**: JSON
* **JSON 필드명**: camelCase
* **API 함수 및 변수명**: camelCase
* **WebSocket `eventType` 값**: 대문자 스네이크케이스
* **문자 인코딩**: UTF-8
* **시간 형식**: ISO 8601
* **인증**: 없음
* **CORS**: 프론트엔드와 백엔드가 같은 Origin이므로 현재 미사용
* **스키마 검증**: FastAPI/Pydantic 사용
* **기본 에러 형식**: `{"detail": "..."}`
* **잘못된 Body, Query, Path Enum**: HTTP 422

---

## 공통 Enum

### 현재 구현된 Enum

| Enum            | 허용 값                                                                      |
| --------------- | ------------------------------------------------------------------------- |
| `CameraId`      | `ELEV-01` | `ELEV-02` | `REST-4F-01`                                      |
| `DetectedClass` | `general` | `paper` | `plastic` | `coffeeCup` | `mixed` | `uncertain`     |
| `ActionTaken`   | `lightAndSound` | `soundOnly` | `lightOnly` | `notificationOnly` | `none` |
| `Mode`          | `MANAGE` | `COLLECT`                                                      |

### 기본값 및 의미

| 항목              | 설명                                                           |
| --------------- | ------------------------------------------------------------ |
| 기본 Mode         | 서버 시작 시 `MANAGE`                                             |
| `MANAGE`        | 오분류 이벤트 저장, `actionTaken=lightAndSound`, WebSocket 오분류 알림 전송 |
| `COLLECT`       | 오분류 이벤트 저장, `actionTaken=none`, WebSocket 오분류 알림 미전송         |
| `lightAndSound` | 현재 실제 하드웨어 작동이 아니라 처리 결과를 나타내는 Mock 값                        |
| `none`          | 별도의 경고 동작을 수행하지 않음                                           |

### 향후 추가 예정 Enum

| Enum            | 예정 값                                                             | 현재 상태        |
| --------------- | ---------------------------------------------------------------- | ------------ |
| `EventCategory` | `misclassification` | `overflow`                                 | 미구현          |
| `CameraStatus`  | `ONLINE` | `OFFLINE`                                             | API 응답에서 미사용 |
| `WSEventType`   | `BIN_OVERFLOW_DETECTED` | `CAMERA_DISCONNECTED` | `SYSTEM_ERROR` | 미구현          |

---

# 1. JSON API (`controllers/api.py`)

## EP-01. `GET /api/stream/{cameraId}`

카메라 영상을 MJPEG 스트림으로 반환한다.

### 요청

| 구분    | 이름         | 타입       | 필수 | 설명                         |
| ----- | ---------- | -------- | -- | -------------------------- |
| Path  | `cameraId` | CameraId | ✅  | 카메라 위치 ID                  |
| Query | `role`     | string   | ❌  | `top` 또는 `side`, 기본값 `top` |

### 요청 예시

```http
GET /api/stream/ELEV-01?role=top
```

```http
GET /api/stream/ELEV-01?role=side
```

### 정상 응답

* **상태 코드**: HTTP 200
* **Content-Type**:

```text
multipart/x-mixed-replace; boundary=frame
```

### 에러 응답

| 상태 코드 | 발생 조건                           |
| ----- | ------------------------------- |
| 422   | `cameraId` 또는 `role`이 허용된 값과 다름 |
| 503   | 카메라가 설정되지 않았거나 연결할 수 없음         |

### 현재 구현 참고사항

* `cameraId`는 `CameraId` Enum으로 검증한다.
* `role`에 따라 `top` 또는 `side` 카메라 관리자를 선택한다.
* 현재 개발용 카메라 소스는 환경 설정을 사용한다.
* `side` 카메라 소스가 설정되지 않은 경우 HTTP 503이 발생할 수 있다.
* 실제 CameraId별 독립 RTSP 소스 연결은 향후 확장 범위다.
* 스트리밍 구현은 CTO 담당 영역이며, 변경 시 사전 협의가 필요하다.

---

## EP-02. `POST /api/events`

오분류 판정 결과를 전달받아 이벤트를 생성한다.

현재 v0.1에서는 `misclassification` 이벤트만 지원한다. `overflow` 이벤트는 아직 요청 스키마에 포함되어 있지 않다.

### Request Body — `EventCreate`

| 필드                | 타입            | 필수 | 제약 조건             | 설명           |
| ----------------- | ------------- | -- | ----------------- | ------------ |
| `cameraId`        | CameraId      | ✅  | Enum 값            | 이벤트가 발생한 카메라 |
| `detectedClass`   | DetectedClass | ✅  | Enum 값            | 탐지된 쓰레기 클래스  |
| `isMisclassified` | boolean       | ✅  | `true` 또는 `false` | 오분류 여부       |
| `confidenceScore` | float         | ✅  | 0.0 이상 1.0 이하     | AI 판단 신뢰도    |

### 요청 예시

```json
{
  "cameraId": "ELEV-01",
  "detectedClass": "mixed",
  "isMisclassified": true,
  "confidenceScore": 0.85
}
```

### curl 예시

```bash
curl -X POST "http://localhost:8047/api/events" \
  -H "Content-Type: application/json" \
  -d "{\"cameraId\":\"ELEV-01\",\"detectedClass\":\"mixed\",\"isMisclassified\":true,\"confidenceScore\":0.85}"
```

### 이벤트가 생성되는 경우

* `isMisclassified`가 `true`
* 동일한 `cameraId`와 `detectedClass` 조합으로 생성된 직전 이벤트로부터 5초 이상 경과

### 이벤트가 생성되지 않는 경우

다음 조건에서는 HTTP 200과 함께 `null`을 반환한다.

* `isMisclassified=false`
* 동일한 `cameraId`와 `detectedClass` 조합의 5초 Cooldown이 적용 중

### 정상 응답 — `Event`

```json
{
  "eventId": "a3b70dae-3a1b-48b6-a8d1-a06afcb934d1",
  "timestamp": "2026-08-11T06:47:50.261977Z",
  "cameraId": "ELEV-01",
  "detectedClass": "mixed",
  "isMisclassified": true,
  "confidenceScore": 0.85,
  "actionTaken": "lightAndSound",
  "imageFileId": null,
  "notes": null
}
```

### Response 필드

| 필드                | 타입                | null 허용 | 설명                                     |
| ----------------- | ----------------- | ------- | -------------------------------------- |
| `eventId`         | string            | ❌       | 생성 이벤트는 UUID, 초기 Mock 이벤트는 고정 ID 사용 가능 |
| `timestamp`       | ISO 8601 datetime | ❌       | 서버의 UTC 기준 이벤트 생성 시각                   |
| `cameraId`        | CameraId          | ❌       | 카메라 ID                                 |
| `detectedClass`   | DetectedClass     | ❌       | 탐지 클래스                                 |
| `isMisclassified` | boolean           | ❌       | 오분류 여부                                 |
| `confidenceScore` | float             | ❌       | 신뢰도                                    |
| `actionTaken`     | ActionTaken       | ❌       | 모드에 따른 경고 처리 결과                        |
| `imageFileId`     | string            | ✅       | 향후 GridFS 파일 ID, 현재 `null`             |
| `notes`           | string            | ✅       | 추가 설명, 현재 생성 이벤트는 `null`               |

### 모드별 처리

| 현재 Mode   | 이벤트 저장 | `actionTaken`   | WebSocket 오분류 알림 |
| --------- | ------ | --------------- | ---------------- |
| `MANAGE`  | 저장     | `lightAndSound` | 전송               |
| `COLLECT` | 저장     | `none`          | 전송하지 않음          |

> 현재 `lightAndSound`는 실제 RPA 장치 작동 결과가 아니라 Mock 응답 값이다.

### 부수 효과

`MANAGE` 모드에서 이벤트가 실제로 생성되면 연결된 WebSocket 클라이언트에 다음 메시지를 전송한다.

```json
{
  "eventType": "MISCLASSIFICATION_DETECTED",
  "cameraId": "ELEV-01",
  "timestamp": "2026-08-11T06:47:50.261977+00:00",
  "isMisclassified": true
}
```

### 상태 코드

| 상태 코드 | 설명                                    |
| ----- | ------------------------------------- |
| 200   | 이벤트 생성 또는 `null` 반환                   |
| 422   | 필수 필드 누락, Enum 오류, 타입 오류 또는 신뢰도 범위 오류 |
| 500   | 서버 내부 처리 오류                           |

---

## EP-03. `GET /api/events`

저장된 이벤트 목록을 최신순으로 조회한다.

### Query Parameter

| 이름     | 타입                | 필수 | 설명                 |
| ------ | ----------------- | -- | ------------------ |
| `from` | ISO 8601 datetime | ❌  | 조회 시작 시각, 해당 시각 포함 |
| `to`   | ISO 8601 datetime | ❌  | 조회 종료 시각, 해당 시각 포함 |

> Python 내부 변수명은 `fromDate`, `toDate`지만 실제 API Query 이름은 각각 `from`, `to`이다.

### 전체 조회 예시

```http
GET /api/events
```

### 기간 조회 예시

```http
GET /api/events?from=2026-08-11T00:00:00Z&to=2026-08-11T23:59:59Z
```

### 정상 응답

```json
[
  {
    "eventId": "a3b70dae-3a1b-48b6-a8d1-a06afcb934d1",
    "timestamp": "2026-08-11T06:47:50.261977Z",
    "cameraId": "REST-4F-01",
    "detectedClass": "coffeeCup",
    "isMisclassified": true,
    "confidenceScore": 0.83,
    "actionTaken": "lightAndSound",
    "imageFileId": null,
    "notes": null
  }
]
```

### 동작

* `timestamp` 기준 내림차순으로 반환한다.
* 조건에 해당하는 이벤트가 없으면 빈 배열을 반환한다.

```json
[]
```

### 현재 저장 방식

* In-memory 리스트에 저장한다.
* 서버 시작 시 Mock 이벤트 2건이 생성된다.
* API로 생성한 이벤트는 실행 중인 서버 메모리에 추가된다.
* 서버를 다시 시작하면 API로 생성한 이벤트는 사라진다.
* 현재 페이지네이션은 지원하지 않는다.

### 상태 코드

| 상태 코드 | 설명          |
| ----- | ----------- |
| 200   | 정상 조회       |
| 422   | 날짜 형식 오류    |
| 500   | 서버 내부 처리 오류 |

---

## EP-04. `GET /api/events/{id}`

`eventId`로 이벤트 한 건을 조회한다.

### Path Parameter

| 이름   | 타입     | 필수 | 설명            |
| ---- | ------ | -- | ------------- |
| `id` | string | ✅  | 조회할 `eventId` |

### 요청 예시

```http
GET /api/events/event-001
```

### 정상 응답

```json
{
  "eventId": "event-001",
  "timestamp": "2026-08-11T01:05:53.810490Z",
  "cameraId": "ELEV-01",
  "detectedClass": "plastic",
  "isMisclassified": true,
  "confidenceScore": 0.91,
  "actionTaken": "lightAndSound",
  "imageFileId": null,
  "notes": "플라스틱 오분류 Mock 이벤트"
}
```

### 이벤트가 없는 경우

* **상태 코드**: HTTP 404

```json
{
  "detail": "이벤트를 찾을 수 없습니다."
}
```

### 상태 코드

| 상태 코드 | 설명             |
| ----- | -------------- |
| 200   | 이벤트 조회 성공      |
| 404   | 해당 ID의 이벤트가 없음 |
| 500   | 서버 내부 처리 오류    |

---

## EP-05. `GET /api/statistics`

조회 시점에 이벤트 저장소를 집계해 탐지 클래스별 이벤트 수를 반환한다.

### Query Parameter

| 이름     | 타입                | 필수 | 설명       |
| ------ | ----------------- | -- | -------- |
| `from` | ISO 8601 datetime | ❌  | 통계 시작 시각 |
| `to`   | ISO 8601 datetime | ❌  | 통계 종료 시각 |

### 요청 예시

```http
GET /api/statistics
```

```http
GET /api/statistics?from=2026-08-11T00:00:00Z&to=2026-08-11T23:59:59Z
```

### 정상 응답 — `Statistics`

```json
{
  "labels": [
    "general",
    "paper",
    "plastic",
    "coffeeCup",
    "mixed",
    "uncertain"
  ],
  "counts": [
    0,
    1,
    1,
    0,
    0,
    0
  ]
}
```

### Response 필드

| 필드       | 타입              | 설명                      |
| -------- | --------------- | ----------------------- |
| `labels` | DetectedClass[] | 지원하는 탐지 클래스 전체 목록       |
| `counts` | integer[]       | 같은 인덱스의 클래스에 해당하는 이벤트 수 |

### 인덱스 대응

| `labels` 값  | 화면 표시      |
| ----------- | ---------- |
| `general`   | 일반 쓰레기     |
| `paper`     | 종이         |
| `plastic`   | 플라스틱, 병, 캔 |
| `coffeeCup` | 커피 컵       |
| `mixed`     | 복합재질       |
| `uncertain` | 분류 불확실     |

### 동작

* 캐시 없이 호출 시점마다 이벤트 저장소를 집계한다.
* 모든 클래스가 항상 `labels`에 포함된다.
* 이벤트가 없는 클래스는 `counts` 값으로 `0`을 반환한다.
* `from`, `to`가 있으면 해당 기간의 이벤트만 집계한다.
* 현재 `overflow` 이벤트는 구현되지 않았으므로 통계에 포함되지 않는다.

### 상태 코드

| 상태 코드 | 설명          |
| ----- | ----------- |
| 200   | 정상 집계       |
| 422   | 날짜 형식 오류    |
| 500   | 서버 내부 처리 오류 |

---

## EP-06. `POST /api/mode`

서버의 관리/수거 모드를 변경한다.

### Request Body — `ModeUpdate`

```json
{
  "mode": "MANAGE"
}
```

### 허용 값

| 값         | 설명    |
| --------- | ----- |
| `MANAGE`  | 관리 모드 |
| `COLLECT` | 수거 모드 |

### 정상 응답 — `ModeResponse`

```json
{
  "mode": "MANAGE"
}
```

### 부수 효과

모드 변경이 성공하면 연결된 모든 WebSocket 클라이언트에 다음 메시지를 전송한다.

```json
{
  "eventType": "MODE_CHANGED",
  "mode": "MANAGE",
  "timestamp": "2026-08-11T05:30:23.192897+00:00"
}
```

### 잘못된 값 요청 예시

```json
{
  "mode": "INVALID"
}
```

### 잘못된 값 응답

* **상태 코드**: HTTP 422

```json
{
  "detail": [
    {
      "type": "enum",
      "loc": [
        "body",
        "mode"
      ],
      "msg": "Input should be 'MANAGE' or 'COLLECT'",
      "input": "INVALID"
    }
  ]
}
```

### 현재 상태 저장 방식

* 모드는 서버 메모리에 저장한다.
* 서버가 실행되는 동안에는 페이지 이동 후에도 같은 서버 모드를 사용할 수 있다.
* 서버가 재시작되면 기본값 `MANAGE`로 초기화된다.
* 영구 저장은 아직 구현되지 않았다.

### 상태 코드

| 상태 코드 | 설명                       |
| ----- | ------------------------ |
| 200   | 모드 변경 성공                 |
| 422   | 허용되지 않은 Mode 또는 요청 형식 오류 |
| 500   | 서버 내부 처리 오류              |

---

## EP-07. `WS /ws/events`

관리자 웹 클라이언트가 실시간 모드 변경 및 오분류 이벤트를 수신하는 WebSocket 엔드포인트다.

### 연결 주소

```text
ws://localhost:8047/ws/events
```

HTTPS 배포 환경에서는 다음 형식을 사용한다.

```text
wss://서버주소/ws/events
```

### 연결 직후 동작

클라이언트 연결이 승인되면 서버는 현재 모드를 담은 `MODE_CHANGED` 메시지를 즉시 한 번 전송한다.

```json
{
  "eventType": "MODE_CHANGED",
  "mode": "MANAGE",
  "timestamp": "2026-08-11T04:03:45.610103+00:00"
}
```

### 현재 구현된 WebSocket 메시지

| `eventType`                  | Payload 필드                                 | 발생 조건                            |
| ---------------------------- | ------------------------------------------ | -------------------------------- |
| `MODE_CHANGED`               | `mode`, `timestamp`                        | 연결 직후 1회 또는 모드 변경 성공 시           |
| `MISCLASSIFICATION_DETECTED` | `cameraId`, `timestamp`, `isMisclassified` | `MANAGE` 모드에서 오분류 이벤트가 실제 생성됐을 때 |

### `MODE_CHANGED` 예시

```json
{
  "eventType": "MODE_CHANGED",
  "mode": "COLLECT",
  "timestamp": "2026-08-11T05:30:23.192897+00:00"
}
```

### `MISCLASSIFICATION_DETECTED` 예시

```json
{
  "eventType": "MISCLASSIFICATION_DETECTED",
  "cameraId": "ELEV-01",
  "timestamp": "2026-08-11T05:25:28.109933+00:00",
  "isMisclassified": true
}
```

### 모드별 WebSocket 동작

| Mode      | 이벤트 저장 | 오분류 WebSocket 전송 |
| --------- | ------ | ---------------- |
| `MANAGE`  | 저장     | 전송               |
| `COLLECT` | 저장     | 전송하지 않음          |

### 향후 구현 예정 메시지

| `eventType`             | 예정 Payload              | 현재 상태                   |
| ----------------------- | ----------------------- | ----------------------- |
| `BIN_OVERFLOW_DETECTED` | `cameraId`, `timestamp` | `overflow` 기능과 함께 구현 예정 |
| `CAMERA_DISCONNECTED`   | `cameraId`, `timestamp` | 카메라 연결 감시 구현 후 추가 예정    |
| `SYSTEM_ERROR`          | `message`, `timestamp`  | 서버 오류 알림 정책 확정 후 추가 예정  |

> `eventType` 값은 대문자 스네이크케이스를 사용한다. JSON Payload 필드명은 camelCase를 사용한다.

---

# 2. 페이지 라우트 (`controllers/views.py`)

페이지 라우트는 JSON이 아닌 Jinja2 `TemplateResponse`를 반환한다.

JSON API는 `controllers/api.py`, 페이지 라우트는 `controllers/views.py`에서 관리한다.

| ID    | Method | Path          | 템플릿               | 설명             |
| ----- | ------ | ------------- | ----------------- | -------------- |
| PG-01 | GET    | `/`           | `index.html`      | 카메라 모니터링 메인 화면 |
| PG-02 | GET    | `/events`     | `eventsList.html` | 이벤트 이전기록 화면    |
| PG-03 | GET    | `/statistics` | `statistics.html` | 클래스별 통계 대시보드   |

## PG-01. `GET /`

메인 모니터링 페이지를 반환한다.

### 주요 기능

* Jinja2 Context로 `cameraId` 전달
* `top`, `side` 카메라 스트림 표시
* 사이드바 메뉴
* 관리/수거 모드 표시
* WebSocket 연결
* 오분류 이벤트 경고 표시

### 사용하는 API

```text
GET /api/stream/{cameraId}?role=top
GET /api/stream/{cameraId}?role=side
POST /api/mode
WS /ws/events
```

---

## PG-02. `GET /events`

이벤트 이전기록 페이지를 반환한다.

### 주요 기능

* 실제 `GET /api/events` 결과 표시
* 이벤트 총 개수
* 오늘 이벤트 개수
* 평균 신뢰도
* 날짜, 클래스, 결과 및 알림 상태 필터
* 테이블 정렬
* 페이지네이션
* 행 선택 시 상세 모달
* 새 이벤트 생성 후 새로고침하면 목록에 반영

### 사용하는 API

```text
GET /api/events
POST /api/mode
WS /ws/events
```

---

## PG-03. `GET /statistics`

통계 대시보드 페이지를 반환한다.

### 주요 기능

* 클래스별 이벤트 수 표시
* 전체 이벤트 수 표시
* 오분류 이벤트 수 표시
* 최근 이벤트 목록 표시
* 실제 API 데이터 사용

### 사용하는 API

```text
GET /api/statistics
GET /api/events
POST /api/mode
WS /ws/events
```

---

## 공통 Partial

`sidebar.html`은 독립 페이지가 아니라 다음 페이지에 포함되는 공통 Jinja2 Partial이다.

```jinja2
{% include "sidebar.html" %}
```

### 주요 기능

* 페이지 이동
* 현재 메뉴 활성화
* 관리/수거 모드 버튼
* 모드 상태 표시
* `POST /api/mode` 연동
* `MODE_CHANGED` WebSocket 메시지 반영

---

## 현재 존재하지 않는 페이지 라우트

| Path           | 상태                |
| -------------- | ----------------- |
| `/events/{id}` | 이벤트 상세 전용 페이지 미구현 |

이벤트 상세 정보는 현재 `/events` 페이지의 모달과 `GET /api/events/{id}` API를 통해 확인한다.

---

# 3. 상태 코드 요약

| 상태 코드 | 상황                                      |
| ----- | --------------------------------------- |
| 200   | 정상 처리                                   |
| 404   | 해당 이벤트를 찾을 수 없음                         |
| 422   | Body, Query 또는 Path Parameter 스키마 검증 실패 |
| 500   | 서버 내부 처리 오류                             |
| 503   | 카메라 미설정 또는 카메라 연결 실패                    |

## HTTP 404 예시

```json
{
  "detail": "이벤트를 찾을 수 없습니다."
}
```

## HTTP 422 예시

```json
{
  "detail": [
    {
      "type": "enum",
      "loc": [
        "body",
        "mode"
      ],
      "msg": "Input should be 'MANAGE' or 'COLLECT'",
      "input": "INVALID"
    }
  ]
}
```

---

# 4. 저장소 및 상태 관리

## 이벤트 저장소

현재 `repositories/eventRepository.py`는 In-memory Mock 저장소다.

| 항목     | 현재 동작                  |
| ------ | ---------------------- |
| 저장 방식  | Python 리스트             |
| 초기 데이터 | Mock 이벤트 2건            |
| 생성 이벤트 | 실행 중인 서버 메모리에 추가       |
| 서버 재시작 | 생성 이벤트 초기화             |
| 정렬     | `timestamp` 최신순        |
| 상세 조회  | `eventId` 일치 검색        |
| 기간 조회  | `from`, `to` 기준 필터     |
| 통계     | `DetectedClass`별 개수 집계 |

## 모드 상태

현재 `services/modeService.py`에서 메모리로 관리한다.

| 항목     | 현재 동작                    |
| ------ | ------------------------ |
| 기본값    | `MANAGE`                 |
| 변경     | `POST /api/mode`         |
| 실시간 전파 | WebSocket `MODE_CHANGED` |
| 서버 재시작 | `MANAGE`로 초기화            |
| DB 저장  | 미구현                      |

---

# 5. 향후 구현 예정 API 변경 사항

> 아래 내용은 현재 API에 구현되어 있지 않다. 구현 전에 스키마와 응답 호환성을 CTO와 협의해야 한다.

## 5-1. 이벤트 카테고리

향후 `EventCreate`와 `Event`에 다음 필드를 추가할 수 있다.

```json
{
  "eventCategory": "misclassification"
}
```

예정 값:

```text
misclassification
overflow
```

### 예정 의미

| 값                   | 설명                |
| ------------------- | ----------------- |
| `misclassification` | 투기 또는 오분류 이벤트     |
| `overflow`          | 쓰레기통 포화 또는 넘침 이벤트 |

---

## 5-2. Overflow 이벤트

예정 요청 예시:

```json
{
  "cameraId": "ELEV-01",
  "eventCategory": "overflow"
}
```

예정 WebSocket 메시지:

```json
{
  "eventType": "BIN_OVERFLOW_DETECTED",
  "cameraId": "ELEV-01",
  "timestamp": "2026-08-11T06:47:50.261977+00:00"
}
```

다음 사항은 아직 확정되지 않았다.

* Overflow Cooldown 시간
* Overflow 이벤트의 `actionTaken`
* Overflow 이벤트의 RPA 처리 방식
* Overflow 통계 응답 구조
* 영상 녹화 파일 저장 위치
* 기존 Event 스키마 필드의 null 허용 범위

---

## 5-3. MongoDB 및 GridFS

향후 In-memory 저장소를 Motor 기반 MongoDB 저장소로 교체할 예정이다.

| 항목           | 예정 내용                       |
| ------------ | --------------------------- |
| MongoDB 이미지  | `mongo:7.0`                 |
| 로컬 Host Port | `27020`                     |
| 컨테이너 Port    | `27017`                     |
| Python 드라이버  | `motor`                     |
| 파일 저장        | GridFS 또는 GPU 서버 로컬 디스크 검토  |
| 저장 대상        | 이벤트, 모드 상태, 이미지 또는 영상 메타데이터 |

MongoDB 연결 후에도 외부 JSON API 필드명은 camelCase를 유지한다.

---

## 5-4. 실제 RPA 연동

현재 `actionTaken`은 Mock 결과 값이다.

향후 다음 기능을 구현할 예정이다.

* 전구 점등
* 경고음 출력
* 알림만 전송
* 젯슨 나노 GPIO 트리거
* RPA 실패 상태 기록
* 장치 연결 상태 확인

신호 전달 방식은 다음 후보 중에서 결정한다.

* HTTP
* WebSocket
* MQTT

---

# 6. TBD — 팀 논의 필요

* `MISCLASSIFICATION_DETECTED` Payload에 `detectedClass`를 추가할지 여부
* WebSocket 메시지에 `eventId`와 `actionTaken`을 포함할지 여부
* 이벤트 목록 페이지네이션 방식

  * `limit`/`offset`
  * `page`/`pageSize`
  * Cursor 방식
* 통계 API에 전체 건수와 오분류 건수를 함께 포함할지 여부
* 통계 API에서 `overflow`를 별도 집계할지 여부
* `overflow` Cooldown 기준
* `EventCategory` 적용 시 기존 Event 응답 호환 방식
* 카메라 상태 조회 API 추가 여부
* 모드 조회용 `GET /api/mode` 추가 여부
* 실제 RPA 통신 방식
* 인증 및 권한
* 이벤트 상세 페이지 구현 여부
* 이미지와 영상의 GridFS 저장 여부
* AI 탐지 신뢰도 Threshold
* 정상 분류 이벤트도 저장할지 여부
* CameraId별 `top`/`side` 영상 소스 매핑 방식

---

# 7. 구현 상태 체크표

| ID      | 기능                    | 현재 상태           |
| ------- | --------------------- | --------------- |
| EP-01   | 카메라 MJPEG 스트리밍        | 구현됨 — CTO 담당 영역 |
| EP-02   | 오분류 이벤트 생성            | 구현됨             |
| EP-03   | 이벤트 목록 및 기간 조회        | 구현됨             |
| EP-04   | 이벤트 상세 및 404 처리       | 구현됨             |
| EP-05   | 클래스별 통계 조회            | 구현됨             |
| EP-06   | 관리/수거 모드 전환           | 구현됨             |
| EP-07   | WebSocket 모드 및 오분류 알림 | 구현됨             |
| PG-01   | 모니터링 페이지              | 구현됨             |
| PG-02   | 이전기록 페이지              | 구현됨             |
| PG-03   | 통계 대시보드               | 구현됨             |
| DB-01   | MongoDB 이벤트 저장        | 미구현             |
| DB-02   | GridFS 이미지·영상 저장      | 미구현             |
| AI-01   | YOLO 탐지 연동            | 미구현             |
| EVT-01  | Overflow 이벤트          | 미구현             |
| RPA-01  | 실제 전구·경고음 연동          | 미구현             |
| AUTH-01 | 인증 및 권한               | 미구현             |

---

# 8. 변경 관리 규칙

* 새로운 엔드포인트에는 반드시 새로운 EP-ID를 부여한다.
* 기존 엔드포인트 Path는 임의로 변경하지 않는다.
* JSON 필드는 camelCase를 사용한다.
* WebSocket `eventType`만 대문자 스네이크케이스를 허용한다.
* Enum 값을 추가하기 전에 이 문서를 먼저 수정한다.
* API를 변경하면 다음 문서를 함께 최신화한다.

  * Notion API 명세서
  * `.agentfiles/apiSpec.md`
  * 필요한 경우 `.agentfiles/architecture.md`
* API 변경 후 `/docs`에서 실제 요청과 응답을 검증한다.
* Git 작업 전 최신 `dev`와 루트 `README.md`를 확인한다.
* `git pull` 후 `python ..\..\infra\checkEnv.py`를 실행한다.
* 스트리밍 관련 변경은 CTO 담당 영역이므로 사전 협의한다.
