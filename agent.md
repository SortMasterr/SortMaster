# 프로젝트 컨텍스트 문서 (AI 개발 참고용)
> ⚠️ **과거 초안(비활성)**: 이 문서의 설치 위치, CameraId, 모델, DB/Mock 상태는 현재 구현과
> 충돌한다. 현재 source of truth는 `CLAUDE.md`가 연결하는
> `.agentfiles/architecture.md`, `.agentfiles/apiSpec.md`, `Docs/API_SPEC.md`,
> `Docs/ERD.md`다. 아래 내용은 결정 이력 참고용이며 구현 근거로 사용하지 않는다.
>
> 바이브 코딩 세션 시작 시 프로젝트 메모리로 사용. `CLAUDE.md`/`.cursorrules`로 저장.
> 목적: 프로젝트 배경 재추측 방지 (목적/범위, 파이프라인, DB/기술스택 결정, TBD)

---

## 1. 개요
- **팀**: 1팀 / **프로젝트**: CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템
- **목적**: 행정직원 분리수거 감독 부담 경감
- **흐름**: CCTV → 객체탐지 → 오분류 판단 → 전구점등+경고음(현장) + 관리자 페이지 알림 → DB 통계 → 대시보드
- **알림 수단**: 스피커 + 경고 전구 (둘 다)
- **UI 요구사항**: 오분류 시 실시간 스트리밍 화면 테두리 빨간색
- **안면 인식**: 본 파이프라인에 미포함. CTO 공통과제(ArcFace 등)는 3팀(출결) 소관, 1팀 레포 기본 제외. '투기자 식별' 확장 여부 TBD

---

## 2. 설치/수집 환경
| 항목 | 내용 |
|---|---|
| 설치 위치 | 엘리베이터 앞 2대, 4층 휴게실 1대 (총 3대) |
| 수집 방식 | 실시간 영상 스트림 |
| 클래스(1차) | 일반, 종이, 플라스틱(커피컵 별도), 오탐 |
| 추가 클래스 | 복합재질/애매 쓰레기 신설 여부 TBD |

---

## 3. 시스템 아키텍처

### 3-1. 컴포넌트 (5개)
1. 실시간 객체 디텍팅: 영상수신→프레임분할→탐지모델→오분류 판정
2. 데이터 저장소: 이미지 저장소 + 기록 DB(MongoDB)
3. 현장 물리 알림: 알림제어모듈 → 전구점등+경고음
4. 백엔드 서버: 영상전송, 결과수신 API, 기록/통계 관리
5. 관리자 웹: 사이드바(이전기록→상세, 수거/관리모드) / 실시간 스트리밍 / 통계 대시보드. 오분류 시 테두리 빨간색

### 3-2. 흐름 (개요)
```
[CCTV] → [프레임분할] → [객체디텍팅] → [오분류 판정]
  ├─ 탐지 시 → [현장알림: 전구+경고음]
  └─ 결과전송 → [백엔드: 수신API → 기록/통계]
→ [관리자웹: 스트리밍·기록·통계, 오분류 시 테두리 빨간색]
```

### 3-3. 상세 데이터 흐름
```
실시간 디텍팅 시스템
  ├─ 실시간 영상 → 백엔드(전송) → 관리자웹(스트리밍)
  ├─ 결과(오분류) → 백엔드(수신API) → 관리자웹(테두리 빨간색)
  ├─ 오분류 탐지 → 현장알림(알림제어) → 전구/스피커
  └─ 이미지 저장 → 데이터저장소

백엔드 서버
  ├─ 수신 데이터 → DB(기록) + 통계처리
  └─ 기록관리 → 관리자웹(이전기록→상세)
```

