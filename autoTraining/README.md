# SortMaster 자동 재학습 파이프라인

CCTV 이벤트 영상에서 신규 학습 후보를 만들고, 자동 라벨링·Qwen 검수·사람 승인을 거쳐
MongoDB 학습 데이터 원본에 추가한 뒤 YOLO 모델을 재학습·평가·승격·배포하는 파이프라인입니다.

## 핵심 원칙

- MongoDB의 `trainingSamples` 컬렉션과 `trainingImages` GridFS가 기존·신규 학습 데이터의 원본입니다.
- `events`와 `topMedia`는 TOP 카메라 이벤트 GIF 수집용이며 학습 데이터 저장소와 분리합니다.
- 로컬 디스크는 프레임 선별·검수·학습을 위한 배치 작업공간과 고정 스냅샷입니다.
- Qwen 판정과 관계없이 사람의 최종 `approved` 데이터만 MongoDB에 추가합니다.
- 재학습은 실행 도중 MongoDB가 바뀌어도 영향받지 않도록 SyncDataset이 고정한 스냅샷만 사용합니다.
- Golden Test는 학습 데이터와 분리하며 Publish·Sync·Build 대상에 포함하지 않습니다.
- Promote와 Deploy를 분리하여 평가 통과만으로 운영 모델이 자동 교체되지 않게 합니다.
- `.env`는 공유 문서나 코드에 실값을 복사하지 않으며 사용자 사전 고지 없이 수정하지 않습니다.

## 전체 흐름

```text
MongoDB events + visitClips + topMedia GridFS
  ↓
0. Collect
   지정 날짜의 ELEV-TOP/misclassification 이벤트와 미확정 방문 GIF 수집
  ↓
1. Extract
   GIF/영상 프레임 추출
  ↓
2. Select
   간격·선명도·밝기 기준으로 후보 프레임 선별
  ↓
3. Label
   현재 활성 YOLO 기준 모델을 사이클에 고정하고 자동 라벨 생성
  ↓
4. Review
   vLLM Qwen-VL 검수 및 전체 결과를 사람 검수 큐로 전달
  ↓
localhost 사람 검수 UI
   승인 / YOLO 라벨 수정 승인 / 거절
  ↓
5. HumanReview
   결정 누락·중복·허용값·승인 라벨 파일 검증
  ↓
6. Publish
   승인 이미지·라벨을 MongoDB trainingSamples/trainingImages에 추가
  ↓
7. SyncDataset
   현재 클래스·입력 계약과 일치하는 전체 active 데이터를 로컬에 고정
  ↓
8. Build
   sourceGroup 단위 train/val/test 분리 및 data.yaml 생성
  ↓
9. Train
   신규 YOLO 후보 모델 학습
  ↓
10. Evaluate
   고정 Golden Test로 기준 모델과 후보 모델 비교
  ↓
11. Promote
   품질 기준을 만족한 후보를 불변 registry에 승격
  ↓ 사람의 배포 승인
12. Deploy
   tracking2.py용 bestTop.pt 원자적 교체
```

Deploy는 모델 교체 전에 로드·클래스 계약·더미 프레임 추론 smoke test를 자동 수행합니다. `tracking2.py` 프로세스 재시작과 실패 시 자동 rollback은 아직 수동입니다.

## 단계별 자동화 수준

아래 분류는 목표가 아니라 **현재 코드의 동작 기준**입니다.

- **자동**: 단계가 시작되면 사람의 판단이나 입력 없이 완료됩니다.
- **반자동**: 처리는 코드가 수행하지만 사람의 검수·승인 또는 별도 실행 명령이 필요합니다.
- **수동**: 핵심 판단이나 작업을 사람이 직접 수행합니다.

