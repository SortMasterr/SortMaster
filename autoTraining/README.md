# SortMaster 자동 학습 파이프라인

CCTV 영상에서 학습 후보 프레임을 만들고, 기존 YOLO 모델로 자동 라벨링한 뒤 Qwen-VL 검수, 데이터셋 병합, 재학습, 비교 평가 및 모델 승격까지 수행하는 파이프라인입니다.

## 전체 흐름

```text
MongoDB events + 카메라별 GridFS 이벤트 영상 저장소
  ↓
0. Collect  : 해당 날짜 ELEV-TOP 투기 이벤트의 topMedia GIF 수집
  ↓
1. Extract  : GIF/영상 프레임 추출
  ↓
2. Select   : 학습 후보 프레임 선별
  ↓
3. Label    : 활성 기준 모델 고정 후 자동 라벨링
  ↓
4. Review   : vLLM Qwen-VL 1차 검수
  ↓
모든 결과를 humanReviewQueue.jsonl로 전달
  ↓
localhost 검수 UI에서 사람이 승인/라벨 수정 승인/거절
→ humanDecisions.jsonl 자동 저장
  ↓
5. HumanReview : 누락·중복·라벨 파일 검증
  ↓
6. Build    : 기존 train/val + 사람 승인 신규 데이터 병합
              고정 Golden Test는 병합하지 않음
  ↓
7. Train    : 신규 YOLO 후보 모델 학습
  ↓
8. Evaluate : 고정 Golden Test로 기준 모델/후보 모델 비교
  ↓
9. Promote  : 최소 품질 향상 시 불변 registry에 승격
  ↓ 사람의 배포 승인
10. Deploy  : tracking2.py용 bestTop.pt 원자적 교체
  ↓
tracking2.py 재시작 + smoke test, 실패 시 rollback
```

일일 자동 실행은 사람 검수를 경계로 두 구간으로 나뉩니다. Promote와 Deploy도 의도적으로
분리하여 평가 통과만으로 운영 모델이 즉시 바뀌지 않게 합니다.

## 구현 상태

### 현재 판정

2026-08-25 기준으로 파이프라인 11개 단계(`Collect`부터 `Deploy`까지)와 사람 검수 전·후
실행 구간은 코드로 구현되어 있습니다. Conda `env_py311`의 실제 패키지 버전을
`requirements.txt`에 반영했고 Python 구문, CLI import, 의존성 충돌, GridFS GIF 프레임 추출
smoke test까지 통과했습니다.

다만 현재 저장소에는 기존 학습 데이터셋과 Golden Test가 없고 일일 입력도 0개입니다. Qwen용
localhost 포트의 SSH 리스너에는 도달하지만 원격 측이 `/v1/models` HTTP 응답 전에 연결을 종료합니다. bootstrap 체크포인트의 snake_case
클래스명은 설정의 camelCase 계약과 다르므로 현재 상태로 Label부터 전체 E2E를 실행할 수 없습니다.

| 항목 | 상태 | 확인 결과 |
|---|---|---|
| 전체 단계 코드 | 구현됨 | `Collect → Extract → Select → Label → Review → HumanReview → Build → Train → Evaluate → Promote → Deploy` |
| 일일 2구간 CLI | 구현됨 | `prepareDailyBatch`는 사람 검수 큐까지, `continueAfterHumanReview`는 평가까지 실행 |
| 사람 라벨 검수 UI | 구현·HTTP smoke test 통과 | localhost UI에서 원본/bbox/Qwen/클래스 순서를 보고 승인·라벨 텍스트 수정 승인·거절을 원자적으로 저장 |
| Python 코드 | 통과 | `autoTraining` Python 파일 18개 `compileall` 및 CLI import 성공 |
| 실행 환경 | 일치 | Conda `env_py311`, Python 3.11.15, `pip check` 충돌 없음 |
| requirements | 최신화됨 | 실제 환경의 Ultralytics 8.4.117, PyTorch 2.7.1+cu118, OpenCV 4.14.0.94, NumPy 2.4.4 등을 고정 |
| GPU | 사용 가능 | 현재 환경에서 CUDA 사용 가능, PyTorch CUDA 빌드는 11.8 |
| Collect 저장소 연동 | 구현됨, 실DB 미검증 | MongoDB `events`를 읽고 `ELEV-TOP`/`misclassification`의 `topMedia` GridFS GIF를 수집하도록 구현 |
| GIF 프레임 추출 | 테스트 통과 | 생성한 다중 프레임 GIF를 Collect 매니페스트 기준으로 Extract하는 smoke test 통과 |
| Qwen-VL 주소 구성 | 구현됨 | `.env`의 `LLM_PORT`와 `qwenVl.apiHost`를 조합하고 포트 범위를 검증 |
| Qwen-VL 실제 연결 | SSH 터널 도달, vLLM 응답 실패 | TCP 연결과 SSH 리스너는 확인했지만 `/v1/models` 3회 모두 `ConnectionResetError`; GPU 서버의 vLLM 기동·로그·원격 목적지 포트 확인 필요 |
| bootstrap 모델 파일 | 로드 가능 | `models/bootstrap/best.pt`, 5,393,150바이트, SHA-256 `757F...B7F2` |
| 모델 클래스 계약 | 불일치 | 체크포인트는 `trash_normal`, `trash_paper`, `trash_recyclables`, `trash_coffeecup`; 설정은 camelCase 4종 |
| 활성 모델 포인터 | 초기 상태 | `models/current.json`이 없어 최초 사이클은 bootstrap 모델을 선택 |
| 일일 입력 | 없음 | `autoTraining/inputVideos` 파일 0개이며 실제 GridFS 수집 실행 기록 없음 |
| 기존 데이터셋 | 없음 | `autoTraining/baseDataset` 디렉터리가 없음 |
| Golden Test | 없음 | `autoTraining/goldenTest` 디렉터리가 없어 비교평가 불가 |
| 버전형 학습 데이터셋 | 미생성 | `autoTraining/datasets/<batchId>`는 Build 성공 후 생성됨 |
| 모델 레지스트리·배포 | 구현됨 | 해시 검증, 후보/registry/current 관리, `bestTop.pt` 원자적 교체 및 수동 rollback 지원 |
| 운영 재시작·smoke test | 미구현 | Deploy 후 `tracking2.py` 재시작과 실패 시 자동 rollback은 수동 |
| 전체 E2E | 실행 불가·미검증 | 데이터, 클래스가 맞는 모델, 실행 중인 Qwen 및 실제 GridFS 연결이 필요 |
### 구현된 기능

