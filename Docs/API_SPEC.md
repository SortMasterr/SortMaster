# API 명세서 — CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템

> **버전**: v0.2 MVP / 클래스 명명 계약 변경(CTO 검토 필요)
> **기준일**: 2026-08-25
> **Base URL**: `http://localhost:8047`
> **배포 환경**: 로컬 배포 서버 `<LOCAL_BACKEND_IP>:8047`(실제 IP는 Notion 참고)로 대체 예정(백엔드는 GPU 서버가 아니라
> 로컬에서 구동 — `.agentfiles/architecture.md` 참고)
> **Swagger UI**: `http://localhost:8047/docs`
> **OpenAPI JSON**: `http://localhost:8047/openapi.json`
>
> 엔드포인트 경로와 응답 구조를 변경하거나 새로운 엔드포인트를 추가할 경우 CTO 검토 후 이 문서와 `.agentfiles/apiSpec.md`를 함께 수정한다. 두 문서는 동일한 EP-ID를 사용한다.
> v0.2에서는 `DetectedClass`/`BinType`의 `general`→`normal`, `plasticCan`→`recyclables` 변경을 코드와 문서에 반영했다. 새로 저장되는 값과 API 응답은 새 이름만 사용하며, 기존 MongoDB 문서는 읽을 때 새 값으로 변환한다.

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
* 통계 대시보드 자동 보고서 수신 이메일 설정 API 및 별도 일일·주간 스케줄러
* 5초 중복 이벤트 방지 Cooldown
* 요청 스키마 및 Enum 검증
* 이벤트 미존재 시 HTTP 404 처리
* MongoDB(motor) 연동 — 이벤트 저장소가 In-memory Mock에서 완전히 전환됨
* `overflow` 이벤트(스키마·저장·별도 통계·WS `BIN_OVERFLOW_DETECTED` 포함) 구현
* 이벤트 트리거 녹화 → GIF 인코딩 → GridFS 업로드 파이프라인(`recordingService`/
  `mediaService`/`mediaRepository`) — 실제 탐지 서비스가 아직 없어 `debug/detection/
  simulateEventPipeline.py`로 시작/종료 신호를 흉내내 검증
* `BIN_STATES` 스키마·저장소·상태 갱신/조회 API(EP-10/EP-11) — `binId`당 최신 상태 1행을
  upsert로 유지하고, `NORMAL`→`FULL` 전환 순간에만 overflow 이벤트를 생성한다
  (`schemas/binState.py`, `repositories/binStateRepository.py`, `services/binStateService.py`)

### 현재 Mock 또는 미구현

* 서버 재시작 시 모드 상태 초기화(이벤트는 이제 MongoDB에 영속화되어 재시작에도 유지됨)
* 실제 RPA 전구·경고음 장치 연동 미구현
* AI 탐지 모델 연동 — GPU 서버의 `models/trashdetect/tracking2.py`가 투척 완료를 자체
  판정해 `POST /api/events/aiDisposal`(EP-12)로 결과를 푸시하는 방식으로 **구현 완료**
  (데모 영상 기준 end-to-end 검증 성공). `bestTop.pt`가 쓰레기 `plastic`/`can`을
  `recyclables` 하나로 합친 4클래스(쓰레기만, 통은 미포함)인 건 재학습 대신 **API 계약을
  4종(plastic/can 통합)으로 바꾸는 쪽으로 CTO 승인**받아 해소(`decisionLog.md` 참고) —
  아래 `DetectedClass` 정의도 이에 맞춰 갱신됨. 통 위치는 모델이 아니라 **룰 베이스(고정
  ROI)**로 판정(SIDE의 `roi.json`과 같은 패턴, `tracking2.py`의 `RULE_BASED_BIN_ROIS`).
  `tracking2.py` 자체는 아직 데모 영상 대상 로컬 스크립트 상태라 실제 TOP RTSP 연결+상시
  서비스화는 TBD.
* 카메라 연결 해제 및 시스템 오류 WebSocket 이벤트 미구현
* 이벤트 상세 페이지 미구현
* `imageFileId`의 GridFS GIF를 내려받는 외부 API 미정의 — 새 API이므로 CTO 승인 필요
* 인증 및 권한 미구현
* EP-02/EP-09로 직접 만드는 overflow 이벤트는 여전히 `BIN_STATES` 전환 검증을 거치지 않는다
  (호출자가 유효한 스키마+새 `detectionId`만 보내면 바로 저장). 로컬 백엔드의 SIDE
  GPU 서버의 MobileNet_V3_Small 로직이 상태 전환 기준으로 overflow를 만들 때는 EP-11(`POST
  /api/binStates`)을 쓰는 쪽이 확정 설계와 일치한다 — EP-02/EP-09는 수동/디버그 경로로
  계속 남겨둔다.

---

## 탐지 파이프라인 개요 — 확정 설계와 현재 HTTP 연결부

> TOP은 GPU 서버의 `models/trashdetect/tracking2.py`가 실제로 판정+`POST
> /api/events/aiDisposal`(EP-12) 푸시까지 구현 완료됐고, 실제 TOP MJPEG 스트림(로컬 백엔드
> 중계) 기준 end-to-end 연결도 검증됨(2026-08-25) — 상시 서비스화(systemd/Docker)만 아직
> TBD. SIDE(MobileNet_V3_Small, `feature/side-overflow-integration` 브랜치 — `dev`에 merge
> 완료)/EP-08~EP-11은 이미 실사용 경로다.