### 3-4. 물리 파이프라인 (RTSP)
```
CCTV(RTSP) → OpenCV 영상수신 → 프레임 단위 추론 ⚠️모델 보류
```
- **모델 보류**: YOLO 버전/커스텀학습/클래스매핑 등 미확정. 임의 구현 금지 (4-1, 9번)
- **MVP(8/7~8/10)**: 웹캠 또는 `/videos/sample.mp4`로 Mock Streaming, FPS 5~10 제한
- **모델 미확정 시 진행**: 나머지 파이프라인은 Mock 추론 함수(랜덤 클래스+임의 confidence)로 우선 개발, 모델 확정 시 함수만 교체
- **디텍팅↔백엔드 분리 여부**: TBD (9번). MVP는 한 프로세스 내 모듈 분리 권장
- **⚠️ OpenCV 블로킹 방지**: `cv2.VideoCapture().read()`는 동기 블로킹 — `async def` 안 직접 호출 금지, `asyncio.to_thread()`/스레드 분리 필수 (8-18)

### 3-5. 현장 알림(RPA)
- 오분류 탐지 시 즉시 전구점등+경고음 둘 다 (자동 대응이 핵심, 관리자 재전파 없음)
- MVP: HW/Webhook 없이 `RPAs/alertController.py` 비동기 호출. `soundPlayer`(오디오 재생) + `lightController`(경고등, MVP는 콘솔로그/모의신호 대체, GPIO/HW는 TBD) 둘 다 트리거

### 3-6. 이벤트 적재 정책
- 매 프레임 Insert 금지 — **이벤트 발생 시점만** 저장
- **Cooldown**: 동일 카메라+클래스 5초간 재적재 금지 (기본값, 조정 여부 TBD)
- **이미지**: MongoDB GridFS 확정 (별도 인프라 없이 기존 Docker 컨테이너 재사용, 저장량 적어 규모 적합)
- **Mock 단계**: `imageFileId` 대신 더미 경로(예: `/debug/assets/sample_misclassified.jpg`) 반환, GridFS 연동 확정 시 교체
- 오탐/복합쓰레기 전용 DB 별도 구축해 대시보드 시각화 (회의 피드백)

### 3-7. WebSocket 메시지 규격 (백엔드→프론트, 고정)
```json
{"eventType": "MISCLASSIFICATION_DETECTED", "cameraId": "ELEV-01", "timestamp": "ISO8601", "isMisclassified": true}
```
- `eventType`은 대문자 스네이크케이스(7번 camelCase 규칙 예외), 필드값은 camelCase
- 새 이벤트 타입 필요 시 이 표에 먼저 추가 후 구현 (임의 문자열 금지)

### 3-8. 수거 모드
- 활성화 시: 전구/스피커 알림 + 화면 테두리 경고 **Mute**
- 오분류 탐지 로직 자체는 계속 동작, **알림/UI 트리거 단계에서만 모드 확인 후 스킵**
- 관리 모드 복귀 시 알림 정상 재개

---

## 4. 기술 스택 (CTO 결정)
| 영역 | 결정 |
|---|---|
| DB | MongoDB (스키마 유연성, JSON 처리) |
| DB 실행 환경 | Docker (DB 전용) |
| 로컬 개발 | Windows |
| 형상관리 | GitHub, 브랜치 전략 교육 예정(8/6) |
| AI 개발 보조 | MCP + 바이브 코딩 스킬 (4-2 참고) |
| 객체 탐지 모델 | 보류 (YOLO 계열 후보 언급뿐, 미확정) |
| 백엔드 언어 | Python |
| AI 코딩 툴/IDE | 미정, 범용 문서로 작성 |

### 4-1. 언어/런타임 버전
> 버전 불일치 시 AI가 신/구 문법 혼용 문제 발생 — 확정 즉시 아래에 고정