- MongoDB `events`와 `topMedia` GridFS에서 일일 TOP 투기 이벤트 GIF 수집
- CCTV/GIF 영상 프레임 추출과 JPG 저장
- 상대 경로 해시 기반 영상 키로 같은 파일명의 카메라 영상 충돌 방지
- JSONL 스트리밍과 프로세스별 임시 파일·`fsync`·원자적 교체
- Select 단계의 간격 선검사 및 blur/brightness 단일 grayscale 계산
- causal 자동 라벨링에서 현재 프레임 중복 디코딩 제거
- 학습·평가 결과 JSON의 원자적 저장
- 선명도, 밝기, 프레임 간격을 이용한 후보 선별
- 기존 YOLO 모델을 사용한 자동 라벨링
- RGB 및 causal 입력 지원
- YOLO 라벨과 bbox 표시 이미지 생성
- vLLM OpenAI 호환 API를 이용한 Qwen-VL 자동 검수
- Qwen 결과 전체의 사람 검수 큐 생성과 사람 결정 JSONL 검증
- localhost 사람 검수 UI에서 원본·bbox·Qwen 결과 확인, 승인·YOLO 라벨 수정 승인·거절
- 사람 최종 승인 데이터와 기존 train/val 데이터셋 병합
- 영상 단위 train/val/test 분리
- 신규 모델 학습 및 실행별 불변 `models/candidates/<batchId>/<runName>/best.pt` 저장
- 고정 Golden Test를 사용한 기존 모델과 신규 모델 성능 비교
- 최소 성능 향상 모델의 불변 registry 등록과 SHA-256 검증
- Promote와 분리된 운영 `bestTop.pt` 배포 및 registry 버전 롤백

### 실행 전 반드시 해결할 문제

1. **최신 TOP 클래스 계약과 현재 설정 — 과도기 상태(2026-08-25 재회의 최종 결정)**
   - 최신 기준은 쓰레기 4종만 YOLO가 구분하는 구조입니다.
   - **현재 운영 중인 체크포인트(`bestTop.pt`)의 외부 클래스명과 순서는 snake_case**
     (`trash_normal`, `trash_paper`, `trash_recyclables`, `trash_coffeecup`)입니다 — 이미
     학습 완료된 모델에 박힌 고정값이라 코드만으로는 못 바꿉니다. `tracking2.py`의
     `EXPECTED_CLASS_NAMES`/`TRASH_CLASSES`/`TRASH_TYPE_MAP`은 이 값과 반드시 일치해야
     하며, 임의로 camelCase로 바꾸면 감지가 전부 무시되는 회귀가 납니다(이미 한 번 발생,
     `.agentfiles/decisionLog.md` 참고).
   - **전체 camelCase 통일이 팀 목표**이며 **다음에 재학습되는 새 TOP 모델도 camelCase**
     (`trashNormal`, `trashPaper`, `trashRecyclables`, `trashCoffeeCup`)로 만들기로
     확정됐습니다(`pipelineConfig.yaml`의 `dataset.classes`가 이미 이 목표값을 씁니다).
     새 모델이 이 계약으로 재학습되어 Promote/Deploy를 통해 `bestTop.pt`를 교체하는
     시점에 `tracking2.py`도 그때 같이 camelCase로 전환해야 합니다 — 그 전까지는 "설정
     파일은 목표(camelCase), 운영 모델/`tracking2.py`는 현재값(snake_case)"인 상태가
     정상입니다.
   - API 의미값은 각각 `normal`, `paper`, `recyclables`, `coffeeCup`으로 매핑됩니다(이건
     위 클래스명 표기법과 별개로 이미 확정, `.agentfiles/decisionLog.md` 참고). 플라스틱과
     캔은 `recyclables` 하나로 통합됐습니다.
   - 물리 통은 4개지만 YOLO 클래스가 아닙니다. `tracking2.py`의 `RULE_BASED_BIN_ROIS`가
     고정 화면 ROI로 통 위치를 판정하므로 자동 학습 데이터에 통 클래스를 추가하면 안 됩니다.

