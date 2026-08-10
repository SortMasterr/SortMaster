# architecture.md

원본(source of truth). agent.md 3/12~17번과 겹치면 이 문서 우선.

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

## 추론 인프라

- NVIDIA L40S 4장 중 **1장만 할당** (타 팀과 공유). 학습/DB/백엔드 전부 이 1장 안에서 처리
- 메인보드 3대 → RTSP → 중앙(GPU 1장)에서 탐지 수행 (엣지 추론 아님)
- 탐지 모델/프레임워크 보류(YOLO 후보뿐, 미확정) — 확정 전 임의 구현 금지

## 배포 전략

- 개발: Windows+Docker, 로컬 웹캠 테스트
- 배포: 동일 이미지를 할당받은 GPU 1장으로 이전
- MVP: 백엔드+학습+DB+추론 전부 GPU 1장에 통합 배포
- GPU 패스스루: nvidia-docker 필요
- 영상 소스는 `.env`의 `CAMERA_SOURCE`만 환경별로 교체, 코드 불변

## 웹캠 시뮬레이션 (메인보드 입고 전)

- 웹캠 동시 다중 오픈 불가(OS 제약) → 단일 캡처 + 프레임을 3개 카메라ID에 복제
- 입고 후 CameraId별 독립 RTSP로 교체(이 부분만)
- `cv2.VideoCapture().read()` 동기 블로킹 → `async def` 직접 호출 금지, `asyncio.to_thread()` 필수

## 젯슨 나노 엣지 코드 (미착수)

1. 웹캠→RTSP 송신: GStreamer(JetPack 포함) 예정. 1단계 웹캠 뷰어(Py 3.11)는 노트북 테스트 완료
2. 중앙 신호 수신→GPIO 트리거: 설계 전. `RPAs/alertController.py`는 현재 중앙에서 Mock 처리 중, 젯슨 쪽으로 이전 가능성. 전달 방식(MQTT/HTTP/WS) TBD

## RPA 정책

- 오분류 시 전구+경고음 즉시 자동 트리거(재전파 없음)
- `COLLECT` 모드: 알림 전부 Mute, 탐지 로직은 계속 동작(통계만 갱신)

## 이벤트 적재

- 매 프레임 Insert 금지, 이벤트 시점만 저장
- 동일 카메라+클래스 5초 Cooldown(조정 TBD)
- 이미지는 MongoDB GridFS
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

- 탐지 모델/프레임워크
- `mixed`/`uncertain` 클래스 세부 정의
- Cooldown 5초 조정 여부
- 경고 전구 HW/GPIO 연동, 젯슨↔중앙 신호 전달 방식
- 학습용 원본 이미지 저장 방식
- 안면인식 레포 포함 여부

## 해결된 TBD

- Git 브랜치 전략 → `Docs/skills/github/README.md`
- IDE/AI 코딩 툴 → 개인별 사용