| 항목 | 값 | 비고 |
|---|---|---|
| Python | `3.11 권장` | CV 스택(YOLO/PyTorch) 지원 고려, 확정 후 `python --version`으로 고정 |
| 객체 탐지 프레임워크 | 보류 | 팀 논의 후 확정, 확정 전 특정 프레임워크 코드 생성 금지 |
| 웹 백엔드 | `FastAPI(최신 안정, 예 0.141.x)` + `uvicorn[standard]` | 설치 시 `pip freeze`로 버전 고정 |
| MongoDB 드라이버 | `motor`(비동기) | 단순 CRUD면 `pymongo`도 가능 |
| MongoDB 버전 | TBD | Docker 이미지 태그로 고정(예 `mongo:7.0`) |
| Docker/Compose 버전 | TBD | |
| Node.js | **사용 안 함** | Jinja2 전환으로 Node 빌드 불필요 |
| Git 브랜치 전략 | TBD | 8/6 교육 이후 확정 |
| 프론트엔드 렌더링 | **Jinja2(FastAPI 서버사이드 템플릿)** | React SPA 완전 제거, `templates/`의 `.html` 직접 렌더링 |
| 프론트엔드 언어 | **바닐라 JavaScript** | `static/js/`에 페이지별 스크립트, 번들러 없음 |
| 실시간 알림(프론트) | 네이티브 `WebSocket` API | socket.io 등 불필요 |
| 영상 스트림 표시 | **MJPEG over HTTP**(`StreamingResponse`, `multipart/x-mixed-replace`) | 카메라 3대 규모에 적합, WebRTC 과함/HLS 지연 큼 |
| 통계 차트 | **Chart.js** | **로컬 파일 서빙**(`static/js/lib/chart.umd.js`, CDN 아님 — 폐쇄망/불안정망 대비), 기본 차트로 충분해 확정 |
| 스타일링 | **순수 CSS** | Tailwind CDN 프로덕션 비권장·빌드 필요해 배제, 페이지 적어 `static/css/main.css`로 충분 |
| CORS | **미들웨어 불필요(제거)** | 프론트/백엔드 같은 origin(FastAPI가 둘 다 서빙) |
| OS | Windows(버전 미정) | |

### 4-2. 관리자 웹 IA
```
메인 관리자 페이지
├── 사이드바: 이전기록→상세 / 수거모드·관리모드(기본값)
├── 실시간 스트리밍 (카메라 3대 동시 표시, 오분류 시 해당 카메라 테두리 빨간색)
└── 통계 대시보드
```

### 4-3. MCP 서버 (TBD)
| MCP | 용도 | 상태 |
|---|---|---|
| MongoDB MCP | DB 조회/집계 | TBD |
| GitHub MCP | 이슈/PR, 브랜치 자동화 | TBD |
| Filesystem MCP | 로컬 파일 탐색/편집 | TBD |
> 확정 전까지 연결된 것으로 가정 금지

---

## 5. DB 스키마 (⚠️ 실연동 보류, Mock 우선)
> 확정 전까지 실제 MongoDB 연결 코드 금지 — 인메모리/Mock 계층으로 대체. 필드명 camelCase. 적재는 이벤트 발생 시점만 + 5초 Cooldown.

```json
{
  "eventId": "string (uuid)",
  "timestamp": "ISO8601",
  "cameraId": "string (ELEV-01|ELEV-02|REST-4F-01)",
  "detectedClass": "general|paper|plastic|coffeeCup|mixed|uncertain",
  "isMisclassified": "boolean",
  "confidenceScore": "float",
  "actionTaken": "lightAndSound|soundOnly|lightOnly|notificationOnly|none",
  "imageFileId": "string (GridFS ObjectId, optional)",
  "notes": "string (optional)"
}
```
- 통계 집계용 컬렉션(일별/클래스별)은 별도 설계 필요 (TBD)

---

## 6. 폴더 구조

```
project-root/
├── WebApps/
│   └── backend/            # FastAPI (⚠️ frontend/ 제거 — backend가 화면까지 서빙)
│       ├── templates/      # Jinja2 템플릿
│       └── static/         # CSS, JS, 이미지
├── Docs/skills/            # 스킬/문서 자료
├── RPAs/                   # 현장 알림 트리거 소스
├── debug/                  # F5 디버그(test API 세팅)
├── videos/                 # Mock Streaming용 영상 (Git 제외)
├── .agentfiles/            # AI 컨텍스트 파일(본 문서 포함)
├── .env.example
├── .gitignore
└── README.md
```

- `WebApps/backend/`: ⚠️ 기존 `frontend/`(React+Vite) 제거, `backend/`로 통합. 재생성 금지
- `.env.example`: 변수 키 목록만, 실제 값 금지 (`.env`는 Git 제외, Slack 공유)
- `.agentfiles/`: 본 문서 등 AI 컨텍스트 파일 보관
- `debug/`: 실제 CCTV 연동 전 test API로 F5 즉시 구동. FastAPI 단일 서버라 백엔드/프론트 동시실행 설정 불필요(⚠️변경). Mock API 서버 실행 스크립트, 더미 데이터 생성 스크립트(`debug/seedData.py`, 5번 스키마 기준) 포함