* **탐지 모델**

  * TOP: YOLO26 사용(변경 전 YOLOv8-Nano), **GPU 서버의 `models/trashdetect/tracking2.py`가
    TOP 영상을 직접 보며 상시 추론** — 메인보드가 Jetson Orin Nano Super에서 라즈베리파이로
    바뀌면서 라즈베리파이(엣지)는 캡처+RTSP 송신+GPIO/스피커만 담당, 추론은 GPU 서버로
    이관됨(아래 "처리 위치" 참고)
  * SIDE: **MobileNet_V3_Small** 경량 분류 모델 — **TOP과 완전히 동일한 구조**로 GPU
    서버의 `models/trashoverflow/sideOverflow.py`가 자체 추론+판정
    (`WebApps/backend/models/trashoverflow/` — 룰 베이스 → 로컬 백엔드 CPU 추론(GPU
    미사용) → 지금의 GPU 서버 방식까지 두 번 재전환됨, 마지막 전환은 TOP과의 아키텍처
    일관성이 이유. `decisionLog.md` 참고. 실제 GPU 서버 배포/실행+end-to-end 검증
    완료(2026-08-25))
  * 손 감지 조건 폐지 — 쓰레기 감지 자체가 트리거
  * 옆 카메라(SIDE, MobileNet_V3_Small)가 넘침 상태와 대상 물리 통(`binId`)을 감지 → 위
    카메라 연동 없이 바로 알림+DB 저장
  * 위 카메라(TOP): `tracking2.py`가 쓰레기 감지+추적+종류 분류+정상/오분류 판정까지
    프레임 단위로 자체 수행 → 투척 완료 시 최종 판정 결과를 **직접** 백엔드로 푸시(EP-12)
    → 백엔드는 재판정 없이 그대로 저장(상세는 `.agentfiles/architecture.md`의 "탐지
    파이프라인" 참고). SIDE(`sideOverflow.py`)도 동일하게 `POST /api/binStates`(EP-11)로
    직접 푸시

> `EventCreate`/`Event`에 `detectionId`, `trackingId`, `binId`, `binType`, `modelVersion`,
> overflow 전용 필드가 반영되었다. `detectionId`는 MongoDB 유니크 인덱스로 중복 저장을
> 방지한다. `BIN_STATES` 컬렉션과 상태 갱신/조회 API(EP-10/EP-11)는 구현 완료됐다 — 아래
> "5-2. Overflow 이벤트 및 녹화 파이프라인"과 EP-10/EP-11 참고.

* **LLM(Qwen3-VL-8B) — 실시간 탐지 경로엔 없음**

  * 실시간 탐지(TOP/SIDE 둘 다)엔 안 씀 — TOP은 YOLO26이, SIDE는 MobileNet_V3_Small이 전담
  * 학습 준비 단계 용도로 사용: ①**자동 라벨링 검증(진행 중)** — 전처리+자동 라벨링 도구가
    만든 1차 라벨 중 불확실한 것만 LLM이 검증/보정(베이스 모델+프롬프트, 파인튜닝은 미착수)
    ②환경별 통 모양 인식 학습 데이터 생성(아직 미착수)(`.agentfiles/architecture.md`의
    "LLM 활용" 참고)

* **처리 위치**

  * GPU 서버의 `tracking2.py`가 TOP의 탐지·추적·분류·최종 판정을, `sideOverflow.py`가
    SIDE의 넘침 판정을 각각 전부 자체 수행하고 결과를 로컬 백엔드로 푸시(TOP은 EP-12,
    SIDE는 EP-11) — 백엔드는 저장만 함. GPU 서버는 YOLO26 학습(`training`)+LLM 자동
    라벨링 검증(`llm`)도 같이 담당
  * 백엔드+DB는 로컬(`<LOCAL_BACKEND_IP>`, 실제 값은 Notion 참고)에서 구동, GPU 서버가 아님
  * 라즈베리파이는 영상 캡처, RTSP 송신, GPIO/스피커 알림 출력만 담당(추론 없음) — TOP/SIDE
    추론 둘 다 GPU 서버(`tracking2.py`/`sideOverflow.py`)가 전담

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
| `CameraId`      | `ELEV-TOP` | `ELEV-SIDE` | `REST-4F-01` — 설치 위치가 12층 엘리베이터 앞 1곳뿐이라 번호 불필요(`.agentfiles/architecture.md` 참고). `ELEV-TOP`=YOLO26(쓰레기 4종 분류+추적)+룰 베이스(통 위치, 고정 ROI) 조합, `ELEV-SIDE`=MobileNet_V3_Small(쓰레기통 넘침 여부, GPU 서버 추론 — TOP과 동일 구조) |
| `EventCategory` | `misclassification` | `overflow`                                       |
| `DetectedClass` | `normal` \| `paper` \| `recyclables` \| `coffeeCup` — `BinType`과 값 체계 1:1 |
| `BinType`       | `normal` \| `recyclables` \| `coffeeCup` \| `paper` |
| `ActionTaken`   | `lightAndSound` | `soundOnly` | `lightOnly` | `notificationOnly` | `none` |
| `Mode`          | `MANAGE` | `COLLECT`                                                      |

### 기본값 및 의미

| 항목              | 설명                                                           |
| --------------- | ------------------------------------------------------------ |
| 기본 Mode         | 서버 시작 시 `MANAGE`                                             |
| `MANAGE`        | 이벤트 저장, `actionTaken=lightAndSound`, 카테고리별 WebSocket 알림 전송 |
| `COLLECT`       | 이벤트 저장, `actionTaken=none`, 이벤트 WebSocket 알림 미전송         |
| `lightAndSound` | 현재 실제 하드웨어 작동이 아니라 처리 결과를 나타내는 Mock 값                        |
| `none`          | 별도의 경고 동작을 수행하지 않음                                           |

### 향후 추가 예정 Enum

| Enum            | 예정 값                                                             | 현재 상태        |
| --------------- | ---------------------------------------------------------------- | ------------ |
| `CameraStatus`  | `ONLINE` | `OFFLINE`                                             | API 응답에서 미사용 |
| `WSEventType`   | `CAMERA_DISCONNECTED` | `SYSTEM_ERROR`                                | 미구현          |

> `EventCategory`, `WSEventType`의 `BIN_OVERFLOW_DETECTED`는 구현 완료 — 위 "허용 값" 표 및 EP-02 참고.

---

# 1. JSON API (`controllers/api.py`)

## EP-01. `GET /api/stream/{cameraId}`

카메라 영상을 MJPEG 스트림으로 반환한다.

### 요청

| 구분   | 이름         | 타입       | 필수 | 설명                                |
| ---- | ---------- | -------- | -- | --------------------------------- |
| Path | `cameraId` | CameraId | ✅  | 카메라 ID(카메라 1대 = 지점 1개 = CameraId 1개) |

### 요청 예시

```http
GET /api/stream/ELEV-TOP
```

```http
GET /api/stream/ELEV-SIDE
```

### 정상 응답

* **상태 코드**: HTTP 200
* **Content-Type**:

```text
multipart/x-mixed-replace; boundary=frame
```

### 에러 응답

| 상태 코드 | 발생 조건                  |
| ----- | ---------------------- |
| 422   | `cameraId`가 허용된 값과 다름  |
| 503   | 카메라가 설정되지 않았거나 연결할 수 없음 |

### 현재 구현 참고사항

* `cameraId`는 `CameraId` Enum으로 검증한다.
* `cameraId`마다 별도 카메라 관리자를 사용한다(카메라 1대당 독립 라즈베리파이 1대 구성).
* 현재 개발용 카메라 소스는 `.env`의 `CAMERA_SOURCE_<ID>`(예: `CAMERA_SOURCE_ELEVTOP`)를 사용한다.
* 소스가 설정되지 않은 `cameraId`는 HTTP 503이 발생할 수 있다.
* 소스 값으로 웹캠 번호와 RTSP URL을 모두 처리한다. 배포 시 CameraId별 RTSP URL을 `.env`에
  설정하며, 실제 장비 연결·운영 검증은 향후 범위다.

---

## EP-02. `POST /api/events`

판정 결과를 전달받아 이벤트를 생성한다. `eventCategory`로 `misclassification`(투기, 분류
정보 포함)/`overflow`(넘침, 분류 없이 감지만) 두 카테고리를 모두 지원한다.

녹화 파이프라인(`recordingService`/`mediaService`)이 이벤트 클립을 GIF로 인코딩해 GridFS에
올린 뒤, 그 파일 ID를 `imageFileId`로 함께 전달할 수 있다(선택 필드, 생략하면 `null`).
탐지 서비스가 아직 없어 지금은 `debug/detection/simulateEventPipeline.py`가 이 흐름
전체(녹화 시작/종료 → GIF → GridFS → 이 엔드포인트 호출과 동등한 내부 함수 호출)를 시뮬레이션한다.

### Request Body — `EventCreate`

| 필드                | 타입            | 필수                     | 제약 조건             | 설명                                  |
| ----------------- | ------------- | ---------------------- | ----------------- | ----------------------------------- |
| `cameraId`        | CameraId      | ✅                       | Enum 값            | 이벤트가 발생한 카메라                        |
| `eventCategory`   | EventCategory | ✅                       | Enum 값            | `misclassification` 또는 `overflow`   |
| `detectionId`     | string        | ✅                       | 비어 있지 않음, DB unique | 네트워크 재전송 중복 방지 키. UUID 사용이 규약이지만 현재 스키마는 UUID 형식 자체를 검증하지 않음 |
| `trackingId`      | integer       | 선택                     | 0 이상             | YOLO 추적 ID, misclassification 전용    |
| `detectedClass`   | DetectedClass | `misclassification`만 ✅ | Enum 값            | 탐지된 쓰레기 클래스, overflow는 생략(`null`)   |
| `binId`           | string        | ✅                       | 비어 있지 않음       | 판정 대상 물리 쓰레기통 ID. 현재 허용 ID 목록 또는 `binType`과의 일치 여부는 검증하지 않음 |
| `binType`         | BinType       | ✅                       | Enum 값            | 물리 쓰레기통 종류                         |
| `isMisclassified` | boolean       | `misclassification`만 ✅ | `true` 또는 `false` | 오분류 여부, overflow는 생략(`null`)        |
| `confidenceScore` | float         | `misclassification`만 ✅ | 0.0 이상 1.0 이하     | AI 판단 신뢰도, overflow는 생략(`null`)     |
| `imageFileId`     | string        | 선택                     | GridFS 파일 ID      | 녹화 파이프라인이 업로드한 GIF 파일 ID, 생략 시 `null` |
| `overflowDuration` | float        | overflow 선택            | 0 이상             | FULL 지속시간 스냅샷                       |
| `overflowThreshold` | float       | overflow 선택            | 0 이상             | FULL 판정 기준시간                         |
| `modelVersion`    | string        | ✅                       | 비어 있지 않음       | 판정 모델 버전                             |

`eventCategory=misclassification`인데 `detectedClass`/`isMisclassified`/`confidenceScore` 중
하나라도 빠지면 HTTP 422(Pydantic `model_validator` 검증).

현재 카테고리별 검증은 다음과 같다.

* `misclassification`은 `ELEV-TOP`만, `overflow`는 `ELEV-SIDE`만 허용한다.
* `overflow`에 `detectedClass`/`isMisclassified`/`confidenceScore` 중 하나라도 있으면 422다.
* `trackingId`는 문서상 misclassification 용도지만 현재 스키마는 overflow에 포함되어도
  거부하지 않는다. 반대로 `overflowDuration`/`overflowThreshold`도 misclassification 요청에
  포함되는 것을 현재 스키마가 거부하지 않는다.

### 요청 예시 — misclassification

```json
{
  "cameraId": "ELEV-TOP",
  "eventCategory": "misclassification",
  "detectionId": "a6339b38-a4a0-46a2-90b1-55cd73ba85be",
  "trackingId": 17,
  "detectedClass": "recyclables",
  "binId": "BIN-PAPER",
  "binType": "paper",
  "isMisclassified": true,
  "confidenceScore": 0.85,
  "imageFileId": "68f2c1a4b9d3e2f1a0c5d6e7",
  "modelVersion": "yolo26-mvp-1"
}
```

### 요청 예시 — overflow

```json
{
  "cameraId": "ELEV-SIDE",
  "eventCategory": "overflow",
  "detectionId": "5e67c365-c44b-4a13-b55f-a814a520fa5e",
  "binId": "BIN-GENERAL",
  "binType": "normal",
  "overflowDuration": 5.2,
  "overflowThreshold": 5.0,
  "imageFileId": "68f2c1a4b9d3e2f1a0c5d6e8",
  "modelVersion": "yolo26-mvp-1"
}
```

### curl 예시

```bash
curl -X POST "http://localhost:8047/api/events" \
  -H "Content-Type: application/json" \
  -d "{\"cameraId\":\"ELEV-TOP\",\"eventCategory\":\"misclassification\",\"detectionId\":\"a6339b38-a4a0-46a2-90b1-55cd73ba85be\",\"trackingId\":17,\"detectedClass\":\"recyclables\",\"binId\":\"BIN-PAPER\",\"binType\":\"paper\",\"isMisclassified\":true,\"confidenceScore\":0.85,\"modelVersion\":\"yolo26-mvp-1\"}"
```

### 이벤트가 생성되는 경우

* `misclassification`: `isMisclassified`가 `true`이고, 동일한 `cameraId`+`detectedClass` 조합으로 생성된 직전 이벤트로부터 5초 이상 경과
* `overflow`: 유효한 요청이면 저장하며 `detectionId` 중복만 차단한다. `NORMAL`→`FULL` 전환
  판정은 현재 호출자(GPU 서버의 SIDE MobileNet_V3_Small 로직)의 책임이며, 백엔드는
  `BIN_STATES`로 이를 검증하지 않는다.

### 이벤트가 생성되지 않는 경우

다음 조건에서는 HTTP 200과 함께 `null`을 반환한다.

* `misclassification`이고 `isMisclassified=false`
* misclassification 쿨다운 적용 중(`cameraId`+`detectedClass` 기준 5초)

동일한 `detectionId`가 이미 저장되어 있으면 새 문서를 만들지 않고 기존 `Event`를 HTTP 200으로
반환한다. 내부 생성 결과의 `created` 상태를 구분하므로 기존 이벤트를 반환하는 재전송에서는
WebSocket 알림도 다시 보내지 않는다.

### 정상 응답 — `Event`

```json
{
  "eventId": "a3b70dae-3a1b-48b6-a8d1-a06afcb934d1",
  "timestamp": "2026-08-11T06:47:50.261977Z",
  "cameraId": "ELEV-TOP",
  "eventCategory": "misclassification",
  "detectionId": "a6339b38-a4a0-46a2-90b1-55cd73ba85be",
  "trackingId": 17,
  "detectedClass": "recyclables",
  "binId": "BIN-PAPER",
  "binType": "paper",
  "isMisclassified": true,
  "confidenceScore": 0.85,
  "actionTaken": "lightAndSound",
  "imageFileId": "68f2c1a4b9d3e2f1a0c5d6e7",
  "overflowDuration": null,
  "overflowThreshold": null,
  "modelVersion": "yolo26-mvp-1",
  "notes": null
}
```

### Response 필드

| 필드                | 타입                | null 허용 | 설명                                             |
| ----------------- | ----------------- | ------- | ----------------------------------------------- |
| `eventId`         | string            | ❌       | UUID                                            |
| `timestamp`       | ISO 8601 datetime | ❌       | 서버의 UTC 기준 이벤트 생성 시각                            |
| `cameraId`        | CameraId          | ❌       | 카메라 ID                                          |
| `eventCategory`   | EventCategory     | ❌       | `misclassification` 또는 `overflow`               |
| `detectionId`     | string            | ❌       | 중복 저장 방지용 감지 UUID                             |
| `trackingId`      | integer           | ✅       | YOLO 추적 ID                                      |
| `detectedClass`   | DetectedClass     | ✅       | 탐지 클래스, overflow는 `null`                        |
| `binId`           | string            | ❌       | 물리 쓰레기통 ID                                    |
| `binType`         | BinType           | ❌       | 물리 쓰레기통 종류                                   |
| `isMisclassified` | boolean           | ✅       | 오분류 여부, overflow는 `null`                        |
| `confidenceScore` | float             | ✅       | 신뢰도, overflow는 `null`                           |
| `actionTaken`     | ActionTaken       | ❌       | 모드에 따른 경고 처리 결과                                 |
| `imageFileId`     | string            | ✅       | GridFS 파일 ID(GIF), 녹화 파이프라인 연동 전이거나 생략 시 `null` |
| `overflowDuration` | float            | ✅       | overflow 지속시간                                  |
| `overflowThreshold` | float           | ✅       | overflow 판정 기준시간                              |
| `modelVersion`    | string            | ❌       | 판정 모델 버전                                      |
| `notes`           | string            | ✅       | 추가 설명, 현재 생성 이벤트는 `null`                        |

### 모드별 처리

| 현재 Mode   | 이벤트 저장 | `actionTaken`   | WebSocket 알림 |
| --------- | ------ | --------------- | ------------ |
| `MANAGE`  | 저장     | `lightAndSound` | 전송           |
| `COLLECT` | 저장     | `none`          | 전송하지 않음      |

> 현재 `lightAndSound`는 실제 RPA 장치 작동 결과가 아니라 Mock 응답 값이다.

### 부수 효과

`MANAGE` 모드에서 이벤트가 실제로 생성되면 연결된 WebSocket 클라이언트에 카테고리별로 다른
메시지를 전송한다.

misclassification:
```json
{
  "eventType": "MISCLASSIFICATION_DETECTED",
  "cameraId": "ELEV-TOP",
  "timestamp": "2026-08-11T06:47:50.261977+00:00",
  "isMisclassified": true
}
```

overflow:
```json
{
  "eventType": "BIN_OVERFLOW_DETECTED",
  "cameraId": "ELEV-SIDE",
  "timestamp": "2026-08-11T06:47:50.261977+00:00"
}
```

### 상태 코드

| 상태 코드 | 설명                                                       |
| ----- | -------------------------------------------------------- |
| 200   | 이벤트 생성 또는 `null` 반환                                       |
| 422   | 필수 필드 누락(카테고리별 조건 포함), Enum 오류, 타입 오류 또는 신뢰도 범위 오류         |
| 500   | 서버 내부 처리 오류                                              |

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
    "cameraId": "ELEV-TOP",
    "eventCategory": "misclassification",
    "detectionId": "a6339b38-a4a0-46a2-90b1-55cd73ba85be",
    "trackingId": 17,
    "detectedClass": "coffeeCup",
    "binId": "BIN-PAPER",
    "binType": "paper",
    "isMisclassified": true,
    "confidenceScore": 0.83,
    "actionTaken": "lightAndSound",
    "imageFileId": null,
    "overflowDuration": null,
    "overflowThreshold": null,
    "modelVersion": "yolo26-mvp-1",
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

* MongoDB `events` 컬렉션에 저장한다(motor, In-memory Mock 아님).
* 서버를 다시 시작해도 이벤트는 유지된다.
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
GET /api/events/a3b70dae-3a1b-48b6-a8d1-a06afcb934d1
```

### 정상 응답

```json
{
  "eventId": "a3b70dae-3a1b-48b6-a8d1-a06afcb934d1",
  "timestamp": "2026-08-11T01:05:53.810490Z",
  "cameraId": "ELEV-TOP",
  "eventCategory": "misclassification",
  "detectionId": "a6339b38-a4a0-46a2-90b1-55cd73ba85be",
  "trackingId": 17,
  "detectedClass": "recyclables",
  "binId": "BIN-PAPER",
  "binType": "paper",
  "isMisclassified": true,
  "confidenceScore": 0.91,
  "actionTaken": "lightAndSound",
  "imageFileId": "68f2c1a4b9d3e2f1a0c5d6e7",
  "overflowDuration": null,
  "overflowThreshold": null,
  "modelVersion": "yolo26-mvp-1",
  "notes": null
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
    "normal",
    "paper",
    "recyclables",
    "coffeeCup"
  ],
  "counts": [
    0,
    1,
    1,
    0
  ],
  "totalEventCount": 2,
  "misclassificationCount": 1,
  "overflowCount": 1
}
```

### Response 필드

| 필드       | 타입              | 설명                      |
| -------- | --------------- | ----------------------- |
| `labels` | DetectedClass[] | 지원하는 탐지 클래스 전체 목록       |
| `counts` | integer[]       | 같은 인덱스의 클래스에 해당하는 이벤트 수 |
| `totalEventCount` | integer | 전체 저장 이벤트 수 |
| `misclassificationCount` | integer | 오분류 이벤트 수 |
| `overflowCount` | integer | 넘침 이벤트 수 |

### 인덱스 대응

| `labels` 값   | 화면 표시   |
| ------------ | -------- |
| `normal`    | 일반 쓰레기   |
| `paper`      | 종이       |
| `recyclables` | 플라스틱·캔   |
| `coffeeCup`  | 커피 컵     |

### 동작

* 캐시 없이 호출 시점마다 이벤트 저장소를 집계한다.
* 모든 클래스가 항상 `labels`에 포함된다.
* 이벤트가 없는 클래스는 `counts` 값으로 `0`을 반환한다.
* `from`, `to`가 있으면 해당 기간의 이벤트만 집계한다.
* `overflow` 이벤트는 `detectedClass`가 없어 `labels`/`counts` 클래스별 집계에는 포함되지
  않지만, `totalEventCount`와 `overflowCount`에는 포함된다.

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

## EP-08. `POST /api/detection/start`

라이브뷰/DB 클립용 녹화를 시작한다. TOP은 `presenceGateService.py`(사람 존재 감지 게이팅)가
내부적으로 호출하고, SIDE는 GPU 서버의 MobileNet_V3_Small 로직이 호출한다. **GPU 서버의
`tracking2.py`는 이 엔드포인트를 호출하지 않는다** — 오분류 판정 결과는 별도로 EP-12
(`POST /api/events/aiDisposal`)로만 들어온다(즉 이 녹화는 GPU 판정과 독립적). 수동
검증 시엔 `debug/detection/`의 스크립트가 직접 호출하기도 한다.

### Request Body

```json
{
  "cameraId": "ELEV-SIDE"
}
```

### 정상 응답

```json
{
  "recordingId": "7fde5b24-0a55-4f0f-b0fb-a443380496ad"
}
```

카메라가 설정되지 않았거나 연결할 수 없으면 HTTP 503을 반환한다.

---

## EP-09. `POST /api/detection/stop`

탐지 종료 시점에 EP-08의 녹화를 종료하고, 캡처 프레임을 GIF로 인코딩해 GridFS에 업로드한
뒤 EP-02와 동일한 이벤트 저장 로직을 실행한다. `misclassification`과 `overflow`를 모두
지원한다. 기존 호출 호환성을 위해 `eventCategory`를 생략하면 `misclassification`으로 처리한다.

### 공통 필드

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `recordingId` | string | ✅ | EP-08에서 받은 녹화 ID |
| `cameraId` | CameraId | ✅ | misclassification=`ELEV-TOP`, overflow=`ELEV-SIDE` |
| `eventCategory` | EventCategory | 선택 | 생략 시 `misclassification` |
| `detectionId` | string | ✅ | 탐지 모델이 생성한 중복 방지 UUID(misclassification=GPU 서버 `tracking2.py`, overflow=GPU 서버 `sideOverflow.py`) |
| `trackingId` | integer | 선택 | misclassification 추적 ID |
| `binId` | string | ✅ | 판정 대상 물리 쓰레기통 ID |
| `binType` | BinType | ✅ | 판정 대상 쓰레기통 종류 |
| `modelVersion` | string | ✅ | 판정 모델 버전 |

### misclassification 추가 필드

`detectedClass`, `isMisclassified`, `confidenceScore`가 모두 필수다.

### overflow 추가 필드

분류 필드는 보내지 않는다. `overflowDuration`, `overflowThreshold`를 선택적으로 보낼 수 있다.

```json
{
  "recordingId": "7fde5b24-0a55-4f0f-b0fb-a443380496ad",
  "cameraId": "ELEV-SIDE",
  "eventCategory": "overflow",
  "detectionId": "5e67c365-c44b-4a13-b55f-a814a520fa5e",
  "binId": "BIN-GENERAL",
  "binType": "normal",
  "overflowDuration": 5.2,
  "overflowThreshold": 5.0,
  "modelVersion": "overflow-mvp-1"
}
```

`recordingId`가 없으면 404, 캡처 프레임이 없으면 400, 카테고리별 필드 또는 카메라 역할이
잘못되면 422를 반환한다. 이벤트 생성 후 모드와 카테고리에 맞는 WebSocket 메시지를 전송한다.
`recordingId`에 저장된 시작 카메라와 stop 요청의 `cameraId`가 다르면 HTTP 400으로 거부하며
활성 세션은 올바른 카메라로 다시 요청할 수 있도록 보존한다. GIF 업로드 뒤
`isMisclassified=false`, Cooldown, 중복 `detectionId` 또는 DB 저장 실패로 Event가 새로
저장되지 않으면 방금 올린 GridFS 파일을 보상 삭제한다.

정상 종료된 녹화의 프레임과 duration은 최대 120초 동안만 메모리에 보존한다. GIF/DB 처리가
성공하면 원본 프레임은 즉시 해제하고 완료 결과만 120초 동안 `recordingId`+`detectionId`로
캐시한다. 응답 유실 뒤 같은 두 ID로 stop을 재시도하면 GIF 업로드·DB 저장·WebSocket 전송을
반복하지 않고 기존 결과를 반환한다. 처리 실패 때만 원본 프레임을 보존해 같은 요청으로 다시
처리할 수 있다. 같은 `recordingId`를 다른 `detectionId`에 재사용하면 HTTP 400으로 거부한다.
종료 신호 자체가 오지 않은 활성 세션은 최대 30초 캡처 뒤 세션과 프레임을 자동 정리한다.
`debug/detection/detectionApiClient.py`는 start에는 자동 재시도를 적용하지 않고, stop에만
60초 timeout과 연결 오류(응답 처리 중 연결 단절 포함) 1회 재시도를 적용한다. 재시도에도 같은
`recordingId`와 `detectionId`를 사용한다.

---

## EP-07. `WS /ws/events`

관리자 웹 클라이언트가 실시간 모드 변경, 오분류, 넘침 이벤트를 수신하는 WebSocket 엔드포인트다.

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
| `BIN_OVERFLOW_DETECTED`      | `cameraId`, `timestamp`                    | `MANAGE` 모드에서 overflow 이벤트가 반환됐을 때 |

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
  "cameraId": "ELEV-TOP",
  "timestamp": "2026-08-11T05:25:28.109933+00:00",
  "isMisclassified": true
}
```

