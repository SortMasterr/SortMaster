# SortMaster 자동 학습 파이프라인

CCTV 영상에서 학습 후보 프레임을 만들고, 기존 YOLO 모델로 자동 라벨링한 뒤 Qwen-VL 검수, 데이터셋 병합, 재학습, 비교 평가 및 모델 승격까지 수행하는 파이프라인입니다.

## 전체 흐름

```text
CCTV 영상
  ↓
1. Extract  : 영상 프레임 추출
  ↓
2. Select   : 학습 후보 프레임 선별
  ↓
3. Label    : baseAutolabel/best.pt로 자동 라벨링
  ↓
4. Review   : Qwen-VL 검수
  ├─ approved
  ├─ manual_review
  └─ rejected
  ↓
5. Build    : 기존 데이터셋 + 승인된 신규 데이터 병합
  ↓
6. Train    : 신규 YOLO 모델 학습
  ↓
7. Evaluate : 기존 모델과 신규 모델 비교
  ↓
8. Promote  : 기준 통과 시 신규 모델 승격
```

## 구현 상태

구현된 기능:

- CCTV 영상 프레임 추출과 JPG 저장
- 선명도, 밝기, 프레임 간격을 이용한 후보 선별
- 기존 YOLO 모델을 사용한 자동 라벨링
- RGB 및 causal 입력 지원
- YOLO 라벨과 bbox 표시 이미지 생성
- Ollama의 Qwen-VL을 이용한 자동 검수
- 승인 데이터와 기존 데이터셋 병합
- 영상 단위 train/val/test 분리
- 신규 모델 학습 및 `newAutolabel/best.pt` 저장
- 기존 모델과 신규 모델 성능 비교
- 기준 통과 모델의 백업 및 승격

추가 구현이 필요한 기능:

- `manual_review` 데이터를 수정하는 검수 UI
- 수정된 수동 라벨을 `reviews.jsonl`에 반영하는 기능
- Docker Compose의 독립 `autoTraining` 서비스
- 스케줄 실행, 실패 재시도 및 알림
- 승격 모델을 실시간 추론 서비스에 자동 반영하는 배포 절차
- 실제 GPU 서버에서의 전체 E2E 테스트

## 디렉터리 구조

```text
autoTraining/
├─ README.md
├─ trainingPipeline.py
├─ pipelineConfig.yaml
├─ requirements.txt
├─ Dockerfile
├─ common/
│  ├─ causalImages.py
│  └─ pipelineUtilities.py
├─ stages/
│  ├─ extractFrames.py
│  ├─ selectFrames.py
│  ├─ autoLabeling.py
│  ├─ reviewLabels.py
│  ├─ buildDataset.py
│  ├─ trainModel.py
│  ├─ evaluateModel.py
│  └─ promoteModel.py
├─ inputVideos/
├─ baseDataset/
├─ models/
│  ├─ baseAutolabel/best.pt
│  └─ newAutolabel/best.pt
├─ workspace/
├─ modelArchive/
└─ promotedModels/current.pt
```

설정, 경로, JSONL 처리는 `pipelineUtilities.py` 하나로 통합했습니다. 사용되지 않던 `configLoader.py`, `manifestManager.py`, `pathManager.py`는 중복을 피하기 위해 제거했습니다.

## 모델 역할

| 경로 | 역할 |
|---|---|
| `models/baseAutolabel/best.pt` | 자동 라벨링, 초기 학습 가중치, 기존 모델 평가 |
| `models/newAutolabel/best.pt` | 새로 학습된 후보 모델 |
| `promotedModels/current.pt` | 평가 기준을 통과해 승격된 모델 |

기본 모델은 학습 과정에서 덮어쓰지 않습니다.

## 실행 환경

SortMaster 루트에서 Python 3.11 환경을 준비합니다.

```powershell
python -m venv .venv-autoTraining
.\.venv-autoTraining\Scripts\Activate.ps1
pip install -r autoTraining/requirements.txt
```

주요 의존성:

- `ultralytics`: YOLO 추론, 학습, 평가
- `opencv-python`: 영상과 이미지 처리
- `numpy`: 이미지 배열 처리
- `PyYAML`: 파이프라인 설정과 `data.yaml` 처리

GPU 서버에서는 설치된 CUDA 버전에 맞는 PyTorch가 필요합니다. 현재 개발 환경에 `cv2`가 없으면 CLI import 단계에서 `ModuleNotFoundError`가 발생합니다.

## 입력 준비

CCTV 영상은 다음 위치에 넣습니다.

```text
autoTraining/inputVideos/
```

지원 확장자는 `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`, `.m4v`입니다.

기존 YOLO 데이터셋 구조:

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
autoTraining/models/baseAutolabel/best.pt
```

Review 단계에서는 `pipelineConfig.yaml`의 Ollama 주소와 Qwen-VL 모델 설정을 사용합니다.

## 설정

설정 파일은 `autoTraining/pipelineConfig.yaml`입니다.

주요 경로:

```yaml
paths:
  videos: autoTraining/inputVideos
  workspace: autoTraining/workspace
  base_dataset: autoTraining/baseDataset
  baseAutolabelModel: autoTraining/models/baseAutolabel/best.pt
  newAutolabelModel: autoTraining/models/newAutolabel/best.pt
  deployed_model: autoTraining/promotedModels/current.pt