### 6-1. `.gitignore` 필수 항목
```gitignore
# 환경변수
.env
.env.*
!.env.example

# CCTV 영상/이미지
*.mp4
*.avi
*.mov
*.mkv
/data/cctv/
/videos/
/data/raw/

# Python
__pycache__/
*.pyc
.venv/
venv/

# IDE/OS
.vscode/settings.json
.DS_Store
Thumbs.db

# 모델 가중치 (용량 크면 Git LFS/별도공유 TBD)
*.pt
*.pth
```

---

## 7. 개발 일정
| 일자 | 내용 |
|---|---|
| 8/5 | GitHub repo 생성, DB 연동 템플릿, Docker DB 세팅 |
| 8/6 | GitHub 교육, 업무분장 확정 |
| 8/7~8/10 | 임시데이터 수집, 프론트/백엔드 연결, 스트리밍 테스트 |
| 8/11 | 목업/MVP 중간 점검 |
| CCTV 입고 후 | 실전 연동, 모델 재학습, RPA 통합 |

---

## 8. AI 요청 규칙
1. 클래스 정의 확정 전 임의 추가/변경 금지 — 질문할 것
2. DB 스키마 변경은 5번 기준, 임의 필드 추가 시 사용자 확인. 실연동 보류 — Mock/인메모리로 대체
3. 개발 환경은 Windows 로컬+Docker(DB 전용) 유지, 컨테이너화 제안 시 확인
4. RPA는 "오분류 즉시 현장 경고"가 핵심. 수거 모드 중엔 Mute (3-8)
5. `.env`/CCTV 영상 Git 커밋 코드 생성 금지
6. 6번 폴더 구조 밖 임의 생성 전 확인
7. **네이밍**: 변수/함수 `camelCase`, 클래스 `PascalCase` (PEP8 snake_case 아님, DB/JSON도 camelCase)
   - 예외: 프레임워크 강제 이름(`__init__`, `lifespan` 등), Pydantic 내부 snake_case 필드는 `Field(alias=...)` 사용
8. TBD 항목은 하드코딩 금지, config로 분리
9. RPA는 `RPAs/alertController.py` 비동기 호출로 우선 구현, 전구+경고음 둘 다 트리거. HW/Webhook 임의 변경 금지
10. DB 적재는 이벤트 시점만 + 동일 카메라·클래스 5초 Cooldown — 프레임마다 Insert 금지
11. MVP 영상은 Mock Streaming 기준, FPS 5~10 제한 — 실제 RTSP 연동 코드는 CCTV 입고 전까지 금지
12. 4-3 미확정 MCP를 연결된 것으로 가정 금지
13. 오분류 시 스트리밍 테두리 빨간색 요구사항 항상 반영
14. 객체 탐지 모델 보류 — 학습/프레임워크 설치/클래스 매핑 임의 진행 금지, Mock 추론 함수로 대체
15. WebSocket은 3-7 고정 포맷 준수, 새 이벤트 타입은 문서 먼저 추가 후 구현
16. Mock 단계 이미지 응답은 더미 경로 반환, GridFS 코드는 DB 연동 확정 전 금지
17. **CORS**: ⚠️ `CORSMiddleware` 사용 안 함(Jinja2로 같은 origin). 임의 추가 금지, 필요 시(외부 클라이언트 발생) 팀 확인 후 추가
18. **OpenCV 블로킹 방지**: `cv2.VideoCapture().read()` 동기 블로킹 — `async def`/WebSocket 루프 안 직접 호출 금지, `asyncio.to_thread()`/`threading.Thread` 분리
19. `.env.example` 유지, 신규 환경변수 추가 시 함께 갱신 (실값 금지)
20. API는 11번 명세 엔드포인트만 사용, 신규 필요 시 표에 먼저 추가
21. Controller→Service→Repository 강제, Controller에서 DB 직접 접근 금지
22. 22번(금지사항) 우선 확인 — 라이브러리/폴더/API/Event Flow/DB Schema/네이밍/Camera ID 임의 변경 금지
23. **JS는 `.html` 내부 `<script>`에 직접 작성 금지, `static/js/` 하위 `.js` 파일로 분리할 것** — Jinja2 `{{ }}`와 JS 템플릿 리터럴 `${ }`의 `{}` 충돌로 SyntaxError 발생 흔함. 템플릿→JS 값 전달은 `<script>window.__X__={{ value }}</script>` 한 줄만 허용
24. **View(HTML 반환)와 API(JSON/WS 반환)는 컨트롤러 파일을 분리할 것** (`controllers/views.py` / `controllers/api.py`, 11-1·11-2 참고) — 한 파일에 섞지 말 것
25. **`POST /api/mode` 성공 시 `MODE_CHANGED`를 `/ws/events` 전체 클라이언트에 브로드캐스트할 것** (16번) — 다른 탭/관제 PC에 모드 전환 즉시 반영 필요
26. **`main.py`에 `StaticFiles(directory="static")`를 `/static`으로 마운트할 것** — 없으면 템플릿의 `<script src="/static/...">`가 전부 404
27. `CameraId(str, Enum)`은 Pydantic v2가 `"ELEV-01"` 문자열을 자동으로 Enum 멤버로 변환함 — 커스텀 validator 작성 불필요, 목록에 없는 값은 자동 422
28. `pydantic-settings`는 Pydantic 코어와 분리된 별도 패키지 — `requirements.txt`에 `pydantic-settings` 명시할 것 (누락 시 `ImportError`)

