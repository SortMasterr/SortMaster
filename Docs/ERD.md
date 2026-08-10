# ERD — CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템

> 버전: MVP(Mock 단계) 기준. `WebApps/backend` 코드가 아직 커밋되지 않아 `Docs/API_SPEC.md` / `.agentfiles/apiSpec.md` / `architecture.md` 명세를 근거로 작성함.
> 실제 영속화되는 것은 MongoDB `events` 컬렉션 + GridFS뿐. `CAMERA`/`SystemState`는 현재 DB 컬렉션이 아니라 Enum·런타임 상태라 참고용으로만 표시.
> 2단계 탐지 파이프라인(Nano 상시감시 + Medium 정밀분석)에 따라 이벤트가 `misclassification`(투기)/`overflow`(넘침) 두 카테고리로 나뉨 — `architecture.md` 참고.

## ER 다이어그램

```mermaid
erDiagram
    CAMERA ||--o{ EVENT : "탐지"
    EVENT |o--|| MEDIA_FILE : "참조(선택)"

    CAMERA {
        string cameraId PK "ELEV-01/ELEV-02/REST-4F-01 (Enum, DB 컬렉션 아님)"
        string status "ONLINE/OFFLINE, 런타임 상태(영속화 여부 TBD)"
    }

    EVENT {
        string eventId PK "uuid"
        datetime timestamp
        string cameraId FK "CameraId enum"
        string eventCategory "misclassification(투기) / overflow(넘침)"
        string detectedClass "nullable, misclassification에서만 사용. general/paper/plastic/coffeeCup/mixed/uncertain"
        boolean isMisclassified "nullable, misclassification에서만 사용"
        float confidenceScore "nullable, misclassification에서만 사용, 0.0~1.0"
        string actionTaken "lightAndSound/soundOnly/lightOnly/notificationOnly/none"
        string imageFileId FK "nullable, Mock단계 항상 null"
        string notes "nullable"
    }

    MEDIA_FILE {
        ObjectId fileId PK "GridFS fs.files._id"
        string filename
        string mediaType "image(misclassification) 또는 video/.avi(overflow, 10초 녹화)"
        datetime uploadDate
        int length
        int chunkSize
    }
```

## 참고

- **EVENT**: 실제 MongoDB 컬렉션(`repositories/eventRepository.py`, motor). `.env`의 `USE_MOCK_DB=false`일 때만 영속화, `true`면 in-memory Mock. 매 프레임이 아니라 투기/넘침 판정 시점에만 Insert됨.
  - `misclassification`: 동일 `cameraId`+`detectedClass` 5초 Cooldown
  - `overflow`: 동일 `cameraId` 기준 Cooldown(초 단위 TBD, 현재는 5초로 가정) — 분류 단계 없이 감지 즉시 생성
- **MEDIA_FILE**: MongoDB GridFS(`fs.files`+`fs.chunks`) 표준 구조. `misclassification`은 이미지, `overflow`는 10초 영상(.avi)을 저장하는 것으로 추정(명세상 필드명은 `imageFileId`로 공용). Mock 단계는 항상 `null`.
- **CAMERA**: 별도 컬렉션 없음. `CameraId` Enum + 설정값으로만 존재하는 개념적 엔티티. 3대 고정(`ELEV-01`, `ELEV-02`, `REST-4F-01`).
- **통계(`GET /api/statistics`)**: 저장 없이 매 요청마다 `EVENT`에서 온디맨드 집계 — 별도 엔티티 아님. `overflow` 포함 여부는 TBD.
- **SystemState.mode**(`MANAGE`/`COLLECT`): 전역 상태로만 언급되고 영속화 계층(DB/파일) 명시 없어 ERD에서 제외.
- 2단계 탐지 모델(YOLOv8-Nano/Medium) 자체는 DB에 영속화되는 대상이 아니라 GPU 서버 내 추론 컴포넌트라 ERD 범위 밖.

## TBD (ERD에 영향 줄 수 있는 항목)

- 학습용 원본 이미지 저장 방식: GridFS 재사용 vs GPU 서버 로컬 디스크 축적 (`architecture.md`)
- `CameraStatus`, `SystemState.mode`의 영속화/컬렉션화 여부
- `overflow` 이벤트의 Cooldown 기준(현재 misclassification과 동일 5초로 가정, 재검토 필요)
- 통계에 `overflow` 건수 포함/분리 집계 여부
- `mixed`/`uncertain` 클래스 세부 정의가 `EVENT.detectedClass` 스키마에 영향 줄 수 있음
- 이미지/영상 필드가 실제로 `imageFileId` 하나로 공용될지, `overflow`용 별도 필드(예: `videoFileId`)로 분리될지 미확정