### 모드별 WebSocket 동작

| Mode      | 이벤트 저장 | 이벤트 WebSocket 전송 |
| --------- | ------ | ---------------- |
| `MANAGE`  | 저장     | 전송               |
| `COLLECT` | 저장     | 전송하지 않음          |

### 향후 구현 예정 메시지

| `eventType`           | 예정 Payload              | 현재 상태                  |
| ---------------------- | ----------------------- | ---------------------- |
| `CAMERA_DISCONNECTED`  | `cameraId`, `timestamp` | 카메라 연결 감시 구현 후 추가 예정   |
| `SYSTEM_ERROR`         | `message`, `timestamp`  | 서버 오류 알림 정책 확정 후 추가 예정 |

> `BIN_OVERFLOW_DETECTED`는 구현 완료 — EP-02 "부수 효과" 참고.

> `eventType` 값은 대문자 스네이크케이스를 사용한다. JSON Payload 필드명은 camelCase를 사용한다.

---

## EP-10. `GET /api/binStates`

물리 쓰레기통 4개의 현재 상태(`BIN_STATES`)를 조회한다. 통계·이전기록과 달리 이력이 아니라
`binId`당 최신 상태 1행만 반환한다(대시보드에서 "지금 어느 통이 가득 찼는지" 표시용).