---

## 9. TBD (팀 논의 필요)
- [ ] DB(MongoDB) 실연동 (5번)
- [ ] 객체 탐지 모델/프레임워크 자체
- [ ] 복합재질/애매 쓰레기 클래스 정의·라벨링 기준
- [ ] 오탐 판정 confidence threshold
- [ ] 프론트엔드 실시간 알림 UI/UX 형태
- [ ] 통계 대시보드 세부 지표
- [ ] 언어/런타임 버전(4-1): 탐지 프레임워크, MongoDB, Docker 버전
- [ ] 모델 가중치(.pt) 공유 방식(Git LFS/Slack/별도 스토리지)
- [ ] AI 코딩 툴/IDE 확정 시 `debug/` F5 설정 반영
- [ ] 안면 인식('투기자 식별') 1팀 레포 포함 여부
- [ ] MCP 서버 확정(4-3)
- [ ] Cooldown 5초 조정 여부
- [ ] 디텍팅 시스템·백엔드 프로세스 통합/분리 여부(3-4)
- [ ] 경고 전구 HW/GPIO 실연동 방식
- [ ] WebSocket `detectedClass` 필드 추가 여부 (설계문서 제안, 팀 확인 필요)

---

## 10. 팀 역할
- PM: 목표 수립, 파이프라인 전체 이해, 서비스/사용자 관점
- CTO: 구현 기술 검토, 오탐/성능 이슈, DB/서버 아키텍처

---

## 11. API 명세 (고정 — 임의 엔드포인트 생성 금지)
### 11-1. JSON API (`controllers/api.py`)
| Method | Path | 설명 | Query/Body |
|---|---|---|---|
| GET | `/api/stream/{cameraId}` | 카메라별 CCTV 영상 스트림(MJPEG, cameraId는 13번 Enum) | - |
| POST | `/api/events` | 오분류 이벤트 생성 | Body: `cameraId, detectedClass, isMisclassified, confidenceScore` |
| GET | `/api/events` | 이벤트 목록(이전 기록) | Query: `cameraId?, detectedClass?, from?, to?, limit=20, offset=0` |
| GET | `/api/events/{id}` | 이벤트 상세 | - |
| GET | `/api/statistics` | 통계 조회 | Query: `from?, to?` (미지정 시 전체) → Response: `{labels: string[], counts: number[]}` (클래스별 집계) |
| POST | `/api/mode` | 관리/수거모드 전환 | Body: `{"mode": "MANAGE" \| "COLLECT"}` → Response: `{"mode": "..."}` |
| WS | `/ws/events` | 실시간 브로드캐스트 | 16번 참고 (eventType별 payload 상이) |