| 단계 | 자동화 수준 | 현재 동작 | 사람이 해야 하는 일 |
|---|---|---|---|
| 0. Collect | 자동 | MongoDB의 확정 오분류 이벤트와 `matchedEventIds`가 빈 미확정 `visitClips`를 조회하고 `topMedia` GridFS에서 대상 GIF를 수집합니다. | 실행 전 DB 연결과 대상 날짜를 확인합니다. |
| 1. Extract | 자동 | 수집 영상에서 프레임을 추출합니다. | 없음 |
| 2. Select | 자동 | 간격·선명도·밝기 기준으로 후보 프레임을 선별합니다. | 선별 기준 변경 시 설정값을 조정합니다. |
| 3. Label | 자동 | 고정한 YOLO 기준 모델로 라벨을 생성합니다. | 없음 |
| 4. Review | 자동 | Qwen-VL이 라벨을 검토하고 모든 항목을 검수 큐로 보냅니다. | Qwen 장애나 비정상 응답을 확인합니다. |
| 사람 검수 UI | 수동 | 시스템이 이미지·YOLO 라벨·Qwen 의견을 표시하고 결정을 저장합니다. | 각 항목을 승인, 라벨 수정 승인 또는 거절합니다. |
| 5. HumanReview | 반자동 | 코드가 사람 결정의 누락·중복·허용값과 라벨 파일을 검증합니다. | 앞 단계에서 모든 항목의 최종 결정을 내려야 합니다. |
| 6. Publish | 자동 | 사람 승인 데이터만 MongoDB 학습 데이터 원본에 추가합니다. | 운영 DB 쓰기 전 대상 배치를 확인합니다. |
| 7. SyncDataset | 자동 | 계약에 맞는 전체 active 데이터를 고정 로컬 스냅샷으로 동기화합니다. | 없음 |
| 8. Build | 자동 | `sourceGroup` 단위로 split하고 `data.yaml`을 생성합니다. | 없음 |
| 9. Train | 자동 | GPU에서 신규 YOLO 후보 모델을 학습합니다. | 실행 전 GPU 자원과 학습 설정을 확인합니다. |
| 10. Evaluate | 자동 | Golden Test로 기준 모델과 후보 모델을 비교합니다. | 사전에 독립된 Golden Test를 준비·관리합니다. |
| 11. Promote | 반자동 | 별도 명령을 실행하면 품질 기준을 재검증하고 모델을 registry에 승격합니다. | 평가 결과를 확인하고 승격 실행 여부를 결정합니다. |
| 12. Deploy | 반자동 | 승격 모델의 smoke test를 통과한 경우에만 운영 모델 파일로 원자적으로 교체합니다. | 배포를 승인하고 이후 프로세스를 재시작합니다. |
| Rollback | 반자동 | 지정한 registry 모델의 smoke test를 통과한 경우에만 운영 모델로 되돌립니다. | 롤백 버전을 선택하고 프로세스를 재시작합니다. |

`runDaily` 전체 흐름의 자동화 수준은 **반자동**입니다. Collect부터 Review까지 자동 실행한 뒤 사람 검수가
끝날 때까지 대기하고, 검수가 완료되면 HumanReview부터 Evaluate까지 자동으로 이어집니다. Promote와
Deploy는 `runDaily`에 포함되지 않으며 사람의 평가 확인과 배포 승인을 거쳐 각각 별도로 실행합니다.
## 현재 구현 상태

2026-08-27 기준 코드 상태입니다.