### 요청

파라미터 없음.

### 정상 응답 — `list[BinState]`(HTTP 200)

| 필드                    | 타입           | 설명                                             |
| --------------------- | ------------ | ---------------------------------------------- |
| `binId`               | string       | 물리 쓰레기통 ID                                     |
| `cameraId`             | CameraId     | 항상 `ELEV-SIDE`                                 |
| `binType`              | BinType      | 통 종류                                           |
| `sessionId`            | string       | 넘침 감지 모델 프로세스 세션 ID(재시작마다 갱신)                 |
| `currentState`         | string       | `NORMAL` 또는 `FULL`                             |
| `confidenceScore`      | float        | 최근 판정 신뢰도(0.0~1.0)                             |
| `overflowDuration`     | float        | 현재 `FULL` 상태로 유지된 시간(초)                        |
| `lastChangedAt`        | datetime     | `NORMAL`↔`FULL` 마지막 전환 시각(ISO 8601)             |
| `activeOverflowEventId` | string\|null | 현재 `FULL`을 유발한 `EVENT.eventId`. `NORMAL` 복귀 시 `null` |

### 요청 예시

```http
GET /api/binStates
```

### 응답 예시

```json
[
  {
    "binId": "BIN-GENERAL",
    "cameraId": "ELEV-SIDE",
    "binType": "normal",
    "sessionId": "8f2e...",
    "currentState": "FULL",
    "confidenceScore": 0.97,
    "overflowDuration": 12.4,
    "lastChangedAt": "2026-08-19T02:10:03.512000+00:00",
    "activeOverflowEventId": "5c3a..."
  }
]
```