- **Statistics 갱신 기준**: 서버는 별도 캐시/증분 갱신 없이 **호출 시점에 `EventRepository.list()`를 집계해 반환**(온디맨드, MVP 이벤트량에선 충분). 대시보드의 `chart.update()`(Chart.js)는 WebSocket 수신 시 **클라이언트 로컬 카운터만 증가**시키는 낙관적 갱신이며 서버 재계산이 아님 — 페이지 새로고침 시 `GET /api/statistics`로 진실 값 재동기화됨

### 11-2. 페이지(View) 라우트 (`controllers/views.py`, Jinja2 전환에 따른 신규)
| Method | Path | 템플릿 |
|---|---|---|
| GET | `/` | `index.html` (메인, 스트리밍+최근 이벤트) |
| GET | `/events` | `events_list.html` |
| GET | `/events/{id}` | `event_detail.html` |
| GET | `/statistics` | `statistics.html` |
- View는 `TemplateResponse`만 반환(JSON 아님), JSON API와 컨트롤러 파일 분리(`views.py`/`api.py`)
- `GET /`는 `SystemState`의 현재 모드를 템플릿 컨텍스트로 함께 넘겨 초기 렌더링에 반영 (새로고침 시 상태 초기화 방지)

---

## 12. Event Flow (고정)
```
Detect → Create Event → Save Event(Mock/인메모리)
→ Check SystemState.mode
    ├─ COLLECT(수거모드): Update Statistics만 수행 (Broadcast/RPA 스킵 — 3-8)
    └─ MANAGE(관리모드): Broadcast WebSocket(3-7) + Trigger RPA(전구+스피커) → Update Statistics
```
- ⚠️ **변경**: 기존엔 Broadcast WebSocket → Trigger RPA(Mute 체크) 순서라 수거모드에서도 화면 테두리(WS 수신)가 떴음. 3-8은 RPA뿐 아니라 **화면 테두리 표시도 Mute 대상**이므로, 모드 체크를 Save Event 직후로 올려 Broadcast/RPA를 함께 게이팅
- 각 단계 독립 함수/서비스로 분리 (14번)

---

## 13. Camera ID (고정 — 변경 금지)
- 허용값: `ELEV-01`, `ELEV-02`, `REST-4F-01` (이 외 임의 생성 금지, 형식 변형 금지)
- 카메라 추가/변경 시 이 표 먼저 갱신 후 코드 반영
- **Python 구현은 문자열이 아닌 Enum으로 고정** (오타 방지, `models/constants.py`):
```python
from enum import Enum
class CameraId(str, Enum):
    ELEV_01 = "ELEV-01"
    ELEV_02 = "ELEV-02"
    REST_4F_01 = "REST-4F-01"
```
- `Event.camera_id` 등 모델 필드 타입을 `CameraId`로 지정 (str이 아님)

---

## 14. 아키텍처 원칙 (고정)
```
AI Model → Detection Service → Event Service → RPA Service
→ Repository(현재 Mock, DB 확정 시 MongoDB) → MongoDB(보류) → WebSocket → Frontend
```
- Controller→Service→Repository 강제, Controller의 직접 DB 접근 금지
- `backend/` 구조 (⚠️ `templates/`,`static/`,`state/` 추가):
```
backend/
├── controllers/    # views.py(페이지)+api.py(JSON/WS) 분리
├── services/       # Detection/Event/RPA Service
├── repositories/   # 데이터 접근 (현재 Mock)
├── models/         # Pydantic 모델 (+ constants.py: CameraId 등 Enum)
├── websocket/       # WS 연결·브로드캐스트
├── streaming/       # MJPEG (VideoCaptureManager/FrameBuffer)
├── state/          # SystemState(Mode 보관 싱글톤)
├── templates/      # Jinja2 템플릿
├── static/         # CSS/JS/이미지
└── utils/          # logger.py 등
```

