# SortMaster 학습 데이터셋 계약

> 이 문서는 `CLAUDE.md`가 라벨링·학습 작업의 기준으로 지정한 문서다.
> 실제 데이터 파일 위치, 수량, train/val/test 비율은 아직 저장소에 없으므로 임의로
> 단정하지 않는다. API/ERD 의미 계약과 모델 산출물의 합격 조건만 정의한다.

## 1. MVP Top 모델 의미 클래스

위 카메라 모델은 쓰레기 5종과 물리 통 4종을 서로 구분할 수 있어야 한다. 모델 내부의 숫자
class ID 순서는 학습 설정과 함께 고정·버전 관리해야 하며, 아래 API 의미값으로 일대일 변환할
수 있어야 한다.

### 쓰레기 5종

| API `detectedClass` | 의미 | 정상 `binType` |
|---|---|---|
| `general` | 일반 쓰레기 | `general` |
| `paper` | 종이 | `paper` |
| `plastic` | 플라스틱 | `plasticCan` |
| `can` | 캔 | `plasticCan` |
| `coffeeCup` | 커피 컵 | `coffeeCup` |

`plastic`과 `can`은 같은 물리 통으로 들어가지만 API와 학습 클래스에서는 서로 다른
쓰레기 종류다. `mixed`/`uncertain`은 MVP 클래스에 포함하지 않는다.

### 물리 통 4종

| API `binType` | 의미 |
|---|---|
| `general` | 일반 쓰레기통 |
| `paper` | 종이 쓰레기통 |
| `plasticCan` | 플라스틱·캔 공용 통 |
| `coffeeCup` | 커피 컵 통 |

`binId`는 위 종류가 아니라 설치된 실제 통의 식별자다. 허용 ID 목록은 아직 CTO 확정 전이며,
모델 클래스명에 물리 ID를 하드코딩하지 않는다.

## 2. 현재 수령 산출물 감사

### `bestTop.pt`

- SHA256:
  `2AF28906CE55D7367F807B2FD70B77A7F91C3F469BE8F328E7747B3FE44CDFFC`
- 체크포인트 Ultralytics 버전: `8.4.118`
- 실제 클래스:
  `trash_normal`, `trash_paper`, `trash_recyclables`, `trash_coffeecup`,
  `box_normal`, `box_paper`, `box_recyclables`, `box_coffeecup`

이 모델은 쓰레기 `plastic`과 `can`을 `trash_recyclables` 하나로 합쳤다. 어느 종류인지
출력에서 복원할 수 없으므로 문자열 치환이나 변수명 변경으로 현재 API 계약에 연결할 수 없다.
`coffeecup`을 `recyclables` 통에도 정상으로 보는 외부 `tracking2.py` 규칙 역시 위 매핑과
충돌한다. 이 모델과 코드는 재학습 또는 CTO 승인 하 계약 변경 전까지 운영 이벤트를 보내면 안 된다.

### `bestSide2.pt`

체크포인트에는 `normal`/`overflow` 2개 상태 클래스가 확인된다. 그러나 물리 통 4개의
`binId`별 상태 추적, `NORMAL`→`FULL` 전환, `BIN_STATES` 저장은 아직 구현·검증되지
않았으므로 백엔드 완료로 간주하지 않는다.

## 3. 전처리·실행 위치

- 실촬영: 640×480
- YOLO 입력: 640×640 letterbox(비율 유지)
- MVP 추론 위치: Jetson Orin Nano Super
- 백엔드 Python 3.11 환경에는 PyTorch/Ultralytics를 넣지 않는다.
- 엣지 JetPack 6.x Python 3.10 환경에서 PyTorch/Ultralytics 또는 TensorRT를 관리한다.
- 모델 파일은 Git 제외 대상이므로 해시·버전과 별도의 배포 절차가 필요하다.

## 4. 새 Top 모델 합격 조건

1. 쓰레기 5종+통 4종을 손실 없이 구분하고 class ID/name 매핑이 문서화되어야 한다.
2. 시작 시 모델 class names가 기대 계약과 다르면 경고 후 계속하지 말고 즉시 실패해야 한다.
3. 5개 쓰레기×4개 통 20조합을 검증한다. 정상 조합은
   general/general, paper/paper, plastic/plasticCan, can/plasticCan,
   coffeeCup/coffeeCup 5개뿐이다.
4. 최종 선택 클래스의 confidence를 0~1 한 값으로 계산해 API에 보낸다.
5. 동일 물체 ID switch, 동시 2개 투척, 빠른 연속 투척, 일시 가림, 통 미검출 영상을 포함한다.
6. 엣지 payload가 `Docs/API_SPEC.md`의 EP-08/EP-09 계약과 자동 테스트를 통과해야 한다.

## 5. 아직 확정·제공되지 않은 항목

- 원본 데이터셋 저장 위치와 디렉터리 구조
- 클래스 숫자 ID 순서
- train/validation/test 분할 및 각 클래스 수량
- 물리 `binId` 허용 목록
- 최종 Top 모델 파일명·버전 정책과 Jetson 배포 방식
- BoT-SORT/ReID 파라미터의 실제 영상 기준값