| 항목 | 상태 | 내용 |
|---|---|---|
| 13개 파이프라인 단계 | 구현됨 | Collect부터 Deploy까지 CLI 연결 완료 |
| 사람 검수 전 자동 구간 | 구현됨 | `prepareDailyBatch` |
| 사람 검수 UI | 구현됨 | localhost UI, 결정과 수정 라벨 원자적 저장 |
| 사람 검수 후 자동 구간 | 구현됨 | `HumanReview → Publish → SyncDataset → Build → Train → Evaluate` |
| 단일 명령 전체 실행 | 구현됨 | `runDaily`가 검수 완료를 기다린 뒤 평가까지 자동 진행 |
| MongoDB 이벤트·미확정 방문 수집 | 구현됨·실DB 미검증 | `events.imageFileId`와 `matchedEventIds: []`인 `visitClips.imageFileId`를 `topMedia`에서 수집 |
| GPU 방문 트랙 신호 | 미구현 | `tracking2.py`가 `trackStarted`/`trackEnded`를 아직 보내지 않아 시도 후 미확정 트랙을 visitClip에 연결하지 못함 |
| Qwen-VL 실제 연결 | 연결됨·역할 축소 확정 | 프레임 단위 판정에만 사용. **박스 좌표는 쓰지 않음** — 실측 결과 위치 정확도가 사용 불가 수준(IoU 중앙값 0.00, `decisionLog.md` 참고). 스키마 미준수 폭주는 `max_tokens`로 제한 |
| MongoDB 학습 데이터 Publish | 구현됨·실DB 미검증 | 승인 데이터만 추가, 이미지 중복·계약 충돌 검사 |
| MongoDB 학습 데이터 Sync | 구현됨·실DB 미검증 | active 데이터 다운로드와 이미지·라벨 해시 검증 |
| Build | 구현됨 | MongoDB 스냅샷만 사용, 비율·최소 train/val 검사, 원자적 교체 |
| 모델 학습·평가 | 구현됨·E2E 미검증 | 실제 Golden Test와 GPU 학습 필요 |
| 모델 registry·배포 | 구현됨 | 해시 검증, 불변 후보/registry, 원자적 파일 교체, 수동 rollback |
| Python 환경 | 확인됨 | Conda `env_py311`, Python 3.11, compile/import 통과 |
| bootstrap 모델 | 존재 | `models/bootstrap/best.pt` |
| 활성 모델 포인터 | 초기 상태 | `models/current.json` 없음 |
| 일일 입력 | 없음 | `inputVideos` 파일 없음 |
| MongoDB 배치 스냅샷 | 없음 | 실제 Publish/Sync 실행 전 |
| Golden Test | 없음 | `goldenTest` 디렉터리 없음 |
| 모델 smoke test | 구현됨 | Deploy·Rollback 전 자동 실행, 독립 `smokeTest` 명령 제공 |
| 운영 프로세스 재시작·자동 rollback | 미구현 | 모델 교체 후 `tracking2.py` 재시작과 장애 시 복구는 수동 |
| 전체 E2E | 미검증 | MongoDB, vLLM, Golden Test, GPU 학습이 필요 |


최근 확인에서 설정된 MongoDB endpoint는 TCP timeout이 발생했습니다. 주소·계정 값을 문서에
기록하지 말고 서버 Docker 상태, 포트 공개, 방화벽과 네트워크/VPN을 확인해야 합니다.

## MongoDB 학습 데이터 계약

설정 기본값:

```yaml
trainingDatasetStore:
  samplesCollection: trainingSamples
  imagesBucket: trainingImages
```

`trainingImages`에는 실제 학습 이미지를 저장합니다. `trainingSamples` 문서에는 다음 필드를 기록합니다.

| 필드 | 의미 |
|---|---|
| `_id` | UUID 기반 sample ID |
| `imageFileId` | `trainingImages` GridFS ObjectId |
| `imageSha256` | 이미지 중복·무결성 확인용 해시 |
| `labelSha256` | 정규화된 YOLO 라벨 해시 |
| `yoloLabels` | `classId centerX centerY width height` 문자열 배열 |
| `classNames` | 모델 외부 클래스명과 순서 |
| `inputMode` | `rgb` 또는 `causal` |
| `imageExtension` | 저장 이미지 확장자 |
| `status` | 현재 Sync 대상은 `active` |
| `source` | 기본값 `dailyHumanReview` |
| `sourceEventId` | 원본 이벤트 ID |
| `sourceGroup` | split 누수 방지용 원본 영상 그룹 |
| `batchId` | 등록한 검수 배치 |
| `createdAt` | UTC 등록 시각 |

`imageSha256`에는 unique index를 만들고, `status + createdAt`에는 조회 index를 만듭니다.
같은 이미지와 같은 계약이 이미 있으면 중복 등록을 건너뜁니다. 같은 이미지에 다른 라벨,
`classNames` 또는 `inputMode`가 있으면 조용히 덮어쓰지 않고 실패합니다.

Publish는 GridFS 업로드 후 메타데이터 저장에 실패하면 업로드한 파일을 보상 삭제합니다.
MongoDB 원본의 기존 샘플을 자동 삭제하거나 수정하지 않습니다. 제외가 필요하면 별도 승인된
관리 절차로 `status`를 변경해야 합니다.