2. **체크포인트 신원과 입력 전처리 불일치**
   - 로컬 `models/bootstrap/best.pt`의 SHA-256은
     `757F7E8B19DCD2C166B08B247FE76B8A1D7E79AB735030188181D866DFD2B7F2`입니다.
   - `Docs/DATASET_DESCRIPTION.md`가 감사한 `bestTop.pt`의 SHA-256은
     `2AF28906CE55D7367F807B2FD70B77A7F91C3F469BE8F328E7747B3FE44CDFFC`이므로 두 파일은
     클래스명이 같아도 동일 체크포인트가 아닙니다. 어느 모델을 bootstrap으로 삼을지 확인해야 합니다.
   - 현재 자동화 설정은 `inputMode: causal`, `imgsz: 416`입니다. 실제 운영 `tracking2.py`는
     causal 합성 없이 단일 BGR 프레임을 사용하고 `INFERENCE_IMAGE_SIZE = 416`으로 추론합니다.
     반면 데이터셋 문서는 640×640 letterbox를 명시하므로 학습·자동 라벨링·운영 추론의 입력
     계약을 하나로 확정해야 합니다.

3. **최신 데이터 수집과 운영 재시작 미연결**
   - Qwen Review는 Compose의 vLLM OpenAI 호환 API로 변경했고, 사람 결정 JSONL 승인 게이트와
     `bestTop.pt` 배포·롤백 파일 교체까지 구현했습니다.
   - 로컬 `LLM_PORT`는 SSH 프로세스가 리스닝하고 TCP 연결도 성공하지만 `/v1/models` 요청은
     3회 모두 원격 종료됐습니다. GPU 서버 내부에서 vLLM 상태와 같은 API를 먼저 확인해야 합니다.
   - MongoDB `events.imageFileId`와 카메라별 GridFS 계약을 사용한 Collect를 구현했습니다.
     실제 로컬 DB, 역방향 SSH 터널과 운영 이벤트를 연결한 검증은 아직 필요합니다.
   - Deploy 이후 `tracking2.py` 프로세스 재시작, smoke test와 실패 감지에 따른 자동 rollback은
     운영 방식(systemd/Docker)이 확정되지 않아 자동화하지 않았습니다.
4. **필수 데이터와 실행 자원**
   - Python 3.11과 필수 import는 준비되어 있습니다.
   - 현재 저장소에는 `baseDataset`이 없습니다. GridFS Collect를 실제 DB에 연결해 입력을 수집하고
     기존 데이터셋과 Golden Test를 준비해야 전체 실행이 가능합니다.
   - GPU 서버에서 `tracking2.py`, training, Qwen vLLM이 같은 할당 GPU를 공유하므로 동시 실행
     시 VRAM·연산 경합을 실측하고 제한해야 합니다.

5. **데이터 분할과 선행조건 검증 잔여 작업**
   - Build는 사람 승인 0건과 Golden Test 부재를 시작 전에 차단합니다.
   - 영상 단위 train/val 분할에서 영상 수가 적으면 한 split이 비거나 클래스 분포가 치우칠 수
     있으므로 split별 최소 영상·이미지·클래스 수 검증은 추가해야 합니다.
   - `trainRatio`, `valRatio`, `testRatio`의 범위와 합계 검증은 아직 없으며 고정 Golden Test 도입으로
     일일 `testRatio` 설정은 제거하거나 의미를 재정의해야 합니다.

6. **운영 재시작 자동화 미완료**
   - 사람 검수 전/후, Promote, Deploy는 CLI에서 분리되어 평가만으로 운영 파일이 바뀌지 않습니다.
   - Deploy 이후 `tracking2.py` 재시작·smoke test·실패 감지에 따른 자동 rollback은 아직 수동입니다.

### 오류 또는 잘못된 결과가 발생할 수 있는 부분

