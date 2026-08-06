# CCTV 기반 분리수거 오분류 탐지·자동 경고 시스템

## 개발 환경 (버전 고정)

| 항목 | 버전/값 | 비고 |
|---|---|---|
| OS | Windows (로컬 개발) | 팀 공통 |
| Python | **3.11** | CTO 권장 버전, 반드시 3.11로 통일 |
| 패키지 관리 | `venv` + `pip` | requirements.txt 기준 |
| 웹 프레임워크 | FastAPI (최신 안정 버전) + `uvicorn[standard]` | requirements.txt에서 버전 관리 |
| DB 드라이버 | `motor` (비동기) | MongoDB 연동용 |
| DB 실행 | Docker | 호스트 포트 `27020`, 컨테이너 내부는 `27017` 유지 (팀 간 포트 충돌 방지) |
| MongoDB 버전 | **TBD** | Docker 이미지 태그로 고정 예정 (예: `mongo:7.0`) — 확정 전 임의 지정 금지 |
| Docker / Docker Compose 버전 | **TBD** | 팀 확정 후 여기에 기재 |
| 형상관리 | GitHub | 브랜치 전략 **TBD** (8/6 교육 예정) |
| IDE / AI 코딩 툴 | **TBD** | 팀 확정 후 여기에 기재 |
| 프론트엔드 | Node.js/React 사용 안 함 — Jinja2 + 바닐라 JS | 별도 런타임 설치 불필요 |

> **TBD 항목은 확정되는 대로 이 표를 업데이트해서 전원이 동일한 버전으로 맞춰야 함.**
> 특히 Python은 3.11 외 버전(3.12, 3.10 등) 사용 금지 — 라이브러리 호환성 문제 방지.

### 필수 설치 확인

```bash
python --version   # Python 3.11.x 인지 확인
docker --version   # Docker 설치 확인 (버전 TBD 확정 전까지는 최신 stable 사용)
git --version
```

## 실행 방법 (Windows 로컬 개발)

```bash
cd WebApps/backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

copy ..\..\.env.example .env
:: 필요 시 .env 값 수정 (CAMERA_SOURCE 등)

uvicorn main:app --reload --port 8000
```

브라우저에서 http://localhost:8000 접속.

## 현재 상태 (Mock 단계)

- **영상 소스**: 웹캠(`CAMERA_SOURCE=0`) 1개를 열어, 프레임을 3개 카메라ID
  (`ELEV-01`, `ELEV-02`, `REST-4F-01`)에 복제해서 스트리밍. 동일 웹캠을 여러 번
  열 수 없는 OS 제약 때문에 단일 캡처 + 프레임 공유 방식 사용.
- **탐지**: `services/detection_service.py` — 랜덤 클래스 + 임의 confidence Mock.
- **저장소**: `repositories/event_repository.py` — In-memory Mock (MongoDB 미연동).
- **RPA(전구/경고음)**: `services/rpa_service.py` — 콘솔 로그로 대체.
- **DB**: MongoDB Docker, 호스트 포트 `27020`(다른 팀과 충돌 방지, 컨테이너 내부는
  `27017` 유지) — 아직 연결 전, Mock Repository로 대체 중.

## 메인보드 입고 후 교체할 부분

1. `streaming/camera_manager.py` — 웹캠 단일 소스 → CameraId별 독립 RTSP 소스로 교체
2. `services/detection_service.py` — Mock 추론 → 확정된 탐지 모델로 교체
3. `repositories/event_repository.py` — In-memory → motor 기반 MongoDB 구현으로 교체
4. `services/rpa_service.py` — 콘솔 로그 → 실제 GPIO/HW 연동(`RPAs/` 참고)

## TBD (팀 논의 필요)

- 객체 탐지 모델/프레임워크
- 복합재질(`mixed`)/애매 쓰레기(`uncertain`) 클래스 세부 정의
- 오탐 confidence threshold (현재 `.env`에 임시값 0.7)
- MongoDB 버전, Docker/Compose 버전 (개발 환경 표 참고)
- Git 브랜치 전략, IDE/AI 코딩 툴 (개발 환경 표 참고)
- 통계 대시보드 세부 지표
- 안면인식(투기자 식별) 포함 여부 — 기본 제외