---

## EP-11. `POST /api/binStates`

GPU 서버의 SIDE MobileNet_V3_Small 로직(`models/trashoverflow/sideOverflow.py`, 또는
디버그 스크립트)이 통별 넘침 감지 결과를 주기적으로 보내는 상태 갱신 엔드포인트다(TOP의
EP-12와 같은 방향 — GPU가 로컬 백엔드를 호출). 이전 저장값 대비 `currentState`가 바뀔 때만
상태 전환으로 처리한다.

* `NORMAL`→`FULL` 전환: `overflow` `EVENT`를 새로 생성(EP-02와 동일한 `eventService` 로직 —
  `detectionId` 중복 방지 포함)하고, 생성된 `eventId`를 `activeOverflowEventId`에 기록한다.
  `MANAGE` 모드면 `BIN_OVERFLOW_DETECTED`를 WebSocket으로 브로드캐스트한다(EP-07 참고).
* `FULL`→`NORMAL` 전환: `EVENT`를 만들지 않고 `activeOverflowEventId`만 `null`로 리셋한다.
* 상태 유지(같은 값 반복 수신): `EVENT`도 새로 만들지 않고 `confidenceScore`/`overflowDuration`
  등 값만 최신화한다. `lastChangedAt`은 실제 전환이 있었을 때만 갱신된다.