- 기존 데이터셋의 causal 입력은 파일명 끝 숫자를 1, 2씩 줄여 이전 프레임을 찾습니다. 실제
  촬영 순서나 프레임 간격을 보장하지 않는 데이터셋에서는 잘못된 시간 채널이 결합될 수 있습니다.
- Qwen-VL 응답은 JSON Schema를 완전하게 검증하지 않습니다. 객체 여부, 필수 필드 타입,
  추가 필드를 충분히 검사하지 않아 일부 잘못된 응답에서 전체 Review가 중단될 수 있습니다.
- Review를 다시 실행할 때 `approved`, `manualReview`, `rejected` 폴더를 정리하지 않아 최신
  `reviews.jsonl`과 과거 큐 파일이 서로 다를 수 있습니다. Build는 JSONL을 기준으로 처리합니다.
- Build는 기존 `datasets/<batchId>`를 먼저 삭제하므로 생성 중 실패하면 이전 정상 데이터셋도
  잃을 수 있습니다. JSONL 매니페스트와 달리 데이터셋 디렉터리는 원자적으로 교체하지 않습니다.
- 설정 스키마 검증이 없어 잘못된 `inputMode`, 비율, device 또는 누락 키가 처리 도중에야
  오류로 나타날 수 있습니다.

### 현재 적용된 성능·안정성 최적화

- Select는 `candidateEveryN` 간격을 먼저 검사하므로 탈락할 프레임은 JPEG 디코딩과 품질 계산을 생략합니다.
- blur와 brightness는 같은 grayscale 이미지에서 함께 계산하여 OpenCV 색상 변환을 한 번만 수행합니다.
- causal Label은 이미 읽은 현재 프레임을 재사용하고 이전 두 프레임만 추가로 읽습니다.
- 영상 키는 입력 배치 내 상대 경로의 SHA-256 일부를 포함하므로 카메라별 동일 파일명이 충돌하지 않습니다.
- JSONL은 행 단위로 처리하며 프로세스별 임시 파일에 `flush`/`fsync`한 뒤 교체합니다.
- `trainingResult.json`과 `evaluation.json`도 완성된 JSON만 다음 단계에 노출하도록 원자적으로 저장합니다.

### 추가 구현이 필요한 기능

- 검수 UI의 마우스 기반 bbox 그리기·크기 조절(현재는 YOLO 라벨 텍스트 수정)
- 배치 상태 파일, 실패 단계 재개와 중복 실행 잠금
- Docker Compose의 독립 `autoTraining` 서비스
- 스케줄 실행, 실패 재시도 및 알림
- 배포 승인 한 번으로 Promote·Deploy를 연결하는 release 명령
- Deploy 후 `tracking2.py` 재시작, smoke test 및 실패 시 자동 rollback
- 실제 GPU 서버에서의 전체 E2E 테스트
- 실제 vLLM·Golden Test·GPU 학습을 포함한 단계별 단위 테스트와 소규모 E2E 자동 테스트

### 권장 작업 순서

1. 확정된 쓰레기 4종의 외부 class names를 그대로 설정하고 bootstrap 체크포인트 신원을 확정합니다.
2. 자동화와 `tracking2.py`의 입력 방식·크기 계약을 통일하고 설정 스키마 검증을 추가합니다.
3. 실제 MongoDB/GridFS 수집과 vLLM 멀티모달 JSON Schema 응답을 운영 환경에서 검증합니다.
4. split별 최소 영상·이미지·클래스 수 검증과 Build의 안전한 임시 디렉터리 교체를 구현합니다.
5. 구현된 원자적 Deploy/rollback 뒤 `tracking2.py` 재시작·smoke test를 자동화합니다.
6. 사람 승인 단계를 포함해 GPU 서버에서 자동 라벨링→학습→평가→운영 반영 E2E를 검증합니다.

## 디렉터리 구조

```text
autoTraining/
├─ README.md
├─ trainingPipeline.py
├─ pipelineConfig.yaml
├─ common/
│  ├─ causalImages.py
│  ├─ modelRegistry.py
│  └─ pipelineUtilities.py
├─ stages/
│  ├─ collectEventMedia.py
│  ├─ extractFrames.py
│  ├─ selectFrames.py
│  ├─ autoLabeling.py
│  ├─ reviewLabels.py
│  ├─ humanReview.py
│  ├─ humanReviewUi.py
│  ├─ buildDataset.py
│  ├─ trainModel.py
│  ├─ evaluateModel.py
│  ├─ promoteModel.py
│  └─ deployModel.py
├─ inputVideos/<batchId>/       # GridFS 수집 사본 또는 localDirectory 개발 입력
├─ datasets/<batchId>/          # Build가 생성한 버전형 학습 데이터셋 저장소
├─ baseDataset/
├─ goldenTest/
│  ├─ images/
│  └─ labels/
├─ models/
│  ├─ bootstrap/best.pt
│  ├─ candidates/<batchId>/<runName>/best.pt
│  ├─ registry/model-<version>.pt
│  └─ current.json
└─ workspace/batches/<batchId>/
   ├─ cycleModel.json
   ├─ humanReviewQueue.jsonl
   ├─ humanDecisions.jsonl
   ├─ humanReviews.jsonl
   ├─ trainingResult.json
   ├─ evaluation.json
   └─ deployment.json
```