### 기존 학습 데이터 최초 등록

기존 데이터도 위 계약으로 MongoDB에 최초 적재되어 있어야 SyncDataset이 가져올 수 있습니다.
현재 코드는 사람 승인 신규 데이터의 Publish만 제공하며, 로컬 기존 데이터셋을 일괄 이관하는
관리 명령은 아직 없습니다. 운영 DB에 대한 초기 이관은 데이터 구조·권한·백업을 확인한 뒤
별도 도구로 수행해야 합니다.

## 클래스와 입력 계약

현재 운영 `bestTop.pt`와 재학습 bootstrap 모델의 클래스명과 순서는 다음과 같습니다.
이 네 문자열만 TOP-view YOLO 체크포인트의 외부 계약 예외이며 `model.names`와 정확히 일치해야 합니다.

```text
0 TrashNormal
1 TrashPaper
2 TrashRecyclables
3 TrashCoffeecup
```

TOP-view YOLO 모델 클래스명만 lower camelCase 대신 PascalCase를 사용합니다. 특히 `TrashCoffeecup`은 일반적인
`TrashCoffeeCup` 표기와 다르지만 모델 체크포인트의 실제 문자열이므로 임의로 고치지 않습니다.
`pipelineConfig.yaml`의 `dataset.classes`는 이 계약으로 변경됐습니다.

`tracking2.py`의 `EXPECTED_CLASS_NAMES`, `TRASH_CLASSES`, `TRASH_TYPE_MAP`도 위 PascalCase
계약으로 전환했습니다. `TRASH_TYPE_MAP`의 출력은 기존 API 계약인 `normal`, `paper`,
`recyclables`, `coffeecup`을 유지하므로 백엔드와 DB 값은 변경되지 않습니다. 체크포인트 로드와
`model.names` 대조는 통과했으며 실제 TOP 영상의 탐지·투입 판정 검증은 아직 필요합니다.
물리 쓰레기통은 YOLO 클래스가 아닙니다. `tracking2.py`의 `RULE_BASED_BIN_ROIS`가 통 위치를
판정합니다.

현재 설정에는 아직 입력 계약 차이가 있습니다.

| 항목 | 현재 값 |
|---|---|
| 자동 라벨/Publish `inputMode` | `causal` |
| 자동 라벨 추론 `imgsz` | 416 |
| Train `imgsz` | 640 |
| 운영 `tracking2.py` | 단일 BGR, 416 |
| 데이터셋 문서 목표 | 640×640 letterbox |

bootstrap 체크포인트 신원과 함께 `rgb/causal`, 416/640 계약을 확정하기 전 전체 E2E를
운영 모델 생성 목적으로 실행하면 안 됩니다. SyncDataset은 다른 `classNames`나 `inputMode`
샘플을 제외하여 계약 혼합을 막습니다.

## 실행 환경

SortMaster 루트에서 실행합니다.

```powershell
cd <SORTMASTER_ROOT>
conda activate env_py311
python autoTraining\trainingPipeline.py --help
```

확인된 주요 버전은 `requirements.txt`에 고정되어 있습니다.

- Python 3.11
- Ultralytics 8.4.117
- PyTorch 2.7.1+cu118
- Torchvision 0.22.1+cu118
- OpenCV 4.14.0.94
- NumPy 2.4.4
- Motor 3.7.1
- PyMongo 4.17.0

GPU 서버의 CUDA/드라이버와 맞지 않으면 PyTorch 빌드를 먼저 조정해야 합니다.

## 환경변수

MongoDB 연결은 프로젝트 루트 `.env`의 다음 변수를 사용합니다.

```dotenv
MONGO_HOST=<MONGO_HOST>
DB_PORT=<MONGO_PORT>
DB_NAME=<MONGO_DATABASE>
DB_USER=<PERSONAL_DB_USER>
DB_PASSWORD=<PERSONAL_DB_PASSWORD>
```

Qwen-VL 포트는 `LLM_PORT`를 사용합니다. 실제 IP, 계정, 비밀번호, 토큰은 README나 코드에
기록하지 않습니다. `.env` 변경이 필요하면 반드시 사용자에게 먼저 알립니다.

