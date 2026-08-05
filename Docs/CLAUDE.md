# SortMaster 프로젝트 컨텍스트 (AI 참고용, agent.md 압축본 — 원본은 agent.md)

## 개요
- CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템. 1팀.
- 흐름: CCTV → 프레임분할 → 객체탐지 → 오분류판정 → (전구점등+경고음, 수거모드시 Mute) + 관리자페이지 실시간알림(테두리 빨강) → DB적재 → 통계
- 설치: 엘리베이터앞 2대(ELEV-01/02) + 4층휴게실 1대(REST-4F-01). 클래스(1차): general/paper/plastic/coffeeCup/오탐. 복합재질 클래스 TBD
- 안면인식(투기자 식별)은 본 레포 기본 미포함 (3팀 과제). 확장 여부 TBD

## 아키텍처 (5 컴포넌트)
디텍팅시스템 → 백엔드서버(API/기록/통계) → 관리자웹(스트리밍/기록/대시보드), 병렬로 → 현장알림(전구+스피커), 데이터저장소(MongoDB+GridFS)
- 레이어 강제: Controller→Service→Repository (Controller에서 DB 직접접근 금지)
- backend/ 하위: controllers/ services/ repositories/ models/ websocket/ streaming/ utils/
- 모델 미확정 상태 개발: 탐지결과는 랜덤/더미 Mock 함수로 대체, 나머지 파이프라인 먼저 완성 (모델 확정시 Mock만 교체)
- OpenCV `cv2.VideoCapture().read()`는 블로킹 — FastAPI async 핸들러에서 직접 호출 금지, `asyncio.to_thread()`/별도 스레드 사용
- MVP: 웹캠 또는 `/videos/sample.mp4`로 Mock Streaming, FPS 5~10 제한
- 탐지시스템↔백엔드 분리 여부 TBD (MVP는 한 프로세스 내 모듈로 권장)

## RPA(현장알림)
- 오분류 즉시 `RPAs/alertController.py` 비동기 호출 → soundPlayer + lightController **둘 다** 트리거 (하나만 구현 금지)
- MVP: 별도 HW/Webhook 없음, lightController는 콘솔로그/모의신호 가능 (GPIO 실제 연동 TBD)
- **수거모드(COLLECT) 중엔 전구·스피커·화면테두리 경고 전부 Mute** — 알림 트리거 직전에 항상 모드 체크

## DB/이벤트 적재
- 매 프레임 Insert 금지, **이벤트 발생시점에만** 저장 + **동일 카메라·클래스 5초 Cooldown**
- 이미지: MongoDB GridFS 확정. Mock단계에선 `imageFileId` 대신 더미 경로(`/debug/assets/sample_misclassified.jpg`) 반환
- DB 실제연동 보류 — 확정 전까지 인메모리/Mock으로 개발, 스키마 확정 후 Mock 계층만 교체
- 스키마(초안, camelCase):
```json
{"eventId":"uuid","timestamp":"ISO8601","cameraId":"ELEV-01|ELEV-02|REST-4F-01",
 "detectedClass":"general|paper|plastic|coffeeCup|mixed|uncertain","isMisclassified":"bool",
 "confidenceScore":"float","actionTaken":"lightAndSound|soundOnly|lightOnly|notificationOnly|none",
 "imageFileId":"string?(GridFS)","notes":"string?"}
```
- 통계 집계 컬렉션 별도설계 TBD

## API 명세 (고정 — 새 엔드포인트 임의 생성 금지, 필요시 여기에 먼저 추가)
| Method | Path | 설명 |
|---|---|---|
| GET | /api/stream | CCTV MJPEG 스트림 |
| POST | /api/events | 오분류 이벤트 생성 |
| GET | /api/events | 이벤트 목록 |
| GET | /api/events/{id} | 이벤트 상세 |
| GET | /api/statistics | 통계 조회 |
| POST | /api/mode | 관리/수거 모드 전환 |
| WS | /ws/events | 실시간 이벤트 브로드캐스트 |

## WebSocket 이벤트 규격 (고정)
```json
{"eventType":"MISCLASSIFICATION_DETECTED","cameraId":"ELEV-01","timestamp":"ISO8601","isMisclassified":true}
```
- eventType은 UPPER_SNAKE_CASE(예외), 나머지 필드는 camelCase
- eventType enum(고정): MISCLASSIFICATION_DETECTED, MODE_CHANGED, CAMERA_DISCONNECTED, SYSTEM_ERROR — 새 타입 필요시 먼저 문서에 추가

## Event Flow (고정 순서, 임의 재배치/생략 금지)
Detect → Create Event → Save Event(Mock) → Broadcast WebSocket → Trigger RPA(수거모드시 Mute) → Update Statistics

