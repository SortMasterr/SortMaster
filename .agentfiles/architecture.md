# architecture.md

원본(source of truth). 다른 문서와 내용이 겹치면 이 문서 우선.

## 파이프라인

```
CCTV → 프레임분할 → 객체디텍팅 → 오분류 판정
  ├─ 탐지 시 → 현장알림(전구+경고음)
  └─ 결과전송 → 백엔드(수신API) → 기록/통계
→ 관리자웹(스트리밍/기록/통계, 오분류 시 테두리 빨간색)
```

- 목적: 행정직원 분리수거 감독 부담 경감
- 알림: 전구+스피커 항상 동시 트리거
- 안면인식(투기자 식별) 미포함, CTO 공통과제는 3팀 소관

## 설치 환경

| 항목 | 내용 |
|---|---|
| 위치 | 엘리베이터 2대(`ELEV-01`,`ELEV-02`), 4층 휴게실 1대(`REST-4F-01`) |
| 메인보드 | Jetson Nano, 입고 약 2주 소요 |
| 배포 구조 | 위치 3곳 각각 독립 메인보드+웹캠 |
| 클래스 | general, paper, plastic(coffeeCup 별도), mixed, uncertain |

## 탐지 파이프라인 (2단계 모델)

- **상시 감시(경량)**: YOLOv8-Nano 상주, ROI(쓰레기통 위치 고정) 내 객체 분석, 실시간 프레임 스캔, 메모리 ~300MB
- **트리거 조건**(ROI 내 객체 조합으로 즉시 판단):
  - 손 O + 쓰레기 O → **투기 이벤트**(=기존 오분류 탐지) → 정밀 분석 단계로
  - 손 X + 쓰레기 O → **넘침 이벤트**(쓰레기통 포화) → 정밀 분석 없이 영상 녹화만
- **정밀 분석(투기 이벤트만)**: 트리거 즉시 10초 고화질 영상 녹화(.avi) + YOLOv8-Medium 로드해 캔/페트/종이/기타 정밀 분류 → 분석 완료 후 모델 언로드+`gc.collect()`로 메모리 회수
- 2단계(Nano 상시감시+Medium 정밀분석) 전부 **중앙 GPU 서버에서 처리 확정** — 어차피 RTSP가 계속 중앙으로 들어오므로 엣지에서 중복 처리할 이유 없음, 48GB VRAM 대비 YOLO 계열 부하는 미미. 젯슨 나노는 캡처+RTSP 송신+GPIO 알림 수신만 담당(모델 미탑재)

## 추론 인프라

- NVIDIA L40S 4장 중 **1장만 할당** (타 팀과 공유). 학습/DB/백엔드 전부 이 1장 안에서 처리
- 메인보드 3대 → RTSP → 중앙(GPU 1장)에서 탐지 수행 (엣지 추론 아님)
- 탐지 모델 확정: YOLOv8-Nano(상시감시) + YOLOv8-Medium(정밀분석) — 상세는 위 "탐지 파이프라인" 참고

## 배포 전략

- 개발: Windows+Docker, 로컬 웹캠 테스트
- 배포: 동일 이미지를 할당받은 GPU 1장으로 이전
- MVP: 백엔드+DB+추론(학습 포함)을 GPU 서버 안에 전부 배포. 단 **GPU 연산 자체는
  탐지/추론 컨테이너만 사용**, DB/백엔드는 GPU 미사용(CPU/RAM만) — VRAM은
  탐지 모델 몫으로 남겨둠 (`docker run --gpus`는 추론 컨테이너에만 적용)
- 서버 CPU/RAM이 팀별로 분리되는지(GPU만 분리되는지)는 서버 관리자 확인 필요(TBD)
- GPU 패스스루: nvidia-docker 필요
- 영상 소스는 `.env`의 `CAMERA_SOURCE`만 환경별로 교체, 코드 불변

## 웹캠 시뮬레이션 (메인보드 입고 전)

- 웹캠 동시 다중 오픈 불가(OS 제약) → 단일 캡처 + 프레임을 3개 카메라ID에 복제
- 입고 후 CameraId별 독립 RTSP로 교체(이 부분만)
- `cv2.VideoCapture().read()` 동기 블로킹 → `async def` 직접 호출 금지, `asyncio.to_thread()` 필수

## 젯슨 나노 엣지 코드 (미착수)

역할은 캡처+RTSP 송신+GPIO뿐, 탐지 모델(Nano/Medium) 미탑재(전부 중앙 GPU 처리).

1. 웹캠→RTSP 송신: GStreamer(JetPack 포함) 예정. 1단계 웹캠 뷰어(Py 3.11)는 노트북 테스트 완료
2. 중앙 신호 수신→GPIO 트리거: 설계 전. `RPAs/alertController.py`는 현재 중앙에서 Mock 처리 중, 젯슨 쪽으로 이전 가능성. 전달 방식(MQTT/HTTP/WS) TBD

## RPA 정책

- 오분류 시 전구+경고음 즉시 자동 트리거(재전파 없음)
- `COLLECT` 모드: 알림 전부 Mute, 탐지 로직은 계속 동작(통계만 갱신)

## 이벤트 적재

- 매 프레임 Insert 금지, 이벤트 시점만 저장
- `eventCategory`로 구분: misclassification(투기, 정밀분류 결과 포함) / overflow(넘침, 분류 없이 영상만)
- 동일 카메라+클래스 5초 Cooldown(조정 TBD), overflow의 Cooldown 기준은 별도 TBD
- 이미지/영상은 MongoDB GridFS
- 학습용 원본 이미지 저장 방식 TBD(GridFS 재사용 vs GPU 서버 로컬 디스크)

## Event Flow

```
Detect → Create Event → Save Event → Check mode
  ├─ COLLECT: 통계만 갱신
  └─ MANAGE: WS Broadcast + RPA 트리거 → 통계 갱신
```

## 포트

| 항목 | 값 |
|---|---|
| 백엔드 | 8047 (기본값 8000 대신, 타 팀 충돌 방지) |
| MongoDB 호스트 | 27020 (컨테이너 내부 27017) |

## DB 접속 (팀 공유 vs 로컬)

- `.env`의 `MONGO_HOST/PORT/USER/PASSWORD`를 팀원마다 다르게 설정
  - 팀 공유: `MONGO_HOST=192.168.0.30`
  - 로컬(`my-mongo`): `MONGO_HOST=localhost`
- `infra/checkEnv.py`, `debug/testDbConnection.py`, `debug/testCrud.py` 세 스크립트가 `.env` 키 공유 — 값 다르면 결과 엇갈림
- 디버그 스크립트는 Atlas → 로컬/자체 Docker로 전환(`mongodb+srv://` → `mongodb://`+포트)

## TBD

- `mixed`/`uncertain` 클래스 세부 정의
- Cooldown 5초 조정 여부, overflow의 Cooldown 기준
- 경고 전구 HW/GPIO 연동, 젯슨↔중앙 신호 전달 방식
- 학습용 원본 이미지 저장 방식
- 안면인식 레포 포함 여부

## 해결된 TBD

- Git 브랜치 전략 → `Docs/skills/github/README.md`
- IDE/AI 코딩 툴 → 개인별 사용
- 탐지 모델/프레임워크 → YOLOv8-Nano(상시감시)+YOLOv8-Medium(정밀분석) 2단계 확정