### Request Body — `BinStateUpdate`

| 필드                  | 타입      | 필수 | 제약 조건        | 설명                                    |
| ------------------- | ------- | -- | ------------ | ------------------------------------- |
| `binId`             | string  | ✅  | 비어 있지 않음     | 물리 쓰레기통 ID                            |
| `cameraId`           | CameraId | 선택(기본 `ELEV-SIDE`) | `ELEV-SIDE`만 허용 | 다른 값이면 422           |
| `binType`            | BinType | ✅  | Enum 값       | 통 종류                                  |
| `sessionId`          | string  | ✅  | 비어 있지 않음     | 넘침 감지 모델 세션 ID                        |
| `currentState`       | string  | ✅  | `NORMAL`\|`FULL` | 이번에 관측된 상태                          |
| `confidenceScore`    | float   | ✅  | 0.0~1.0      | 판정 신뢰도                                |
| `overflowDuration`   | float   | ✅  | 0 이상         | 현재 `FULL` 유지 시간(초), `NORMAL`이면 0 전달   |
| `overflowThreshold`  | float   | 선택 | 0 이상         | `FULL` 판정 기준시간. 전환 시 생성되는 `EVENT`에만 사용 |
| `detectionId`        | string  | ✅  | 비어 있지 않음, DB unique | `NORMAL`→`FULL` 전환 시 생성되는 `EVENT`의 중복 방지 키. 전환이 아니면 사용되지 않지만 매 호출 필수(전환 시점에만 갑자기 없어서 실패하는 상황 방지) |
| `modelVersion`       | string  | ✅  | 비어 있지 않음     | 판정 모델 버전                              |

### 요청 예시

```json
{
  "binId": "BIN-GENERAL",
  "cameraId": "ELEV-SIDE",
  "binType": "normal",
  "sessionId": "8f2e...",
  "currentState": "FULL",
  "confidenceScore": 0.97,
  "overflowDuration": 12.4,
  "overflowThreshold": 5.0,
  "detectionId": "GPU 서버 SIDE MobileNet_V3_Small 로직이 생성한 UUID",
  "modelVersion": "overflow-mvp-1"
}
```

### 정상 응답 — `BinState`(HTTP 200)

EP-10 응답 항목과 동일한 단일 객체.

### 에러 응답

| 상태 코드 | 발생 조건                                  |
| ----- | -------------------------------------- |
| 422   | 스키마 불일치, Enum 값 오류, `cameraId != ELEV-SIDE` |

---

## EP-12. `POST /api/events/aiDisposal`

GPU 서버의 `models/trashdetect/tracking2.py`가 TOP 카메라 투척을 자체 판정(감지+추적+분류+
정상/오분류 판정 전부 GPU 쪽에서 완결)한 뒤 결과를 로컬 백엔드로 **직접 푸시**하는 전용
엔드포인트다. 로컬 백엔드가 GPU를 호출하는 방향이 아니라 **GPU가 로컬 백엔드를 호출**하는
방향이며(`decisionLog.md` 참고), `presenceGateService.py`가 관리하는 EP-08/EP-09 녹화
흐름과는 완전히 독립적이다. `tracking2.py`의 `create_disposal_event()` 출력 형태를 그대로
받아 내부 `EventCreate`로 매핑한 뒤 EP-02와 동일한 `eventService.createEventWithStatus`
(쿨다운·멱등성 포함)를 재사용한다(`services/eventService.py`의 `createEventFromAiDisposal`).

### Request Body — `AiDisposalEvent`

| 필드              | 타입      | 필수 | 설명                                                          |
| --------------- | ------- | -- | ----------------------------------------------------------- |
| `eventId`       | string  | ✅  | `tracking2.py`가 생성한 UUID — 내부 `detectionId`로 그대로 사용(중복 방지) |
| `trackId`       | int     | ✅  | ByteTrack 내부 추적 ID — 내부 `trackingId`로 매핑                     |
| `timestamp`     | string  | ✅  | ISO8601, 참고용(백엔드는 자체 저장 시각을 별도로 씀)                          |
| `cameraId`      | string  | ✅  | `tracking2.py` 쪽 값 그대로(`"CAM-01"` 등). 백엔드가 `ELEV-TOP`으로 매핑(현재 매핑표엔 `CAM-01`만 등록) |
| `detectedClass` | string  | ✅  | `"normal"`/`"paper"`/`"recyclables"`/`"coffeecup"` — 백엔드가 `DetectedClass`로 매핑 |
| `binId`         | string  | ✅  | `detectedClass`와 동일 값 체계(모델이 통도 같은 4종으로 인식) — 백엔드가 `BinType`으로 매핑 |
| `result`        | string  | ✅  | `"correct"`/`"incorrect"`/`"unknown"` — 백엔드가 `isMisclassified`(`incorrect`→`true`)로 변환. `unknown`은 이벤트 미생성(로그만) |
| `imagePath`     | string  | 선택 | GPU 서버 로컬 파일 경로 — 아직 GridFS 연동 안 됨(TBD), 현재는 무시됨              |