## 상태/모드 정의
- SystemState: MONITORING / ALERTING / COLLECTING / OFFLINE
- Mode(`POST /api/mode`): MANAGE(기본) / COLLECT

## Camera ID (고정, 절대 변경 금지)
ELEV-01, ELEV-02, REST-4F-01 만 사용 — 다른 형식(camera01 등) 금지

## 네이밍/스타일 규칙
- 변수/함수 camelCase, 클래스 PascalCase (Python도 snake_case로 임의 변경 금지)
- 예외: 프레임워크 강제 이름(`__init__` 등)이나 Pydantic 내부 필드는 `Field(alias=...)`로 camelCase 노출
- TBD 값은 하드코딩 금지, config로 분리 (아래 Config 표 참고)

## Config 목록
FPS(5~10), Cooldown(5초), AlarmDuration(TBD), ConfidenceThreshold(TBD, 모델확정후), SaveImage(bool), MockMode(true, 실연동시 false), DebugMode(true)

## 기술스택 (CTO 결정)
- DB: MongoDB(NoSQL), Docker(DB 전용만) / 로컬: Windows / Python 3.11 권장 / 백엔드: FastAPI 최신 + uvicorn[standard] / motor(비동기 드라이버)
- 프론트: React19+Vite+TypeScript, 네이티브 WebSocket, Tailwind CSS, Recharts
- 스트림 표시: MJPEG over HTTP (WebRTC/HLS 채택 안함)
- CORS: 개발단계 localhost:5173 허용(or `*`), 배포시 Origin 좁힐 것
- 객체탐지 모델·프레임워크: **보류**, YOLO는 후보일 뿐 확정 아님 — 확정 전 특정 프레임워크 설치/코드생성 금지
- MongoDB 버전/Docker 버전/브랜치전략: TBD

## 폴더 구조 (고정, 벗어난 폴더 임의생성 전 확인)
```
WebApps/backend/, WebApps/frontend/, Docs/skills/, RPAs/, debug/, videos/(git제외), .agentfiles/, .env.example, .gitignore
```
- .env·CCTV영상 파일 절대 Git 커밋 금지 (.gitignore: .env*, *.mp4/avi/mov/mkv, /videos/, /data/, *.pt/pth 등)
- .env는 Slack 공유, 새 환경변수 추가시 .env.example도 갱신

## 에러처리/로깅
- 카메라 연결실패 30초 재시도 후 CAMERA_DISCONNECTED 이벤트+알림
- DB 저장실패시 메모리 캐시 임시저장 후 재시도 (DB 연동 확정 후 적용)
- 로그레벨 INFO/WARN/ERROR/DEBUG, prefix [Camera]/[WebSocket]/[RPA]/[DB]

## 개발단계(Phase) / 우선순위
Phase1 Mock(현재) → Phase2 RTSP → Phase3 학습모델 → Phase4 실제RPA(HW) → Phase5 최적화
P0: 실시간영상/Mock탐지/오분류판정/RPA/WS브로드캐스트, P1: 기록조회/통계, P2: 검색·CSV, P3: 권한관리

## 일정
8/5 repo·DB템플릿 / 8/6 브랜치전략 교육 / 8/7~10 통합·스트리밍테스트 / 8/11 MVP중간점검 / CCTV입고후 실전연동

## 용어 통일
Detection(객체탐지), Misclassification(오분류), Event, Alert(전구+스피커), Record, Statistics, Stream(MJPEG), RPA — 유사어(Alarm/Warning/Notice 등) 혼용 금지

## 절대 금지사항
새 라이브러리 임의추가 / 폴더구조 이탈 / API명세·EventFlow·DB스키마·네이밍·CameraID 임의변경 — 전부 사용자 확인 필요

## TBD (미확정 — 임의 결정 금지, 항상 질문할 것)
DB 실제연동, 객체탐지 모델/프레임워크, 복합재질 클래스 정의, confidence threshold, 알림 UI/UX, 통계 세부지표, 런타임버전(탐지FW/Mongo/Docker), 모델가중치 공유방식, IDE별 debug 설정, 안면인식 포함여부, MCP 연결(MongoDB/GitHub/Filesystem MCP), Cooldown 5초 조정여부, 디텍팅↔백엔드 프로세스 분리여부, 경고전구 HW제어방식

## 작업 워크플로우 규칙 (사용자 지정, 2026-08-05)
**agent.md/CLAUDE.md의 확정 사항과 작업 요청이 상충하면 임의로 진행하지 말고 먼저 사용자에게 보고 → 진행/대안 여부를 사용자가 결정한 후 진행.**
