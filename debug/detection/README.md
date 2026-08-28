# debug/detection

탐지·판정 신호를 백엔드로 보내는 쪽을 **백엔드 코드 변경 없이** 로컬에서 검증하는 도구
모음. `debug/db`·`debug/streaming`·`debug/hardware`와 같은 성격이며, 운영 코드가 아니다.

> 실제 운영 경로에서 GPU 서버는 이 스크립트들이 아니라
> `WebApps/backend/models/trashdetect/tracking2.py`(TOP, `POST /api/events/aiDisposal`)와
> `WebApps/backend/models/trashoverflow/sideOverflow.py`(SIDE, `POST /api/binStates`)로
> 직접 판정 결과를 푸시한다(`.agentfiles/architecture.md`의 "탐지 파이프라인" 참고).
> 여기 있는 것들은 그 이전 단계의 데모/검증용이다.

## 1. HTTP 클라이언트 (라이브러리)

외부 패키지 없이 표준 라이브러리만 쓰는 얇은 HTTP 래퍼. 재시도 로직 포함.

| 파일 | 대상 API | 용도 |
|---|---|---|
| `detectionApiClient.py` | EP-08 `POST /api/detection/start`, EP-09 `POST /api/detection/stop` | 녹화 시작/종료(=탐지 시작/종료) 신호. 1회성 시작~종료 쌍 |
| `binStateApiClient.py` | EP-11 `POST /api/binStates`, EP-10 `GET /api/binStates` | 통 상태(NORMAL/FULL) 주기 보고. 위와 성격이 달라 일부러 분리함 |

각 파일 docstring에 호출 예시가 있다. 두 클라이언트의 단위 테스트는
`testDetectionApiClient.py`/`testBinStateApiClient.py`이며 저장소 루트에서 돌린다.

```bat
python -m pytest debug/detection
```

## 2. 파이프라인 시뮬레이터 (실행 스크립트)

HTTP를 거치지 않고 실제 API가 호출하는 **서비스 진입점을 그대로** 호출해서 백엔드 내부
파이프라인을 검증한다. 반드시 **프로젝트 루트에서, backend venv를 활성화하고** 실행한다.

```bat
python debug/detection/simulateEventPipeline.py
python debug/detection/simulateBinStatePipeline.py
```

- `simulateEventPipeline.py` — "이벤트 시작/종료" 두 신호를 흉내내서
  `recordingService`(녹화) → `mediaService`(GIF 인코딩) → GridFS 업로드 →
  `eventService`(이벤트 저장) 전체 흐름을 검증한다.
  MongoDB와 카메라(`.env`의 `CAMERA_SOURCE_ELEVTOP`, 미설정 시 기본값 `0`=로컬 웹캠)가 필요하다.
- `simulateBinStatePipeline.py` — `NORMAL→FULL→NORMAL` 상태 갱신을 흉내내서
  `binStateService`의 전환 판정 → overflow `EVENT` 생성/복귀를 검증한다. MongoDB가 필요하다.

## 3. `testDetectionApi.http`

VS Code REST Client 등으로 EP-08/EP-09를 손으로 호출해보는 요청 모음. 실행 스크립트가 아니다.

## 주의

두 시뮬레이터는 **실제 DB에 이벤트를 쓴다.** `.env`의 `MONGO_HOST`/`DB_NAME`이 팀 배포
서버를 가리키고 있지 않은지 먼저 확인할 것(`debug/db/README.md`의 접속 대상 규칙 참고).