값 매핑 실패(등록 안 된 `cameraId`/`detectedClass`/`binId`) 또는 `result: unknown`이면
에러 응답 없이 이벤트만 생성하지 않는다(외부 스크립트가 보내는 데이터라 방어적으로 처리,
서버 로그에 경고만 남김) — misclassification 여부가 아니라 값 자체를 해석 못 한 경우다.

### 요청 예시

```json
{
  "eventId": "3d0a1f2e-...",
  "trackId": 15,
  "timestamp": "2026-08-23T16:12:00+09:00",
  "cameraId": "CAM-01",
  "detectedClass": "recyclables",
  "binId": "recyclables",
  "result": "incorrect",
  "imagePath": "waste_events/3d0a1f2e-....jpg"
}
```

### 정상 응답 — `Event | null`(HTTP 200)

EP-02와 동일한 `Event` 형태. `result: correct`이거나 값 매핑에 실패하면 `null`(이벤트 미생성,
에러 아님).

### 에러 응답

| 상태 코드 | 발생 조건            |
| ----- | ---------------- |
| 422   | 요청 스키마 자체가 불일치(필드 누락/타입 오류) |

---

## EP-13. `GET/POST /api/reports/email`

통계 대시보드의 **이메일 설정** 기능이다. 이 API는 보고서를 즉시 발송하지 않는다. 관리자가
자동 일일·주간 보고서를 받을 이메일 한 개를 조회·저장하거나 수신을 해제한다. 저장된 주소는
`RPAs/reportAutomation/state/recipientSettings.json`에 기록되며, Docker에서는 `backend`와
별도 `report-scheduler` 프로세스가 `report-state` 볼륨으로 공유한다. SMTP 발신 계정과 앱
비밀번호는 계속 서버 환경 설정에만 두며 브라우저로 전달하지 않는다.

### `GET /api/reports/email`

설정된 수신 이메일을 조회한다. 아직 설정하지 않았으면 HTTP 200과 함께 `configured=false`,
`recipient=null`을 반환한다.

### `POST /api/reports/email` Request — `ReportEmailSettingsRequest`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `recipient` | string \| null | ❌ | 자동 보고서를 받을 이메일 한 개(최대 254자). `null` 또는 빈 문자열이면 수신 해제 |

```json
{
  "recipient": "manager@example.com"
}
```

### 정상 응답 — `ReportEmailSettingsResponse`(HTTP 200)

```json
{
  "configured": true,
  "recipient": "manager@example.com",
  "message": "자동 보고서 수신 이메일을 저장했습니다."
}
```

저장 이후 별도 `report-scheduler` 프로세스가 KST 기준 매일 09:00에 전날 일일 보고서를,
매주 월요일 09:10에 이전 주 주간 보고서를 생성·발송한다. 통계·이벤트 API 교차 검증,
HTML/CSV 생성, 재시도 및 중복 발송 방지는 기존 RPA 로직을 그대로 사용한다.
설정 확인 시점에는 즉시 발송하지 않으며 다음 예약 시각부터 적용한다.
수신 해제 시 `recipient=null` 상태를 저장해 `.env`의 `RPA_REPORT_RECIPIENTS` 폴백도 사용하지
않는다. 다시 이메일을 저장하기 전까지 예약 보고서는 발송되지 않는다.

운영 DB의 7일 보존 경계와 주간 발송 시각 사이에 데이터가 사라지는 것을 막기 위해 일일
보고서에서 검증한 이벤트 메타데이터를 `report-state` 볼륨에 날짜별 JSON으로 임시 저장한다.
최근 7개 날짜만 유지하고 GIF·이미지 원본·SMTP 자격 증명은 저장하지 않는다. 주간 보고서는
이 스냅샷 7개를 합산하며, 누락 또는 검증 실패가 있으면 부정확한 메일을 발송하지 않는다.
전주 비교는 원본 이벤트 대신 최근 2개의 주간 집계만 보존한다. 이 동작은 기존 API 요청·응답
스키마를 변경하지 않는다.

### 에러 응답

| 상태 코드 | 발생 조건 |
| --- | --- |
| 422 | 비어 있지 않은 이메일의 형식 또는 요청 스키마 불일치 |
| 500 | 수신 이메일 설정 파일 조회 또는 저장 실패 |

현재 인증·권한은 구현되지 않았으므로 내부망 대시보드 사용을 전제로 한다. 외부 공개 전에는
이 엔드포인트에 관리자 인증을 추가해야 한다.

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

* Jinja2 Context로 `cameraIds` 목록 전달
* 지점(카메라)별 스트림 분할 표시
* 사이드바 메뉴
* 관리/수거 모드 표시
* WebSocket 연결
* 오분류 이벤트 경고 표시

### 사용하는 API

```text
GET /api/stream/{cameraId}
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
* 최초 진입 시 시작일·종료일을 브라우저 현지 기준 당일로 자동 설정하고, 첫 조회부터 해당
  날짜의 `from`/`to`만 API에 전달(필터 초기화도 당일 범위로 복귀)
* 테이블 정렬
* 페이지네이션
* 행 선택 시 상세 모달
* 새 이벤트 생성 후 새로고침하면 목록에 반영

### 사용하는 API

```text
GET /api/events
GET /api/events/{id}
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
* 자동 일일·주간 보고서 수신 이메일 조회·설정(즉시 발송 없음)

### 사용하는 API