### 14-1. Service 책임 (신규 명세)
| Service | 책임 | 주요 메서드(예시) |
|---|---|---|
| `DetectionService` | 프레임 추론 실행(Mock/실제), 오분류 여부 판정 | `infer(frame) -> DetectionResult` |
| `EventService` | 이벤트 생성/Cooldown 체크/저장, Mode 확인 후 Broadcast+RPA 게이팅(12번) | `handle_detection(result)`, `list_recent()` |
| `RPAService` | `RPAs/alertController.py` 비동기 호출(전구+스피커) | `trigger_alert(camera_id)` |
- Controller는 위 Service만 호출, Service 간 직접 호출은 `EventService → RPAService` 방향만 허용 (역방향 금지)

### 14-2. Model 명칭 분리 (신규 — 요청/응답 모델 구분)
> 기존엔 `Event` 모델 하나를 요청(`POST /api/events`)과 응답에 동일하게 사용 — 요청엔 없는 `eventId/timestamp/actionTaken/imageFileId`가 섞여 혼동 가능. 아래처럼 분리:
- `EventCreate` (요청 전용): `cameraId, detectedClass, isMisclassified, confidenceScore`
- `Event` (응답/저장 전용, `CamelModel` 상속): `EventCreate`의 필드 + `eventId, timestamp, actionTaken, imageFileId, notes` (서버가 채움)

---

## AI 행동 원칙 (신규)
1. 기존 파일 우선 수정 — 새 파일보다 기존 파일 확장을 먼저 검토
2. 새 파일 생성 최소화 — 6번 폴더 구조 안에서, 꼭 필요한 경우만
3. 기존 코드 스타일 유지 (7번 네이밍, 8번 규칙 그대로 따름)
4. TODO 주석으로 남기지 말고 끝까지 구현 — 불가능하면 이유를 명시하고 질문
5. 모르는 것은 임의로 넘기지 말고 질문
6. 명세에 없는 부분은 추측 구현 금지 — 9번 TBD 항목이면 Mock/설정값으로 대체하고 질문

---

## 15. 상태 정의 (고정)
> ⚠️ **변경**: 기존 `SystemState`(MONITORING/ALERTING/COLLECTING/OFFLINE)와 `Mode`(MANAGE/COLLECT)가 의미 중복(COLLECTING≈COLLECT). `state/system_state.py`의 `SystemState` 클래스는 `Mode`를 담는 싱글톤으로 이미 확정되어 있어(7번 설계문서), 이름 충돌도 있었음 → 카메라 연결 상태만 별도 Enum으로 분리하고 나머지는 `Mode`로 통일

**CameraStatus** (카메라별 연결 상태, 17번 에러처리 연동)
- `ONLINE` / `OFFLINE`

**Mode** (시스템 전역, `POST /api/mode`로 전환, `state/system_state.py`의 `SystemState` 싱글톤이 보관)
- `MANAGE` — 관리 모드(기본값) / `COLLECT` — 수거 모드

---

## 16. `eventType` Enum 및 WebSocket payload (고정, 3-7 확장)
> 기존엔 `MISCLASSIFICATION_DETECTED`만 payload가 정의돼 있었음 — 나머지 3종도 고정

| eventType | payload 필드 | 비고 |
|---|---|---|
| `MISCLASSIFICATION_DETECTED` | `cameraId, timestamp, isMisclassified` | detectedClass 추가 여부는 9번 TBD |
| `MODE_CHANGED` | `mode, timestamp` | `mode`: `MANAGE`\|`COLLECT` |
| `CAMERA_DISCONNECTED` | `cameraId, timestamp` | 17번 에러처리 연동 |
| `SYSTEM_ERROR` | `message, timestamp` | |

- **연결 시**: `/ws/events` 접속(accept) 즉시 서버가 그 클라이언트에게만 현재 Mode를 담은 `MODE_CHANGED` 1회 전송 (재연결 시 상태 동기화용, GET / SSR 하이드레이션과 별개)
- **`POST /api/mode` 성공 시**: 반드시 전체 클라이언트에 `MODE_CHANGED` 브로드캐스트 (다른 탭/PC 화면도 즉시 반영, 8번 규칙)

> 신규 타입/필드는 이 표에 먼저 추가 (임의 문자열 금지, 8-15)

---