## 주요 설정

[`pipelineConfig.yaml`](pipelineConfig.yaml):

```yaml
eventStore:
  source: gridFs
  utcOffsetHours: 9
  serverSelectionTimeoutMs: 5000

frames:
  saveEveryN: 1
  candidateEveryN: 3
  minLaplacianVariance: 20.0
  minBrightness: 20.0
  maxBrightness: 235.0

inference:
  inputMode: causal
  imgsz: 416
  confidence: 0.20
  device: 0

dataset:
  trainRatio: 0.80
  valRatio: 0.10
  testRatio: 0.10

training:
  epochs: 100
  imgsz: 640
```

Build는 세 split 비율이 각각 0~1이고 합계가 1인지 검증합니다. 영상 계열 프레임이 서로 다른
split에 섞이지 않도록 `sourceGroup`의 SHA-256 기반으로 결정적으로 분리합니다. train 또는
val이 비면 학습을 시작하지 않습니다. 일일 test split 데이터는 학습에 사용하지 않으며 실제
비교평가는 별도 Golden Test를 사용합니다.

## 실행 방법

### 한 번에 실행

다음 명령 하나로 사람 검수를 포함해 평가까지 실행합니다.

```powershell
python autoTraining\trainingPipeline.py runDaily --batchId <YYYY-MM-DD>
```

`runDaily` 실행 흐름:

```text
Collect → Extract → Select → Label → Review
→ 검수 UI 자동 실행 및 사람 결정 대기
→ 모든 항목 검수 완료 시 UI 자동 종료
→ HumanReview → Publish → SyncDataset → Build → Train → Evaluate
```

마지막 검수 결정을 저장하면 다음 단계가 즉시 이어집니다. 검수 도중 UI를 `Ctrl+C`로 종료하면
Publish로 넘어가지 않고 실패합니다. 브라우저를 자동으로 열 수 없는 서버에서는 `--noBrowser`를
사용하고 표시된 localhost 포트를 SSH 포워딩합니다.

주의: 검수 완료 후 실제 MongoDB에 승인 데이터를 추가하고 GPU 학습까지 실행합니다. 대상 배치,
DB 연결, Golden Test, 입력 계약과 GPU 자원을 먼저 확인해야 합니다.

기존의 1차·검수·2차 분리 명령도 진단과 수동 운영을 위해 계속 사용할 수 있습니다.

하루치 작업은 모든 단계에서 같은 `--batchId`를 사용합니다.

### 1차 자동 구간

```powershell
python autoTraining\trainingPipeline.py prepareDailyBatch --batchId <YYYY-MM-DD>
```

실행 범위:

```text
Collect → Extract → Select → Label → Review
```

이 명령은 `humanReviewQueue.jsonl`을 만든 뒤 멈춥니다.

### 사람 검수

```powershell
python autoTraining\trainingPipeline.py reviewUi --batchId <YYYY-MM-DD>
```

브라우저를 자동으로 열 수 없는 서버:

```powershell
python autoTraining\trainingPipeline.py reviewUi --batchId <YYYY-MM-DD> --noBrowser
```

기본 주소는 `http://127.0.0.1:8765`입니다. UI는 localhost에만 바인딩합니다. 모든 큐 ID에
승인 또는 거절 결정이 있어야 다음 단계로 진행할 수 있습니다.

### 2차 자동 구간

주의: 다음 명령의 Publish 단계는 실제 MongoDB에 승인 데이터를 추가합니다.

```powershell
python autoTraining\trainingPipeline.py continueAfterHumanReview --batchId <YYYY-MM-DD>
```

실행 범위:

```text
HumanReview → Publish → SyncDataset → Build → Train → Evaluate
```

진단 또는 재실행이 필요하면 개별 단계도 실행할 수 있습니다.

```powershell
python autoTraining\trainingPipeline.py publish --batchId <YYYY-MM-DD>
python autoTraining\trainingPipeline.py syncDataset --batchId <YYYY-MM-DD>
python autoTraining\trainingPipeline.py build --batchId <YYYY-MM-DD>
```