설정·경로·JSONL 처리는 `pipelineUtilities.py`, 모델 버전·해시·활성 포인터 처리는
`modelRegistry.py`가 담당합니다.
## 모델 역할

| 경로 | 역할 |
|---|---|
| `models/bootstrap/best.pt` | 최초 자동 라벨링·학습 시작과 복구에 사용하는 원본 모델 |
| `models/candidates/<batchId>/<runName>/best.pt` | 실행별로 보존되는 승격 전 후보 모델 |
| `models/registry/model-<version>.pt` | 평가를 통과한 불변 승격 모델 |
| `models/current.json` | 활성 모델의 버전·절대 경로·SHA-256을 기록한 포인터 |
| `workspace/batches/<batchId>/cycleModel.json` | 현재 학습 사이클에 고정된 기준 모델과 해시 |

`bootstrap/best.pt`와 registry 모델은 덮어쓰지 않습니다. Label 시작 시 `current.json`이
있으면 해당 승격 모델을, 없으면 bootstrap 모델을 선택하고 `cycleModel.json`에 버전과 해시를
고정합니다. 이후 Train과 Evaluate는 사이클에 고정된 같은 모델만 사용합니다. Promote는 평가한
baseline과 후보의 해시를 다시 확인하고 registry 파일 및 `current.json`을 원자적으로 갱신합니다.

## 실행 환경

현재 로컬에서 확인된 Conda 환경은 다음과 같습니다.

```powershell
conda activate env_py311
python autoTraining/trainingPipeline.py --help
```

Conda 활성화 없이 직접 실행할 수도 있습니다.

```powershell
<CONDA_ENV_PATH>\python.exe autoTraining\trainingPipeline.py --help
```

2026-08-25 실제 확인 버전:

| 패키지 | 현재 환경 및 `requirements.txt` |
|---|---:|
| Python | 3.11.15 (`requirements.txt` 밖에서 3.11 사용) |
| Ultralytics | 8.4.117 |
| PyTorch | 2.7.1+cu118 |
| Torchvision | 0.22.1+cu118 |
| OpenCV | 4.14.0.94 |
| NumPy | 2.4.4 |
| PyYAML | 6.0.3 |
| Pillow | 11.1.0 |
| Motor | 3.7.1 |
| PyMongo | 4.17.0 |
| python-dotenv | 1.2.2 |

`requirements.txt`를 위 `env_py311` 실제 버전과 일치시켰습니다. CUDA 11.8 빌드의 PyTorch와
Torchvision을 재현할 수 있도록 PyTorch 공식 cu118 추가 인덱스도 파일에 명시했습니다. 다른 CUDA
버전의 GPU 서버에서는 무조건 이 파일을 설치하지 말고 서버 드라이버·CUDA 계약에 맞춰 PyTorch
빌드를 먼저 확정해야 합니다.
## 입력 준비

### 이벤트 영상 저장소 입력

운영 기본값은 `eventStore.source: gridFs`입니다. Collect는 `--batchId`의 한국 시간 하루 동안 생성된
`ELEV-TOP`/`misclassification` 이벤트 중 `imageFileId`가 있는 문서만 조회하고, 같은 DB의
`topMedia` GridFS GIF를 다음 작업 입력 폴더에 복사합니다. MongoDB/GridFS 원본은 수정하지 않습니다.

```text
autoTraining/inputVideos/<batchId>/<eventId>.gif
autoTraining/workspace/batches/<batchId>/collectedMedia.jsonl
```

연결정보는 백엔드와 동일하게 `.env`의 `MONGO_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`,
`DB_NAME`을 사용합니다. GPU 서버에서는 문서에 정한 역방향 SSH 터널이 먼저 연결되어야 합니다.
로컬 파일로 개발할 때만 `eventStore.source: localDirectory`로 변경하고 위 입력 폴더에 직접
영상을 넣습니다. 두 입력 방식을 한 배치에서 혼합하지 않습니다.

### 학습 데이터셋 저장소

Build 결과는 작업 중간 파일과 분리하여 `autoTraining/datasets/<batchId>`에 저장합니다.
Train과 Evaluate는 같은 배치의 이 버전형 데이터셋을 읽으며 Golden Test는 계속 별도로 유지합니다.
기존 YOLO 데이터셋을 수동으로 사용할 때의 현재 코드 요구 구조:

```text
autoTraining/baseDataset/
├─ images/train
├─ images/val
├─ images/test
├─ labels/train
├─ labels/val
└─ labels/test
```

기본 자동 라벨링 모델:

```text
autoTraining/models/bootstrap/best.pt
```

Review는 Compose의 vLLM OpenAI 호환 API와 JSON Schema 응답 형식을 사용합니다. 실제 GPU 서버의
Qwen 모델로 멀티모달 요청 호환성과 응답 형식을 E2E 검증해야 합니다.
## 설정

설정 파일은 `autoTraining/pipelineConfig.yaml`입니다.

주요 경로:

```yaml
paths:
  videos: autoTraining/inputVideos
  workspace: autoTraining/workspace
  datasetStore: autoTraining/datasets
  baseDataset: autoTraining/baseDataset
  bootstrapModel: autoTraining/models/bootstrap/best.pt
  modelRegistry: autoTraining/models/registry
  candidateModels: autoTraining/models/candidates
  activeModelPointer: autoTraining/models/current.json
```

프레임 설정:

```yaml
frames:
  saveEveryN: 1
  jpegQuality: 95
  candidateEveryN: 3
  minLaplacianVariance: 20.0
  minBrightness: 20.0
  maxBrightness: 235.0
```

- `saveEveryN`: 저장할 원본 프레임 간격
- `candidateEveryN`: 후보 검사 간격
- `minLaplacianVariance`: 최소 선명도
- `minBrightness`, `maxBrightness`: 허용 밝기 범위

추론 설정:

```yaml
inference:
  inputMode: causal
  imgsz: 416
  confidence: 0.20
  device: 0
```

- `rgb`: 현재 프레임만 사용
- `causal`: t-2, t-1, t 프레임의 회색조를 각각 하나의 채널로 결합
- `device: 0`: 첫 번째 GPU
- CPU 사용 시 `device: cpu`

기준 모델을 학습할 때 사용한 입력 방식과 `inputMode`가 같아야 합니다. 현재 `causal` 설정은
운영 `tracking2.py`의 단일 BGR 프레임 입력과 다릅니다. 운영 모델 재학습 목적이라면 임의로
진행하지 말고 RGB/BGR 단일 프레임과 416/640 입력 크기 중 최종 계약을 먼저 확정해야 합니다.

## 단계별 실행

모든 명령은 SortMaster 루트에서 실행하며 하루치 작업은 같은 `--batchId`를 사용합니다.

### 1차 자동 구간: 사람 검수 큐 생성

```powershell
python autoTraining/trainingPipeline.py prepareDailyBatch --batchId 2026-08-25
```

위 명령은 Collect → Extract → Select → Label → Qwen Review를 실행하고
`workspace/batches/2026-08-25/humanReviewQueue.jsonl`을 만든 뒤 멈춥니다.

사람은 로컬 검수 UI를 실행합니다.

```powershell
python autoTraining/trainingPipeline.py reviewUi --batchId 2026-08-25
```

기본 브라우저에서 `http://127.0.0.1:8765`가 열립니다. UI는 원본 이미지, YOLO bbox 이미지,
Qwen 판정, 클래스 ID 순서와 YOLO 라벨 텍스트를 표시합니다. 승인·라벨 텍스트 수정 승인·거절을
누를 때마다 `humanDecisions.jsonl`을 원자적으로 갱신하고 수정 라벨은
`humanReview/correctedLabels`에 별도로 보존합니다. UI 종료는 터미널에서 `Ctrl+C`입니다.

GPU 서버에서 브라우저를 직접 열 수 없다면 `--noBrowser`로 실행하고 SSH 포트 포워딩을 사용합니다.
UI는 기본적으로 localhost에만 바인딩되며 공개 네트워크에 직접 노출하지 않습니다. JSONL 수동
편집도 호환되지만 운영 기본 경로는 검수 UI입니다. 모든 큐 id에 결정이 있어야 다음 단계로
진행되며 누락·중복·허용되지 않은 decision은 `HumanReview`에서 즉시 실패합니다.
### 2차 자동 구간: 사람 검수 이후 평가까지

```powershell
python autoTraining/trainingPipeline.py continueAfterHumanReview --batchId 2026-08-25
```

HumanReview → Build → Train → Evaluate까지만 실행합니다. 평가 결과를 사람이 확인한 뒤 승격과
운영 배포를 별도로 실행합니다.

```powershell
python autoTraining/trainingPipeline.py promote --batchId 2026-08-25
python autoTraining/trainingPipeline.py deploy --batchId 2026-08-25
```

이전 registry 버전으로 운영 파일을 되돌릴 수 있습니다.

```powershell
python autoTraining/trainingPipeline.py rollback --batchId 2026-08-25 --version model-<version>
```

