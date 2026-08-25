# SortMaster 학습 데이터셋 계약

> 이 문서는 `CLAUDE.md`가 라벨링·학습 작업의 기준으로 지정한 문서다.
> 실제 데이터 파일 위치, 수량, train/val/test 비율은 아직 저장소에 없으므로 임의로
> 단정하지 않는다. API/ERD 의미 계약과 모델 산출물의 합격 조건만 정의한다.

## 1. MVP Top 모델 의미 클래스

위 카메라 모델은 **쓰레기 4종**만 구분하면 된다(통 위치는 모델이 아니라 고정 ROI 룰 베이스로
판정 — 아래 "2. 현재 수령 산출물 감사"/`.agentfiles/architecture.md`의 "탐지 파이프라인"
참고). 모델 내부의 숫자 class ID 순서는 학습 설정과 함께 고정·버전 관리해야 하며, 아래 API
의미값으로 일대일 변환할 수 있어야 한다.

### 쓰레기 4종

| API `detectedClass` | 의미 | 정상 `binType` |
|---|---|---|
| `general` | 일반 쓰레기 | `general` |
| `paper` | 종이 | `paper` |
| `plasticCan` | 플라스틱·캔 | `plasticCan` |
| `coffeeCup` | 커피 컵 | `coffeeCup`, `plasticCan`(둘 다 정상) |

과거엔 `plastic`/`can`을 별도 클래스로 두고 `plasticCan`에 다대일로 매핑하기로 했었으나,
실제 YOLO26 모델이 둘을 구분하지 못하는 게 확인돼 **`plasticCan` 하나로 통합 확정**(모델
재학습 대신 API 계약을 4종으로 바꾸는 쪽으로 CTO 승인, `.agentfiles/decisionLog.md` 참고).
`mixed`/`uncertain`은 MVP 클래스에 포함하지 않는다.

### 물리 통 4종

| API `binType` | 의미 |
|---|---|
| `general` | 일반 쓰레기통 |
| `paper` | 종이 쓰레기통 |
| `plasticCan` | 플라스틱·캔 공용 통 |
| `coffeeCup` | 커피 컵 통 |

`binId`는 위 종류가 아니라 설치된 실제 통의 식별자다. 물리 통 4개(일반/플라스틱·캔/커피컵/
종이) 구성은 확정됐고(`Docs/ERD.md` 참고), 통 위치 자체는 모델이 아니라 화면 고정 비율
ROI(룰 베이스, `tracking2.py`의 `RULE_BASED_BIN_ROIS`)로 판정하므로 모델 클래스명에 물리
ID를 하드코딩하지 않는다.

## 2. 현재 수령 산출물 감사

### `bestTop.pt`

- SHA256:
  `2AF28906CE55D7367F807B2FD70B77A7F91C3F469BE8F328E7747B3FE44CDFFC`
- 체크포인트 Ultralytics 버전: `8.4.118`
- **실제 클래스(정정됨)**: `trash_normal`, `trash_paper`, `trash_recyclables`, `trash_coffeecup`
  **쓰레기 4종뿐** — 처음엔 `box_normal`/`box_paper`/`box_recyclables`/`box_coffeecup`(통
  4종)까지 포함한 8클래스 모델로 오인했으나(모델 호출 흔적만 보고 판단), 실기기 테스트로
  모델이 실제로는 쓰레기 4클래스만 알고 있는 게 확인됨 — 통 위치는 애초부터 룰 베이스
  (고정 ROI)가 맞는 설계였음(`.agentfiles/decisionLog.md` 참고)

이 모델은 쓰레기 `plastic`과 `can`을 `trash_recyclables` 하나로 합쳐서 낸다. 어느 종류인지
출력에서 복원할 수 없어서, **모델 재학습 대신 API 계약(`DetectedClass`)을 4종으로 축소하는
쪽으로 CTO 승인을 받아 해소함**(`.agentfiles/decisionLog.md` 참고) — `plastic`/`can` 값은
더 이상 API 계약에 존재하지 않고 `plasticCan` 하나로 통합됨(위 "1. MVP Top 모델 의미 클래스"
참고). `coffeecup`을 `recyclables` 통에도 정상으로 보는 `tracking2.py` 규칙(`VALID_BIN_MAP`)도
이 계약과 일치. **이 모델은 이미 GPU 서버(`tracking2.py`)에서 실제 TOP 카메라 스트림으로
운영 이벤트를 보내는 데 사용 중**(2026-08-25, 로컬 백엔드까지 end-to-end 검증됨 — 단, 실제
통 위치 기준 `RULE_BASED_BIN_ROIS` 재보정은 아직 TBD, `.agentfiles/architecture.md` 참고).