Publish는 이미지 해시 기준으로 동일 계약의 중복을 건너뛰므로 같은 배치 재실행에 대비합니다.
그러나 학습 원본에 쓰는 명령이므로 배치와 사람 결정 파일을 먼저 확인해야 합니다.

### 승격·배포·롤백

```powershell
python autoTraining\trainingPipeline.py promote --batchId <YYYY-MM-DD>
python autoTraining\trainingPipeline.py deploy --batchId <YYYY-MM-DD>
python autoTraining\trainingPipeline.py rollback --batchId <YYYY-MM-DD> --version model-<VERSION>
```

Deploy와 rollback은 모델을 교체하기 전에 smoke test를 자동 수행하지만 프로세스를 재시작하지 않습니다.
현재 운영 모델만 독립적으로 검사하려면 다음 명령을 사용합니다.

```powershell
python autoTraining\trainingPipeline.py smokeTest --batchId <YYYY-MM-DD>
# 운영 GPU 장치까지 확인하려면:
python autoTraining\trainingPipeline.py smokeTest --batchId <YYYY-MM-DD> --smokeDevice 0
```

기본 smoke 장치는 `cpu`이며 모델 로드, SHA-256, 클래스명·순서, 416×416 더미 BGR 프레임 추론을
검증합니다. 실제 카메라 연결, 객체 탐지 성능과 투입 판정은 이 smoke test의 범위가 아닙니다.

## 주요 산출물

```text
autoTraining/
├─ pipelineConfig.yaml
├─ trainingPipeline.py
├─ common/
├─ stages/
│  ├─ collectEventMedia.py
│  ├─ trainingDatasetStore.py
│  └─ ...
├─ inputVideos/<batchId>/
├─ datasets/<batchId>/
├─ goldenTest/
├─ models/
│  ├─ bootstrap/best.pt
│  ├─ candidates/<batchId>/<runName>/best.pt
│  ├─ registry/model-<version>.pt
│  └─ current.json
└─ workspace/batches/<batchId>/
   ├─ collectedMedia.jsonl
   ├─ frames.jsonl
   ├─ candidates.jsonl
   ├─ labels.jsonl
   ├─ reviews.jsonl
   ├─ humanReviewQueue.jsonl
   ├─ humanDecisions.jsonl
   ├─ humanReviews.jsonl
   ├─ publishedSamples.jsonl
   ├─ datasetSnapshot/
   │  ├─ images/
   │  ├─ labels/
   │  └─ samples.jsonl
   ├─ trainingResult.json
   ├─ evaluation.json
   ├─ deployment.json
   └─ smokeTest.json
```

| 단계 | 주요 출력 또는 변경 |
|---|---|
| Collect | `inputVideos/<batchId>/*.gif`, `collectedMedia.jsonl` |
| Extract | `framesAll/`, `frames.jsonl` |
| Select | `candidates/`, `candidates.jsonl` |
| Label | `autoLabels/`, `annotated/`, `labels.jsonl` |
| Review | `reviews.jsonl`, `humanReviewQueue.jsonl` |
| HumanReview | `humanReviews.jsonl` |
| Publish | MongoDB `trainingSamples`/`trainingImages`, `publishedSamples.jsonl` |
| SyncDataset | `datasetSnapshot/`, `datasetSnapshot/samples.jsonl` |
| Build | `datasets/<batchId>/`, `data.yaml` |
| Train | 후보 `best.pt`, `trainingResult.json` |
| Evaluate | `evaluation.json` |
| Promote | registry 모델, `models/current.json` |
| Deploy | 운영 `bestTop.pt`, smoke 결과가 포함된 `deployment.json` |
| SmokeTest | `smokeTest.json` |

JSONL은 행 단위로 읽고 프로세스별 임시 파일에 기록한 뒤 `flush`/`fsync`와 원자적 교체를
사용합니다. SyncDataset과 Build도 임시 디렉터리를 완성한 뒤 기존 결과와 교체합니다.

## 실행 전 필수 확인