```text
GET /api/statistics
GET /api/events
GET /api/reports/email
POST /api/reports/email
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
| 400   | 녹화 프레임 없음, 시작/종료 카메라 불일치 또는 `recordingId` 재사용 충돌(EP-09) |
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

`repositories/eventRepository.py`는 motor 기반 MongoDB 저장소다(In-memory Mock 아님).

| 항목     | 현재 동작                       |
| ------ | --------------------------- |
| 저장 방식  | MongoDB `events` 컬렉션(motor) |
| 초기 데이터 | 없음(시드 제거)                   |
| 생성 이벤트 | `events` 컬렉션에 영구 저장         |
| 서버 재시작 | 이벤트 유지                      |
| 정렬     | `timestamp` 최신순             |
| 상세 조회  | `eventId` 일치 검색             |
| 기간 조회  | `from`, `to` 기준 필터          |
| 통계     | `DetectedClass`별 집계 파이프라인   |
| 미디어 저장 | GridFS(GIF), `imageFileId`로 참조 |

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

# 5. 이벤트 카테고리 / 녹화 / MongoDB·GridFS 연동 (구현 완료)

## 5-1. 이벤트 카테고리

`EventCreate`와 `Event`에 `eventCategory` 필드가 구현되어 있다(상세는 EP-02 참고).

```json
{
  "eventCategory": "misclassification"
}
```

허용 값:

```text
misclassification
overflow
```

### 의미

| 값                   | 설명                |
| ------------------- | ----------------- |
| `misclassification` | 투기 또는 오분류 이벤트     |
| `overflow`          | 쓰레기통 포화 또는 넘침 이벤트 |

---

## 5-2. Overflow 이벤트 및 녹화 파이프라인

요청 예시:

```json
{
  "cameraId": "ELEV-SIDE",
  "eventCategory": "overflow"
}
```

WebSocket 메시지:

```json
{
  "eventType": "BIN_OVERFLOW_DETECTED",
  "cameraId": "ELEV-SIDE",
  "timestamp": "2026-08-11T06:47:50.261977+00:00"
}
```

트리거 시점 녹화 → GIF 인코딩 → GridFS 업로드 파이프라인이 구현되어 있다
(`services/recordingService.py`, `services/mediaService.py`,
`repositories/mediaRepository.py`). 고정 10초가 아니라 시작~종료 신호 사이 실제 구간을
캡처하며(신호 유실 대비 최대 30초 안전 캡), 결과 GridFS 파일 ID가 `imageFileId`로
저장된다. 실제 탐지 서비스가 아직 없어 지금은 `debug/detection/simulateEventPipeline.py`로
시작/종료 신호를 흉내내 검증한다.

현재 구현과 확정 설계를 구분하면 다음과 같다.

* `EP-02`/`EP-09`로 직접 만드는 overflow는 시간 Cooldown이 없다. 서로 다른 `detectionId`이면
  연속 요청도 각각 저장된다 — 상태 전환 검증이 필요 없는 수동/디버그 호출용 경로다.
* 확정 설계(`BIN_STATES.currentState`가 `NORMAL`→`FULL`로 바뀌는 순간에만 저장)는 `EP-10`/`EP-11`
  (`GET`/`POST /api/binStates`, `services/binStateService.py`)로 구현 완료됐다. GPU 서버의
  SIDE MobileNet_V3_Small 로직이 이 엔드포인트로 상태를 보고하면 전환 시점에만 `EVENT`가 생성된다.
* `actionTaken`은 다른 이벤트와 동일하게 `MANAGE=lightAndSound`, `COLLECT=none`으로 저장된다.
  실제 RPA 장치 동작은 미구현이다.
* 통계는 `overflowCount`와 `totalEventCount`에 overflow를 포함한다. 클래스별 `counts`에서는
  제외한다.

---

## 5-3. MongoDB 및 GridFS

In-memory 저장소를 Motor 기반 MongoDB 저장소로 교체 완료했다(`repositories/eventRepository.py`,
`repositories/mongoClient.py`, `repositories/mediaRepository.py`).

| 항목           | 구현 내용                        |
| ------------ | ---------------------------- |
| MongoDB 이미지  | `mongo:7.0`                  |
| 로컬 Host Port | `27020`                      |
| 컨테이너 Port    | `27017`                      |
| Python 드라이버  | `motor`                      |
| 파일 저장        | GridFS(`topMedia`/`sideMedia` 버킷), GIF |
| 저장 대상        | 이벤트(`events` 컬렉션), 이벤트 클립(GridFS), 통 상태(`binStates` 컬렉션, `binId`당 최신 1행) |

이벤트 목록과 통계는 현재 필수 필드·Enum 계약을 만족하는 문서만 대상으로 한다. 과거 raw insert
등으로 필드가 빠졌거나 Enum·timestamp·선택 필드 타입이 다른 문서는 의미를 임의로 만들어
응답하지 않고 건너뛰며 서버 로그에 남긴다. 따라서 구형 문서 한 건 때문에 전체
`GET /api/events`가 500이 되거나 목록과 통계 집계 대상이 달라지지는 않는다.
`debug/db/seedTestEvents.py`와 `testCrud.py`는 `MONGO_HOST=localhost`(또는 loopback)와
`DB_NAME=sortMasterTest` 조합만 허용해 공유 DB에 테스트 문서를 넣는 실행을 차단한다.

앱 lifespan은 시작 시 5초 제한으로 MongoDB `ping`과 Event 인덱스 준비를 수행한다. 연결·인증
또는 인덱스 준비가 실패하면 uvicorn이 정상 시작된 것처럼 응답하지 않고 startup 자체를
실패시킨다. 종료 시 활성 녹화·캐시 프레임·카메라 캡처와 MongoDB 연결 풀을 정리한다.
`GET /api/statistics`의 클래스·카테고리 집계는 한 `$facet` 쿼리에서 계산해 요청 도중 새
이벤트가 들어와도 두 합계의 읽기 시점이 갈리지 않는다.

모드 상태(`services/modeService.py`)는 여전히 메모리로만 관리되어 서버 재시작 시
`MANAGE`로 초기화된다(DB 저장 대상 아님). MongoDB 연결 후에도 외부 JSON API 필드명은
camelCase를 유지한다.

---

## 5-4. 실제 RPA 연동

현재 `actionTaken`은 Mock 결과 값이다.

향후 다음 기능을 구현할 예정이다.

* 전구 점등
* 경고음 출력
* 알림만 전송
* 라즈베리파이 GPIO 트리거
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
* 카메라 상태 조회 API 추가 여부
* 모드 조회용 `GET /api/mode` 추가 여부
* 실제 RPA 통신 방식
* 인증 및 권한
* 이벤트 상세 페이지 구현 여부
* AI 탐지 신뢰도 Threshold

---

# 7. 구현 상태 체크표

| ID      | 기능                    | 현재 상태           |
| ------- | --------------------- | --------------- |
| EP-01   | 카메라 MJPEG 스트리밍        | 구현됨             |
| EP-02   | 오분류/넘침 이벤트 생성         | 구현됨(`BIN_STATES` 전환 검증 제외) |
| EP-03   | 이벤트 목록 및 기간 조회        | 구현됨             |
| EP-04   | 이벤트 상세 및 404 처리       | 구현됨             |
| EP-05   | 클래스별 통계 조회            | 구현됨             |
| EP-06   | 관리/수거 모드 전환           | 구현됨             |
| EP-07   | WebSocket 모드·오분류·넘침 알림 | 구현됨             |
| EP-08   | 탐지 시작 및 이벤트 녹화 시작 | 구현됨             |
| EP-09   | 탐지 종료·GIF·이벤트 저장     | 구현됨(misclassification/overflow) |
| EP-10   | BIN_STATES 조회           | 구현됨             |
| EP-11   | BIN_STATES 갱신(전환 시 overflow 이벤트 생성) | 구현됨 |
| EP-12   | GPU 서버(`tracking2.py`) 투척 판정 결과 수신 | 구현됨(`tracking2.py`의 RTSP 연결·상시 서비스화는 TBD) |
| EP-13   | 자동 통계 보고서 수신 이메일 설정 | 구현됨(대시보드에서 1개 주소 저장, 별도 스케줄러가 일일·주간 자동 발송) |
| PG-01   | 모니터링 페이지              | 구현됨             |
| PG-02   | 이전기록 페이지              | 구현됨             |
| PG-03   | 통계 대시보드               | 구현됨             |
| DB-01   | MongoDB 이벤트 저장 및 중복 방지 | 구현됨          |
| DB-02   | 카메라별 GridFS 영상 저장     | 구현됨             |
| AI-01   | YOLO 탐지 연동            | 미구현             |
| EVT-01  | Overflow 이벤트 저장·통계    | 구현됨             |
| BIN-01  | BIN_STATES 상태 관리       | 구현됨             |
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