### SIDE(옆 카메라) — MobileNet_V3_Small

`bestSide2.pt`(YOLO 체크포인트, `normal`/`overflow` 2클래스)로 판정하려던 초기 계획은
폐기됐고, 한때 룰 베이스(GPU/모델 완전 미사용)로 확정했던 결정도 다시 뒤집혀 **경량 분류
모델(MobileNet_V3_Small)로 최종 확정**됨(`WebApps/backend/models/trashoverflow/` —
`feature/side-overflow-integration` 브랜치, `dev`에 merge 완료. `.agentfiles/decisionLog.md`
참고). ROI로 크롭한 이미지를 모델에 넣어 `normal`/`overflow` 2클래스로 분류 — 모델이 가벼워서
GPU 서버 없이 **로컬 백엔드에서 CPU로 추론**(GPU 있으면 자동 사용). YOLO26(TOP)과 달리 통
위치 추적/추적 판정은 없고, 연속 30초 이상 `overflow`로 유지되면 최종 판정(세션 상태 기반).

## 3. 전처리·실행 위치

- 실촬영: 640×480
- YOLO 입력: 640×640 letterbox(비율 유지)
- **추론 위치: GPU 서버**(`models/trashdetect/tracking2.py`) — Jetson Orin Nano Super는
  발주 취소되고 라즈베리파이로 대체됨(라즈베리파이는 캡처+RTSP 송신+GPIO/스피커만 담당,
  추론 없음). `.agentfiles/architecture.md`의 "탐지 파이프라인"/"배포 전략" 참고
- 백엔드 Python 3.11 환경에는 PyTorch/Ultralytics를 넣지 않는다(그대로 유효 — GPU 서버 쪽
  별도 venv에서 관리, `.agentfiles/gpuServerOps.md` 참고)
- 모델 파일은 Git 제외 대상이므로 해시·버전과 별도의 배포 절차가 필요하다(단, `training`→
  `tracking2.py` 둘 다 GPU 서버 안에 있어 원격 배포는 불필요 — 로컬 파일/볼륨 공유로 충분,
  `.agentfiles/architecture.md`의 "추론 인프라" 참고)

## 4. 새 Top 모델 합격 조건

1. **쓰레기 4종**을 손실 없이 구분하고 class ID/name 매핑이 문서화되어야 한다(통 위치는
   모델이 아니라 고정 ROI 룰 베이스로 판정하므로 모델은 쓰레기 클래스만 책임진다).
2. 시작 시 모델 class names가 기대 계약과 다르면 경고 후 계속하지 말고 즉시 실패해야 한다
   (`tracking2.py`가 이미 이렇게 구현돼 있음 — `EXPECTED_CLASS_NAMES` 비교 후 `[WARNING]`).
3. 4개 쓰레기 클래스 × 4개 통 16조합을 검증한다(`VALID_BIN_MAP` 기준). 정상 조합은
   general/general, paper/paper, plasticCan/plasticCan, coffeeCup/coffeeCup,
   coffeeCup/plasticCan 5개뿐이다(커피컵은 커피컵 통·재활용 통 둘 다 정상).
4. 최종 선택 클래스의 confidence를 0~1 한 값으로 계산해 API에 보낸다.
5. 동일 물체 ID switch, 동시 2개 투척, 빠른 연속 투척, 일시 가림, 통 미검출 영상을 포함한다.
6. 엣지 payload가 `Docs/API_SPEC.md`의 EP-08/EP-09 계약과 자동 테스트를 통과해야 한다.

## 5. 아직 확정·제공되지 않은 항목

- 원본 데이터셋 저장 위치와 디렉터리 구조
- 클래스 숫자 ID 순서
- train/validation/test 분할 및 각 클래스 수량
- `RULE_BASED_BIN_ROIS`(통 위치 고정 ROI) 실측 재보정 — 지금은 데모/임시 좌표, 실제 카메라
  설치 후 필요(`.agentfiles/architecture.md` 참고)
- BoT-SORT/ReID 파라미터의 실제 영상 기준값