1. MongoDB 서버·포트·방화벽·인증과 `trainingSamples`/`trainingImages` 접근 권한
2. 기존 학습 데이터의 최초 MongoDB 등록
3. Golden Test 준비
4. bootstrap 체크포인트 신원과 클래스 계약
5. `rgb/causal` 및 416/640 입력 계약
6. GPU 서버 vLLM `/v1/models`와 멀티모달 응답
7. 실제 이벤트의 `imageFileId`와 `topMedia` GIF
8. 학습·Qwen·실시간 추론 동시 실행 시 GPU/VRAM 경합

## 현재 설계 평가와 개선 우선순위

현재 파이프라인은 `수집 → 사람 검수 → MongoDB 게시 → 전체 데이터 동기화 → 학습 → 평가`가
한 흐름으로 연결된 **실사용 가능한 프로토타입**입니다. 다만 장시간 무인 운영과 안전한 모델 배포까지
고려한 운영형 파이프라인으로 보기에는 아래 보완이 필요합니다.

### 1순위: 학습과 운영의 입력 계약 통일

현재 자동 라벨링과 Publish는 `causal`, 416을 기준으로 하지만 Train은 640, 운영
`tracking2.py`는 단일 BGR 416을 사용하고 데이터셋 문서는 640×640 letterbox를 목표로 합니다.
이 상태에서는 학습 성능이 좋아도 운영 입력에서 같은 성능을 재현한다고 보장하기 어렵습니다.

- bootstrap 모델과 운영 모델이 사용할 `inputMode`를 `rgb` 또는 `causal` 중 하나로 확정
- 라벨링·학습·Golden Test·운영 추론의 색상 채널, `imgsz`, letterbox 방식을 동일하게 적용
- 계약이 다른 샘플과 모델은 Publish·Sync·Promote 단계에서 차단

### 2순위: 수집 데이터의 편향 완화와 GPU 트랙 신호 연동

Collect는 오분류 이벤트뿐 아니라 `matchedEventIds`가 빈 `visitClips`도 이미 재학습 후보로 수집합니다.
따라서 YOLO가 트랙조차 만들지 못한 방문 영상은 확보할 수 있습니다. 다만 현재 `tracking2.py`가
`trackStarted`/`trackEnded`를 전송하지 않으므로, 트랙을 만들었지만 최종 확정하지 못한 사례를
`unresolvedTrackIds`로 연결·구분하는 동작은 아직 완성되지 않았습니다. GPU 신호 연동 후 다음 범주를
균형 있게 선별해야 합니다.

- 오분류와 낮은 confidence 사례
- 미감지 가능성이 있는 방문 구간
- 트랙은 생성됐지만 투입을 확정하지 못한 방문 구간
- 정상 분류 사례의 대표 표본
- 사람이 없거나 쓰레기가 아닌 hard negative

Qwen-VL은 후보 우선순위와 이상 사례 설명을 돕는 보조 수단으로 사용하고, MongoDB Publish의 최종 결정은
사람 검수를 유지합니다.

### 3순위: 중단 재개 가능한 배치 실행

`runDaily`는 한 번에 실행하기 편하지만 현재는 하나의 장시간 프로세스에 의존합니다. 프로세스나 서버가
중단되어도 처음부터 다시 실행하지 않도록 배치별 상태 머신이 필요합니다.

- 단계별 `pending/running/succeeded/failed` 상태와 시작·종료 시각 기록
- 마지막 성공 단계 다음부터 재개하는 `resume` 명령
- 동일 `batchId`의 중복 실행을 막는 잠금과 stale lock 복구
- 재시도 횟수, 실패 원인, 생성 산출물의 추적

### 4순위: 재현 가능한 데이터셋 버전 관리

현재 배치 스냅샷만으로는 특정 모델이 정확히 어떤 MongoDB 샘플 집합으로 학습됐는지 장기적으로
추적하기 어렵습니다. 학습 시작 전에 immutable dataset version을 만들고 다음 정보를 보존해야 합니다.

- 데이터셋 버전 ID와 생성 시각
- 정렬된 sample ID 목록 또는 manifest와 manifest SHA-256
- 클래스·입력 계약·split 정책
- 학습 결과의 dataset version 참조

이 항목은 MongoDB 스키마 추가가 필요하므로 구현 전에 `Docs/ERD.md`와
`Docs/DATASET_DESCRIPTION.md`를 함께 갱신하고 CTO 검토를 받아야 합니다.