Deploy와 Rollback은 모델 파일만 원자적으로 교체합니다. 이후 `tracking2.py` 재시작과 smoke
테스트는 현재 수동입니다. 개별 stage 명령도 진단·재실행 목적으로 사용할 수 있습니다.
## 단계별 출력

| 단계 | 주요 출력 |
|---|---|
| Collect | `inputVideos/<batchId>/*.gif`, `collectedMedia.jsonl` |
| Extract | `workspace/batches/<batchId>/framesAll`, `frames.jsonl` |
| Select | 배치별 `candidates`, `candidates.jsonl` |
| Label | `workspace/autoLabels`, `annotated`, `labels.jsonl` |
| Review | `reviews.jsonl`, `humanReviewQueue.jsonl`, Qwen 판정별 참고 폴더 |
| HumanReview | `humanReviews.jsonl` |
| Build | `datasets/<batchId>`, `data.yaml` |
| Train | `workspace/runs`, `models/candidates/<batchId>/<runName>/best.pt`, `trainingResult.json` |
| Evaluate | `workspace/evaluation.json` |
| Promote | `models/registry/model-<version>.pt`, `models/current.json` |
| Deploy | `WebApps/backend/models/trashdetect/bestTop.pt`, `deployment.json` |

## JSONL 매니페스트

각 줄이 독립된 JSON 객체인 JSONL 형식을 사용합니다.

| 파일 | 내용 |
|---|---|
| `collectedMedia.jsonl` | Event/GridFS 식별자와 내려받은 클립 경로 |
| `frames.jsonl` | 원본 영상과 추출 프레임 정보 |
| `candidates.jsonl` | 선별된 학습 후보 |
| `labels.jsonl` | 자동 라벨, bbox, 검수 이미지 경로 |
| `reviews.jsonl` | Qwen-VL 결정, 오류, 사용 모델 |
| `trainingResult.json` | 학습 결과와 신규 모델 경로 |
| `evaluation.json` | 기존 모델과 신규 모델의 평가 결과 |

매니페스트에는 절대 경로가 포함됩니다. 다른 서버나 Docker 컨테이너로 workspace를 복사하면 경로가 달라질 수 있으므로 해당 환경에서 앞 단계를 다시 실행하거나 동일한 볼륨 경로로 마운트해야 합니다.

## camelCase 변경 후 기존 작업 데이터

설정 키, Python 내부 이름, 매니페스트 필드, 파이프라인이 생성하는 폴더 이름, 그리고 **다음
재학습부터의 목표 YOLO 클래스명**까지 camelCase로 통일했습니다(2026-08-25 재회의 최종 결정
— 전체 camelCase 통일, 다음 TOP 모델 포함). **단, 지금 운영 중인 `bestTop.pt`는 여전히
snake_case 클래스명을 내놓는 기존 체크포인트**라, 새 camelCase 모델이 실제로 재학습·배포될
때까지 `tracking2.py`의 클래스 매칭 값은 예외적으로 snake_case를 유지합니다(`.agentfiles/naming.md`/
`.agentfiles/decisionLog.md` 참고). 기존 workspace에 snake_case 필드나 클래스명으로 생성된
JSONL은 새 코드와 호환되지 않으므로 `extract` 단계부터 다시 실행해야 합니다.

Qwen-VL 설정은 `qwenVl`에 있으며 검수 결과는 camelCase 필드를 사용합니다. API 호스트는
`pipelineConfig.yaml`의 `qwenVl.apiHost`, 포트는 프로젝트 루트 또는 `WebApps/backend/.env`의
`LLM_PORT`를 사용합니다. 실제 포트 번호를 YAML이나 README에 중복 기록하지 않습니다.

```yaml
qwenVl:
  apiHost: http://127.0.0.1
  model: auto
```

Review는 조합한 주소의 vLLM OpenAI 호환 `/v1/models`, `/v1/chat/completions`를 호출합니다.
GPU 서버 외부에서 파이프라인을 실행한다면 `apiHost`를 GPU 서버 주소로 바꾸되 실제 주소와
인증정보는 공개 문서에 기록하지 않습니다.

2026-08-25 재연결 시험에서는 localhost의 설정 포트까지 TCP 연결됐고 해당 포트를 SSH 프로세스가
리스닝하는 것도 확인했습니다. 그러나 `/v1/models` 요청은 3회 모두 HTTP 응답 전에
`ConnectionResetError`로 종료됐습니다. 이는 로컬 파이프라인에서 SSH 터널 입구까지는 도달했지만
터널 뒤의 vLLM 서비스가 정상 응답하지 않는 상태를 의미합니다. GPU 서버에서 다음을 확인해야 합니다.

```bash
docker compose ps llm
docker compose logs --tail=100 llm
curl http://127.0.0.1:${LLM_PORT}/v1/models
```

