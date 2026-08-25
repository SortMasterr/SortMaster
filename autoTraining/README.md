# SortMaster 자동 학습 파이프라인

CCTV 영상에서 학습 후보 프레임을 만들고, 기존 YOLO 모델로 자동 라벨링한 뒤 Qwen-VL 검수, 데이터셋 병합, 재학습, 비교 평가 및 모델 승격까지 수행하는 파이프라인입니다.

## 전체 흐름

```text
하루치 입력 영상 또는 향후 GridFS 수집 배치
  ↓
1. Extract  : 영상 프레임 추출
  ↓
2. Select   : 학습 후보 프레임 선별
  ↓
3. Label    : 활성 기준 모델 고정 후 자동 라벨링
  ↓
4. Review   : vLLM Qwen-VL 1차 검수
  ↓
모든 결과를 humanReviewQueue.jsonl로 전달
  ↓
사람이 humanDecisions.jsonl에 최종 승인/거절 및 수정 라벨 기록
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

2026-08-25 기준으로 Conda `env_py311` 환경에서 CLI import와 bootstrap 모델 로드까지
확인했습니다. 일일 배치 준비부터 운영 모델 파일 배포까지의 단계별 로직은 구현되어 있지만 입력 영상과 기존 데이터셋이 없고,
bootstrap 체크포인트와 설정의 클래스명이 일치하지 않고 최신 운영 데이터 수집·추론 경로가 아직
자동화 코드에 연결되지 않아 현재는 전체 E2E를 실행할 수 없습니다.

| 항목 | 상태 | 설명 |
|---|---|---|
| 일일 2구간 CLI | 구현됨 | `prepareDailyBatch`와 `continueAfterHumanReview`가 사람 검수 지점에서 분리됨 |
| Python 구문·설정 | 확인됨 | Python 파일 16개 AST, YAML, CLI import 검사 통과 |
| Python 환경 | 실행 가능 | Conda `env_py311`, Python 3.11.15 확인 |
| 필수 import | 실행 가능 | OpenCV 4.14.0, NumPy 2.4.4, PyYAML 6.0.3, Ultralytics 8.4.117 import 성공 |
| requirements 일치 | 불일치 | 현재 NumPy·OpenCV 버전이 `requirements.txt` 고정 버전과 다르므로 재현 환경으로는 추가 정리가 필요함 |
| CLI | 실행 가능 | `trainingPipeline.py --help` 정상 실행 |
| 입력 영상 | 준비 안 됨 | `inputVideos` 파일 0개이며 Extract의 `FileNotFoundError` 선행조건 확인 |
| 기존 데이터셋 | 준비 안 됨 | `autoTraining/baseDataset`이 존재하지 않음 |
| bootstrap 모델 | 로드 가능, 설정 불일치 | 5,393,150바이트 `.pt` 로드 성공. 4개 클래스는 최신 의미 계약과 맞지만 설정의 표기법이 다름 |
| 활성 모델 포인터 | 초기 상태 | 아직 `models/current.json`이 없어 최초 사이클은 bootstrap 모델을 선택함 |
| Qwen-VL 검수 | 코드 수정됨, 실서버 확인 필요 | Compose vLLM의 `/v1/models`, `/v1/chat/completions`를 사용함 |
| 모델 레지스트리 | 테스트 통과 | bootstrap 선택, 사이클 고정, SHA-256 검증, registry 승격과 active 포인터 해석 확인 |
| 감사 체크포인트 해시 | 불일치 | 로컬 bootstrap은 `757F...B7F2`, 문서의 `bestTop.pt`는 `2AF2...DFFC`이므로 동일 파일로 간주할 수 없음 |
| 운영 입력 호환성 | 불일치 | 자동화 기본값은 causal/416, `tracking2.py`는 단일 BGR 프레임/416, 데이터셋 문서는 640×640 letterbox를 명시함 |
| 학습 원본 수집 | 미구현 | 최신 설계는 로컬 GridFS 재사용이지만 현재 Extract는 `inputVideos`의 영상 파일만 읽음 |
| 운영 모델 파일 반영 | 구현됨, 재시작은 수동 | Deploy가 `tracking2.py`용 `bestTop.pt`를 해시 검증 후 원자적으로 교체하며 재시작·smoke test는 별도임 |
| 전체 E2E | 미검증 | 실제 영상, 기존 데이터셋, Qwen-VL 서버와 GPU 학습을 연결한 실행 기록이 없음 |

### 구현된 기능

- CCTV 영상 프레임 추출과 JPG 저장
- 선명도, 밝기, 프레임 간격을 이용한 후보 선별
- 기존 YOLO 모델을 사용한 자동 라벨링
- RGB 및 causal 입력 지원
- YOLO 라벨과 bbox 표시 이미지 생성
- vLLM OpenAI 호환 API를 이용한 Qwen-VL 자동 검수
- Qwen 결과 전체의 사람 검수 큐 생성과 사람 결정 JSONL 검증
- 사람 최종 승인 데이터와 기존 train/val 데이터셋 병합
- 영상 단위 train/val/test 분리
- 신규 모델 학습 및 실행별 불변 `models/candidates/<batchId>/<runName>/best.pt` 저장
- 고정 Golden Test를 사용한 기존 모델과 신규 모델 성능 비교
- 최소 성능 향상 모델의 불변 registry 등록과 SHA-256 검증
- Promote와 분리된 운영 `bestTop.pt` 배포 및 registry 버전 롤백

### 실행 전 반드시 해결할 문제

1. **최신 TOP 클래스 계약과 현재 설정**
   - 최신 기준은 쓰레기 4종만 YOLO가 구분하는 구조입니다. 체크포인트 외부 클래스명과 순서는
     `trashNormal`, `trashPaper`, `trashRecyclables`, `trashCoffeeCup`입니다.
   - API 의미값은 각각 `normal`, `paper`, `recyclables`, `coffeeCup`으로 매핑됩니다.
     플라스틱과 캔은 `trashRecyclables`/`recyclables` 하나로 통합됐습니다.
   - 물리 통은 4개지만 YOLO 클래스가 아닙니다. `tracking2.py`의 `RULE_BASED_BIN_ROIS`가
     고정 화면 ROI로 통 위치를 판정하므로 자동 학습 데이터에 통 클래스를 추가하면 안 됩니다.
   - `pipelineConfig.yaml`도 같은 camelCase 클래스명과 순서를 사용해야 합니다. 기존 snake_case
     클래스명의 체크포인트는 새 계약과 불일치하므로 재학습하거나 모델 메타데이터를 명시적으로
     마이그레이션하기 전에는 운영 모델로 승격하지 않습니다.

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
   - 최신 아키텍처의 MongoDB GridFS 학습 원본 수집은 전용 버킷·메타데이터 계약이 없어 아직
     구현하지 않았습니다. 현재 Extract는 수동 `inputVideos`만 처리합니다.
   - Deploy 이후 `tracking2.py` 프로세스 재시작, smoke test와 실패 감지에 따른 자동 rollback은
     운영 방식(systemd/Docker)이 확정되지 않아 자동화하지 않았습니다.
4. **필수 데이터와 실행 자원**
   - Python 3.11과 필수 import는 준비되어 있습니다.
   - 현재 저장소에는 입력 영상과 `baseDataset`이 없습니다. 최신 설계대로라면 단순히 영상
     폴더를 채우는 것보다 GridFS 수집 단계와 데이터셋 생성 계약을 먼저 구현해야 합니다.
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

- 서로 다른 하위 폴더에 같은 이름의 영상이 있으면 영상 stem만 ID로 사용하므로 프레임 ID,
  출력 폴더와 causal 인덱스가 충돌할 수 있습니다.
- 기존 데이터셋의 causal 입력은 파일명 끝 숫자를 1, 2씩 줄여 이전 프레임을 찾습니다. 실제
  촬영 순서나 프레임 간격을 보장하지 않는 데이터셋에서는 잘못된 시간 채널이 결합될 수 있습니다.
- Build에서 신규 causal 이미지를 저장할 때 `cv2.imwrite()` 성공 여부를 확인하지 않아 이미지
  저장 실패 후 라벨만 남을 수 있습니다.
- Qwen-VL 응답은 JSON Schema를 완전하게 검증하지 않습니다. 객체 여부, 필수 필드 타입,
  추가 필드를 충분히 검사하지 않아 일부 잘못된 응답에서 전체 Review가 중단될 수 있습니다.
- Review를 다시 실행할 때 `approved`, `manualReview`, `rejected` 폴더를 정리하지 않아 최신
  `reviews.jsonl`과 과거 큐 파일이 서로 다를 수 있습니다. Build는 JSONL을 기준으로 처리합니다.
- Build는 기존 `datasetCurrent`를 먼저 삭제하므로 생성 중 실패하면 이전 정상 데이터셋도
  잃을 수 있습니다. JSONL 매니페스트와 달리 데이터셋 디렉터리는 원자적으로 교체하지 않습니다.
- 설정 스키마 검증이 없어 잘못된 `inputMode`, 비율, device 또는 누락 키가 처리 도중에야
  오류로 나타날 수 있습니다.

### 추가 구현이 필요한 기능

- `humanReviewQueue.jsonl`과 `humanDecisions.jsonl` 계약을 사용하는 사람 검수 UI
- Docker Compose의 독립 `autoTraining` 서비스
- 스케줄 실행, 실패 재시도 및 알림
- Deploy 후 `tracking2.py` 재시작, smoke test 및 실패 시 자동 rollback
- 실제 GPU 서버에서의 전체 E2E 테스트
- 실제 vLLM·Golden Test·GPU 학습을 포함한 단계별 단위 테스트와 소규모 E2E 자동 테스트
- MongoDB GridFS 학습 원본 수집 어댑터

### 권장 작업 순서

1. 확정된 쓰레기 4종의 외부 class names를 그대로 설정하고 bootstrap 체크포인트 신원을 확정합니다.
2. 자동화와 `tracking2.py`의 입력 방식·크기 계약을 통일하고 설정 스키마 검증을 추가합니다.
3. 실제 vLLM 서버로 멀티모달 JSON Schema 응답을 검증하고 GridFS 학습 원본 수집 단계를 구현합니다.
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
│  ├─ extractFrames.py
│  ├─ selectFrames.py
│  ├─ autoLabeling.py
│  ├─ reviewLabels.py
│  ├─ humanReview.py
│  ├─ buildDataset.py
│  ├─ trainModel.py
│  ├─ evaluateModel.py
│  ├─ promoteModel.py
│  └─ deployModel.py
├─ inputVideos/<batchId>/
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

| 패키지 | 현재 환경 | `requirements.txt` |
|---|---:|---:|
| Python | 3.11.15 | 프로젝트 지침 3.11 |
| OpenCV | 4.14.0 | 4.10.0.84 |
| NumPy | 2.4.4 | 1.26.4 |
| PyYAML | 6.0.3 | 6.0 이상 |
| Ultralytics | 8.4.117 | 8.0 이상 |

CLI 실행에는 성공했지만 OpenCV와 NumPy는 고정 버전과 다릅니다. 팀 공용/GPU 환경의 재현성을
위해서는 별도 환경에서 `requirements.txt`에 맞춰 설치하거나, 현재 조합을 공식 버전으로 채택한
뒤 requirements를 함께 갱신해야 합니다. GPU 서버에서는 설치된 CUDA 버전에 맞는 PyTorch도
필요합니다.

## 입력 준비

### 현재 코드의 수동 입력 방식

현재 구현된 Extract는 같은 `--batchId`의 CCTV 영상 파일만 다음 위치에서 읽습니다.

```text
autoTraining/inputVideos/<batchId>/
```

지원 확장자는 `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`, `.m4v`입니다. 이 방식은 로컬 개발과
수동 검증에는 사용할 수 있지만 최신 운영 데이터 수집 계약은 아닙니다.

### 최신 운영 데이터 수집 계약

최신 아키텍처에서는 이벤트의 학습용 원본 이미지를 로컬 MongoDB GridFS에서 재사용하고,
GPU 서버의 training 프로세스가 역방향 SSH 터널을 통해 읽기로 확정했습니다. 현재 파이프라인에는
GridFS 조회·다운로드·수집 매니페스트 생성 단계가 없으므로 별도 구현이 필요합니다. 운영 자동화가
완성되기 전까지 `inputVideos` 방식과 GridFS 방식의 결과를 같은 실행에서 혼합하지 않습니다.

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

위 명령은 Extract → Select → Label → Qwen Review를 실행하고
`workspace/batches/2026-08-25/humanReviewQueue.jsonl`을 만든 뒤 멈춥니다.

사람은 같은 배치 폴더에 `humanDecisions.jsonl`을 작성합니다.

```json
{"id":"video__frame_00000001","decision":"approved","reviewer":"reviewerId","reviewedAt":"2026-08-25T18:00:00+09:00"}
{"id":"video__frame_00000002","decision":"rejected","reviewer":"reviewerId","reviewedAt":"2026-08-25T18:01:00+09:00","notes":"bbox 오류"}
```

수정한 YOLO txt를 승인하려면 결정 행에 `labelPath`를 지정합니다. 모든 큐 id에 결정이 있어야
다음 단계로 진행되며 누락·중복·허용되지 않은 decision은 즉시 실패합니다.

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
| Extract | `workspace/batches/<batchId>/framesAll`, `frames.jsonl` |
| Select | 배치별 `candidates`, `candidates.jsonl` |
| Label | `workspace/autoLabels`, `annotated`, `labels.jsonl` |
| Review | `reviews.jsonl`, `humanReviewQueue.jsonl`, Qwen 판정별 참고 폴더 |
| HumanReview | `humanReviews.jsonl` |
| Build | 배치별 `datasetCurrent`, `data.yaml` |
| Train | `workspace/runs`, `models/candidates/<batchId>/<runName>/best.pt`, `trainingResult.json` |
| Evaluate | `workspace/evaluation.json` |
| Promote | `models/registry/model-<version>.pt`, `models/current.json` |
| Deploy | `WebApps/backend/models/trashdetect/bestTop.pt`, `deployment.json` |

## JSONL 매니페스트

각 줄이 독립된 JSON 객체인 JSONL 형식을 사용합니다.

| 파일 | 내용 |
|---|---|
| `frames.jsonl` | 원본 영상과 추출 프레임 정보 |
| `candidates.jsonl` | 선별된 학습 후보 |
| `labels.jsonl` | 자동 라벨, bbox, 검수 이미지 경로 |
| `reviews.jsonl` | Qwen-VL 결정, 오류, 사용 모델 |
| `trainingResult.json` | 학습 결과와 신규 모델 경로 |
| `evaluation.json` | 기존 모델과 신규 모델의 평가 결과 |

매니페스트에는 절대 경로가 포함됩니다. 다른 서버나 Docker 컨테이너로 workspace를 복사하면 경로가 달라질 수 있으므로 해당 환경에서 앞 단계를 다시 실행하거나 동일한 볼륨 경로로 마운트해야 합니다.

## camelCase 변경 후 기존 작업 데이터

설정 키, Python 내부 이름, 매니페스트 필드와 파이프라인이 생성하는 폴더 이름 및 YOLO 클래스명은 camelCase로 통일했습니다. 기존 workspace에 snake_case 필드나 클래스명으로 생성된 JSONL은 새 코드와 호환되지 않으므로 `extract` 단계부터 다시 실행해야 합니다.

Qwen-VL 설정은 `qwenVl`에 있으며 검수 결과는 camelCase 필드를 사용합니다. 현재 구현은 Compose의 vLLM OpenAI 호환 `/v1/models`, `/v1/chat/completions`를 호출합니다.

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
- Build는 해당 배치의 `workspace/batches/<batchId>/datasetCurrent`를 새로 생성하므로 필요한 결과는 먼저 백업합니다.
- TOP 모델 외부 클래스명은 `trashNormal`, `trashPaper`, `trashRecyclables`, `trashCoffeeCup` 순서를 보존해야 합니다.
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