### 5순위: 배포 안전장치 완성

Promote와 Deploy는 분리되어 있으며 모델 smoke test는 Deploy·Rollback 전에 자동 수행됩니다. 다만 운영 프로세스 재시작과 실패 시 자동 rollback은 아직 수동입니다.
Golden Test 기준을 확정한 뒤 승인된 후보에만 release를 허용하고, 배포 후 상태 확인에 실패하면 직전
모델과 프로세스로 자동 복구해야 합니다.

권장 구현 순서는 다음과 같습니다.

1. 입력 계약 확정 및 전 단계 통일
2. `tracking2.py`의 `trackStarted`/`trackEnded` 연동과 방문 클립 분류 완성
3. 기존 데이터 MongoDB 이관 도구
4. 배치 상태·재개·잠금
5. 데이터셋 버전과 모델 계보 기록
6. Golden Test 및 단계별 자동 테스트
7. Qwen 장애 시 fallback
8. 프로세스 재시작·상태 확인·자동 rollback을 포함한 배포 자동화
9. 스케줄·재시도·알림
## 남은 개발 및 검증 작업

- PascalCase `bestTop.pt`로 실제 TOP 영상 탐지·클래스 매핑·투입 판정 검증
- `tracking2.py`의 `trackStarted`/`trackEnded` 신호 전송 연동
- 기존 로컬 데이터셋을 MongoDB 계약으로 안전하게 최초 이관하는 관리자 도구
- MongoDB Publish/Sync의 mock 기반 단위 테스트와 운영 DB 소규모 통합 테스트
- Qwen 응답 JSON Schema의 객체·필수 타입·추가 필드 완전 검증
- Review 재실행 전 상태별 참고 폴더 정리
- 배치 상태 파일, 실패 단계 재개, 동일 배치 실행 잠금
- split별 최소 이미지뿐 아니라 최소 영상·클래스 분포 검증
- `testRatio` 제거 또는 Golden Test 체계에 맞는 의미 재정의
- 검수 UI에서 그린 박스의 크기 조절(핸들 드래그) — 그리기·선택·삭제는 구현됨
- 독립 `autoTraining` Compose 서비스, 스케줄, 재시도와 알림
- 배포 승인형 release 명령
- Deploy 후 `tracking2.py` 재시작·서비스 상태 확인·자동 rollback
- 실제 GPU 서버 전체 E2E

## 실패와 복구

- Publish 중 MongoDB 문서 저장이 실패하면 해당 실행에서 먼저 올린 GridFS 이미지를 삭제합니다.
- 같은 이미지가 다른 라벨·클래스·입력 계약으로 존재하면 Publish를 중단합니다.
- Sync 이미지 또는 라벨 해시가 다르면 기존 정상 스냅샷을 유지하고 실패합니다.
- Build가 실패하면 기존 정상 `datasets/<batchId>`을 복구합니다.
- ManifestWriter가 관리하는 JSONL은 단계 성공 때만 교체됩니다.
- 모델 rollback은 교체 전 smoke test를 자동 수행하지만 `tracking2.py` 재시작과 서비스 상태 확인은 직접 수행해야 합니다.

## 코드 변경 원칙

1. Python 내부 이름, 설정 키와 매니페스트 필드는 외부 계약을 제외하고 camelCase를 사용합니다. 예외는 TOP-view YOLO 체크포인트의 `model.names` 4종뿐이며, 다른 모델 클래스명과 프로젝트 내부 이름에는 이 예외를 확대 적용하지 않습니다.
2. 입력·출력·실패 동작 또는 경로가 바뀌면 이 README와 데이터셋 계약 문서를 함께 수정합니다.
3. MongoDB 원본을 삭제하거나 기존 sample을 덮어쓰는 기능은 별도 승인 없이 추가하지 않습니다.
4. `.env`, 서버 주소, 계정, 비밀번호와 토큰을 코드·문서·커밋에 넣지 않습니다.
5. 운영 DB 쓰기 명령은 대상 배치와 사람 승인 결과를 확인한 뒤 실행합니다.