GPU 서버 내부의 `curl`이 성공한 뒤 로컬 터널을 다시 시험하고, 이후 실제 이미지가 포함된
`/v1/chat/completions` 멀티모달 요청까지 확인해야 Review를 실환경 검증 완료로 판단합니다.

## 메모리 및 I/O 최적화

프레임 수가 많아도 RAM 사용량이 프레임 개수에 비례해 계속 증가하지 않도록 다음 구조를 사용합니다.

- `iterateManifest()`가 JSONL을 한 줄씩 읽습니다.
- Extract, Select, Label, Review 단계는 `ManifestWriter`로 결과를 한 줄씩 기록합니다.
- Build 단계는 승인 행을 리스트로 만들지 않고 제너레이터로 처리합니다.
- 매니페스트는 `.tmp` 파일에 기록하며 단계가 성공했을 때만 기존 파일과 교체합니다.
- 단계가 실패하면 임시 파일을 삭제하고 이전 매니페스트를 보존합니다.
- causal 입력용 프레임 경로 인덱스는 최초 한 번만 생성해 캐시합니다.
- Extract를 다시 실행하면 프레임 캐시를 초기화합니다.

causal 인덱스 자체는 프레임 경로 탐색을 위해 프레임 수에 비례하는 작은 딕셔너리를 사용합니다. 이미지 배열 전체를 보관하는 것은 아니며 실제 이미지는 필요한 시점에만 OpenCV로 읽습니다.

## Docker와 GPU 서버

Docker는 실행 환경과 의존성을 고정하는 수단이고, GPU는 YOLO 학습 및 추론 연산을 수행하는 장치입니다. GPU 서버에서도 NVIDIA Container Toolkit을 구성하면 Docker 컨테이너가 GPU를 사용할 수 있습니다.

`docker-compose.yml`의 `training` 서비스는 `./training` Jupyter 환경을 마운트하며 이 `autoTraining` 디렉터리를 직접 실행하는 독립 서비스가 아닙니다. Compose의 `llm`은 vLLM OpenAI 호환 API이며 Review 클라이언트도 같은 계약으로 수정됐지만 실제 GPU Qwen 모델과의 멀티모달 E2E는 미검증입니다. 현재 자동화 코드는 GPU 서버 Python 환경에서 직접 실행하거나 별도 이미지·볼륨·GridFS 연결을 구성해야 합니다.

## 주의 사항

- Qwen 판정과 무관하게 사람의 최종 `approved`만 Build에 포함됩니다.
- Build는 해당 배치의 `datasets/<batchId>`를 새로 생성하므로 필요한 결과는 먼저 백업합니다.
- **다음 재학습 목표 클래스명은 `trashNormal`, `trashPaper`, `trashRecyclables`,
  `trashCoffeeCup`(camelCase) 순서로 확정**(2026-08-25 재회의 최종 결정, 전체 camelCase
  통일 — 다음 TOP 모델 포함). 단, **현재 운영 중인 `bestTop.pt`는 여전히
  snake_case**(`trash_normal` 등)를 내놓는 기존 체크포인트라 `tracking2.py`의
  `EXPECTED_CLASS_NAMES`/`TRASH_CLASSES`/`TRASH_TYPE_MAP`은 지금 당장 camelCase로
  바꾸면 안 된다(바꾸면 현재 모델 기준 감지가 전부 무시되는 회귀, 이미 한 번 발생,
  `.agentfiles/decisionLog.md` 참고) — **새 camelCase 모델이 실제로 재학습되어
  Promote/Deploy될 때 `tracking2.py`도 그 시점에 같이 전환**해야 한다.
- 통 위치는 모델 학습 클래스가 아니라 `tracking2.py`의 고정 ROI 계약입니다.
- Promote 전에는 `evaluation.json`의 mAP50과 recall을 확인합니다.
- 로컬 bootstrap과 문서가 감사한 `bestTop.pt`의 해시가 다르므로 기준 모델 신원을 먼저 확정합니다.
- registry 승격 뒤 `tracking2.py`의 `bestTop.pt` 반영과 reload까지 검증해야 운영 배포 완료입니다.
- 실제 운영 영상과 GPU 환경에서 E2E 테스트를 완료한 뒤 자동 실행을 연결합니다.

## 코드 수정 원칙

파이프라인 코드를 변경할 때는 다음을 함께 반영합니다.

1. 처음 보는 사람이 처리 목적과 데이터 흐름을 이해할 수 있는 주석 또는 docstring을 추가합니다.
2. 메모리, 파일 형식, 경로 또는 실행 방법이 달라지면 이 README도 함께 수정합니다.
3. 주석에는 코드 자체를 그대로 반복하기보다 처리 이유, 입력·출력, 실패 시 동작을 설명합니다.
4. Python 이름은 외부 형식이나 필수 호환 항목이 아니라면 camelCase를 사용합니다.