```

프레임 설정:

```yaml
frames:
  save_every_n: 1
  jpeg_quality: 95
  candidate_every_n: 3
  min_laplacian_variance: 20.0
  min_brightness: 20.0
  max_brightness: 235.0
```

- `save_every_n`: 저장할 원본 프레임 간격
- `candidate_every_n`: 후보 검사 간격
- `min_laplacian_variance`: 최소 선명도
- `min_brightness`, `max_brightness`: 허용 밝기 범위

추론 설정:

```yaml
inference:
  input_mode: causal
  imgsz: 416
  confidence: 0.20
  device: 0
```

- `rgb`: 현재 프레임만 사용
- `causal`: t-2, t-1, t 프레임의 회색조를 각각 하나의 채널로 결합
- `device: 0`: 첫 번째 GPU
- CPU 사용 시 `device: cpu`

기본 모델을 학습할 때 사용한 입력 방식과 `input_mode`가 같아야 합니다.

## 단계별 실행

모든 명령은 SortMaster 루트에서 실행합니다.

```powershell
python autoTraining/trainingPipeline.py extract
python autoTraining/trainingPipeline.py select
python autoTraining/trainingPipeline.py label
python autoTraining/trainingPipeline.py review
python autoTraining/trainingPipeline.py build
python autoTraining/trainingPipeline.py train
python autoTraining/trainingPipeline.py evaluate
python autoTraining/trainingPipeline.py promote
```

전체 단계를 연속 실행할 수도 있습니다.

```powershell
python autoTraining/trainingPipeline.py all
```

운영 환경에서는 Review 결과와 `evaluation.json`을 사람이 확인한 다음 Build 및 Promote를 실행하는 방식을 권장합니다.

## 단계별 출력

| 단계 | 주요 출력 |
|---|---|
| Extract | `workspace/frames_all`, `frames.jsonl` |
| Select | `workspace/candidates`, `candidates.jsonl` |
| Label | `workspace/auto_labels`, `annotated`, `labels.jsonl` |
| Review | `approved`, `manual_review`, `rejected`, `reviews.jsonl` |
| Build | `workspace/dataset_current`, `data.yaml` |
| Train | `workspace/runs`, `models/newAutolabel/best.pt`, `training_result.json` |
| Evaluate | `workspace/evaluation.json` |
| Promote | `promotedModels/current.pt`, `modelArchive` 백업 |

## JSONL 매니페스트

각 줄이 독립된 JSON 객체인 JSONL 형식을 사용합니다.

| 파일 | 내용 |
|---|---|
| `frames.jsonl` | 원본 영상과 추출 프레임 정보 |
| `candidates.jsonl` | 선별된 학습 후보 |
| `labels.jsonl` | 자동 라벨, bbox, 검수 이미지 경로 |
| `reviews.jsonl` | Qwen-VL 결정, 오류, 사용 모델 |
| `training_result.json` | 학습 결과와 신규 모델 경로 |
| `evaluation.json` | 기존 모델과 신규 모델의 평가 결과 |

매니페스트에는 절대 경로가 포함됩니다. 다른 서버나 Docker 컨테이너로 workspace를 복사하면 경로가 달라질 수 있으므로 해당 환경에서 앞 단계를 다시 실행하거나 동일한 볼륨 경로로 마운트해야 합니다.

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

현재 `Dockerfile`은 존재하지만 `docker-compose.yml`에 독립적인 `autoTraining` 서비스가 완전히 연결된 상태는 아닙니다. 따라서 현재는 GPU 서버의 Python 환경에서 직접 실행하거나 Docker 이미지를 수동으로 빌드하고 필요한 폴더를 볼륨으로 연결해야 합니다.

## 주의 사항

- `manual_review`와 `rejected` 데이터는 Build에 포함되지 않습니다.
- Build는 기존 `workspace/dataset_current`를 새로 생성하므로 필요한 결과는 먼저 백업합니다.
- 클래스 순서와 YOLO class ID는 반드시 일치해야 합니다.
- Promote 전에는 `evaluation.json`의 mAP50과 recall을 확인합니다.
- 실제 운영 영상과 GPU 환경에서 E2E 테스트를 완료한 뒤 자동 실행을 연결합니다.

## 코드 수정 원칙

파이프라인 코드를 변경할 때는 다음을 함께 반영합니다.

1. 처음 보는 사람이 처리 목적과 데이터 흐름을 이해할 수 있는 주석 또는 docstring을 추가합니다.
2. 메모리, 파일 형식, 경로 또는 실행 방법이 달라지면 이 README도 함께 수정합니다.
3. 주석에는 코드 자체를 그대로 반복하기보다 처리 이유, 입력·출력, 실패 시 동작을 설명합니다.
4. Python 이름은 외부 형식이나 필수 호환 항목이 아니라면 camelCase를 사용합니다.
