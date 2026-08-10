# CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템 (1팀)

## 개발 환경 (버전 고정)

| 항목 | 버전/값 | 비고 |
|---|---|---|
| OS | Windows (로컬 개발) | 팀 공통 |
| Python | **3.11** | CTO 권장 버전, 반드시 3.11로 통일 |
| 패키지 관리 | `venv` + `pip` | `infra/checkEnv.py`가 목록 관리(별도 requirements.txt 없음) |
| 웹 프레임워크 | FastAPI (최신 안정 버전) + `uvicorn[standard]` | 버전도 `infra/checkEnv.py`에서 관리 |
| DB 드라이버 | `motor` (비동기) | MongoDB 연동용 |
| DB 실행 | Docker | 호스트 포트 `27020`, 컨테이너 내부는 `27017` 유지 (팀 간 포트 충돌 방지) |
| MongoDB 버전 | **TBD** | Docker 이미지 태그로 고정 예정 (예: `mongo:7.0`) — 확정 전 임의 지정 금지 |
| Docker / Docker Compose 버전 | **TBD** | 팀 확정 후 여기에 기재 |
| 형상관리 | GitHub | 브랜치 전략은 `Docs/skills/github/README.md` 참고 |
| IDE / AI 코딩 툴 | 개인별 사용 | 팀 공통 지정 없음, 각자 편한 도구 사용 |
| 프론트엔드 | Node.js/React 사용 안 함 — Jinja2 + 바닐라 JS | 별도 런타임 설치 불필요 |

> **TBD 항목은 확정되는 대로 이 표를 업데이트해서 전원이 동일한 버전으로 맞춰야 함.**
> 특히 Python은 3.11 외 버전(3.12, 3.10 등) 사용 금지 — 라이브러리 호환성 문제 방지.

### 필수 설치 확인

```bash
python --version   # Python 3.11.x 인지 확인
docker --version   # Docker 설치 확인 (버전 TBD 확정 전까지는 최신 stable 사용)
git --version
```

패키지는 별도 requirements.txt 없이 `infra/checkEnv.py`가 직접
설치+체크까지 담당함(또는 `infra/checkEnv.bat` 더블클릭). Python 버전·필요 패키지
자동 설치·Docker 설치 여부·MongoDB(포트 27020) 접속을 한 번에 확인.

## 실행 방법 (Windows 로컬 개발)

```bash
cd WebApps/backend
python -m venv venv
venv\Scripts\activate

python ..\..\infra\checkEnv.py
:: 패키지 자동 설치 + Python/Docker/MongoDB 체크. 전부 OK가 아니면 여기서 먼저 해결

copy ..\..\.env.example .env
:: 필요 시 .env 값 수정 (CAMERA_SOURCE, USE_MOCK_DB 등)

uvicorn main:app --reload --port 8047
```

브라우저에서 http://localhost:8047 접속.
API 상세 스펙은 `.agentfiles/apiSpec.md` 참고.

## 현재 상태 (Mock 단계)

- **영상 소스**: 웹캠(`CAMERA_SOURCE=0`) 1개를 열어, 프레임을 3개 카메라ID
  (`ELEV-01`, `ELEV-02`, `REST-4F-01`)에 복제해서 스트리밍. 동일 웹캠을 여러 번
  열 수 없는 OS 제약 때문에 단일 캡처 + 프레임 공유 방식 사용.
- **탐지**: `services/detectionService.py` — 랜덤 클래스 + 임의 confidence Mock.
  (모델 미확정 상태라 여전히 Mock)
- **저장소**: `repositories/eventRepository.py` — `.env`의 `USE_MOCK_DB` 값으로
  In-memory Mock ↔ 실제 MongoDB(motor) 전환 가능. **DB 실연동 완료**, 로컬 Docker
  MongoDB(포트 27020)로 저장 테스트 확인됨.
- **RPA(전구/경고음)**: `services/rpaService.py` — 콘솔 로그로 대체(젯슨 나노 GPIO
  연동 전까지 유지).
- **DB**: MongoDB Docker, 호스트 포트 `27020`(다른 팀과 충돌 방지, 컨테이너 내부는
  `27017` 유지).

### 배포 전략

- 개발: Windows 노트북에서 Docker로 진행(로컬 웹캠 테스트)
- 배포: 동일 Docker 이미지를 그대로 학원 GPU 서버(Linux, **NVIDIA L40S 4장 중
  할당받은 1장**)로 이전
- 다른 팀들과 서버를 공유하기 때문에 4장 중 **1장만 할당**받아 사용. MVP 단계는
  백엔드(FastAPI)+모델 학습+DB 저장+탐지 추론을 **할당받은 GPU 1장 안에 전부
  통합 배포**(별도 상시 서버 불필요). GPU 패스스루는
  `nvidia-docker`(NVIDIA Container Toolkit) 필요.
- 로컬(웹캠)과 GPU 서버 배포(RTSP 수신/샘플 영상) 간 영상 소스는 `.env`의
  `CAMERA_SOURCE` 값만 다르게 관리(코드 변경 없음).

### 젯슨 나노(메인보드) 엣지 코드

메인보드 입고 전까지 별도 진행 중 (`webcamViewer.py` 등, 백엔드와는 다른 코드베이스):

1. **웹캠 캡처 → RTSP 송신**: 1단계(웹캠 뷰어) 노트북에서 테스트 완료. 다음 단계로
   GStreamer 기반 RTSP 송신 서버로 확장 예정 (JetPack 기본 포함).
2. **중앙 서버 알림 신호 수신 → GPIO 트리거**: 아직 설계 전. 현재 `RPAs/`는
   중앙 백엔드 안에서 Mock 처리 중인 자리만 잡아둔 상태 — 실제로는 젯슨 나노 쪽
   리스너로 옮겨야 할 가능성 높음. 신호 전달 방식(MQTT/HTTP/WebSocket)은 TBD.

## 메인보드 입고 후 교체할 부분

1. `streaming/cameraManager.py` — 웹캠 단일 소스 → CameraId별 독립 RTSP 소스로 교체
2. `services/detectionService.py` — Mock 추론 → 확정된 탐지 모델로 교체
3. ~~`repositories/eventRepository.py` — In-memory → motor 기반 MongoDB 구현으로 교체~~
   **완료** (`USE_MOCK_DB=false`로 전환하면 실제 MongoDB 사용)
4. `services/rpaService.py` — 콘솔 로그 → 실제 GPIO/HW 연동 (`RPAs/` 참고,
   젯슨 나노 쪽으로 이전 검토 중)

## TBD (팀 논의 필요)

- 객체 탐지 모델/프레임워크
- 복합재질(`mixed`)/애매 쓰레기(`uncertain`) 클래스 세부 정의
- 오탐 confidence threshold (현재 `.env`에 임시값 0.7)
- MongoDB 버전, Docker/Compose 버전 (개발 환경 표 참고)
- 통계 대시보드 세부 지표
- 안면인식(투기자 식별) 포함 여부 — 기본 제외
- 젯슨 나노 ↔ 중앙 서버 알림 신호 전달 방식(MQTT/HTTP/WebSocket)
- 학습용 원본 이미지 저장 방식 (MongoDB GridFS 재사용 vs GPU 서버 로컬 디스크 파일 축적)