## 17. 에러 처리
- 카메라 연결 실패: 재시도 → 30초 초과 시 `CameraStatus=OFFLINE` 전환 + `CAMERA_DISCONNECTED` 이벤트 + WebSocket 알림
- DB 저장 실패: 메모리 캐시 임시 저장 → 재시도 (실 Mongo 연동 후 적용)

---

## 18. Logging
- 레벨: `INFO`/`WARN`/`ERROR`/`DEBUG`
- Prefix: `[Camera]`/`[WebSocket]`/`[RPA]`/`[DB]`
- 예: `[Camera] INFO 카메라 ELEV-01 연결됨`
- **구현**: 표준 `logging` 모듈 사용, `utils/logger.py`에서 모듈별 logger를 `logging.getLogger(f"[{prefix}]")`로 생성해 재사용 (print 금지)

---

## 19. Config (하드코딩 금지)
| 설정 | 기본값 | 비고 |
|---|---|---|
| FPS | 5~10 | Mock Streaming 기준 |
| Cooldown | 5초 | 동일 카메라·클래스 (조정 여부 TBD) |
| AlarmDuration | TBD | 전구/스피커 지속시간 |
| ConfidenceThreshold | TBD | 모델 확정 후 결정 |
| SaveImage | true/false | Mock 단계 더미 경로 |
| MockMode | true | 모델·DB 보류 반영, 실연동 시 false |
| DebugMode | true(개발) | 개발/배포 구분 |

- **구현**: `pydantic-settings`의 `BaseSettings`로 `config/settings.py`에 1개 클래스로 정의, `.env` 값 자동 로드. 코드 내 하드코딩된 상수 금지, 전부 `settings.XXX`로 참조
- ⚠️ `pydantic-settings`는 Pydantic 코어와 별도 패키지 — `pip install pydantic-settings` 필요(`requirements.txt`에 명시, 누락 시 `ImportError`)
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    fps: int = 10
    cooldown_sec: int = 5
    mock_mode: bool = True
    debug_mode: bool = True
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 20. 개발 Phase
1. Mock — 웹캠/샘플영상+Mock추론+인메모리 (현재)
2. RTSP — 실제 CCTV 연동 (입고 후)
3. 학습 모델 — 확정 및 교체
4. 실제 RPA — HW/GPIO 연동
5. 최적화

---

## 21. 기능 우선순위
- P0: 실시간 영상, 탐지(Mock), 오분류 판정, RPA, WebSocket
- P1: 기록 조회, 통계 대시보드
- P2: 검색/필터, CSV 내보내기
- P3: 권한 관리

---

## 22. 금지사항
- 새 라이브러리 임의 추가 (확인 필요)
- 6번 폴더 구조 밖 임의 폴더
- 11번 API 엔드포인트 이름 임의 변경
- 12번 Event Flow 구조 임의 변경
- 5번 DB Schema 임의 변경 (실연동 보류)
- 7번 네이밍 규칙 임의 변경 (예외는 규칙 7)
- 13번 Camera ID 규칙 임의 변경 (문자열 임의 생성 포함, Enum 사용)
- Node.js/React/Vite/TypeScript 재도입 금지 (Jinja2+바닐라 JS 확정, 4-1)
- `CORSMiddleware` 재도입 금지 (같은 origin, 8-17)
- Tailwind CDN 재도입 금지 (순수 CSS 확정, 4-1)
- Chart.js CDN 로드 금지 (`static/js/lib/` 로컬 파일만, 4-1)
- `.html` 내부 `<script>`에 JS 로직 직접 작성 금지 (8-23)
- `controllers/views.py`·`api.py` 혼용 금지 (8-24)

---

## 23. 용어집
| 용어 | 정의 |
|---|---|
| Object Detection | 객체 탐지 |
| Misclassification | 오분류 |
| Event | 오분류 발생 기록 |
| Alert | 현장 알림(전구+스피커) |
| Record | DB 저장 데이터 |
| Statistics | 집계 데이터 |
| Stream | 실시간 영상(MJPEG) |
| RPA | 현장 물리 알림 시스템 |
> `Detection`/`Alarm`/`Warning`/`Notice`/`Notification` 등 유사어 혼용 금지
