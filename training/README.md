# training/ — 모델팀 데이터셋 준비 스크립트

`autoTraining/`(자동 재학습 파이프라인)과는 **별개**다. 이쪽은 모델팀이 **초기 학습
데이터셋을 손으로 만들 때** 쓴 일회성 유틸 모음이고, 백엔드/GPU 상시 서비스가 import하거나
호출하지 않는다.

| 구분 | `training/` (이 폴더) | `autoTraining/` |
|---|---|---|
| 목적 | 초기 데이터셋 수집·라벨링·증강·분할(수동) | 운영 이벤트 기반 자동 재학습 사이클 |
| 실행 | 사람이 직접 스크립트 하나씩 | `trainingPipeline.py`의 단계 실행 |
| 경로 | 개인 PC 절대경로 하드코딩 | `pipelineConfig.yaml` |

> **주의**: 아래 스크립트는 전부 파일 상단에 **개인 PC의 Windows 절대경로가 하드코딩**돼
> 있다(`C:\final_project\...`, `C:\Users\Woori\Pictures\...`). 다른 사람이 돌리려면 경로를
> 먼저 자기 환경에 맞게 고쳐야 한다 — CLI 인자를 받는 건 `cupholder_autolabeling.py`뿐이다.

## 파일

| 파일 | 역할 |
|---|---|
| `frame_extraction.py` | 촬영 영상(mp4)에서 `extract_interval_seconds`(기본 0.3초)마다 프레임 1장씩 추출해 이미지 폴더 생성. 데이터셋 만들기의 첫 단계 |
| `auto_labeling/auto_labeling2.py` | 이미 학습된 YOLO 가중치로 이미지 폴더를 훑어 YOLO 형식 `.txt` 라벨을 자동 생성(1차 라벨). 사람이 검수하는 걸 전제로 함 |
| `auto_labeling/cupholder_autolabeling.py` | 컵홀더처럼 **화면에서 위치가 고정된** 객체용. 대표 이미지 한 장에 마우스로 박스를 한 번 그리면 같은 폴더의 모든 라벨 파일에 그 박스를 같은 클래스로 추가한다. 유일하게 CLI 인자(`folder`, `--image`, `--class-id`, `--yes`, `--no-backup`)를 받으며 기본적으로 라벨 백업을 만든다 |
| `auto_labeling/auto_labeling_model.ipynb` | **Google Colab** 노트북. Drive에 올린 `yolo_dataset_trash`로 **`yolov8s.pt`**를 200 epochs/`imgsz=640`/`batch=16` 파인튜닝해 `trash_auto_label` 모델을 만들고, 같은 노트북 안에서 그 모델로 예측(`conf=0.5`)까지 돌린다. **가장 초기의 부트스트랩 라벨러** — `auto_labeling2.py`가 쓰는 모델과는 계보가 다르다(아래 참고) |
| `data_augmentation/blurr_img.py` | 폴더 내 jpg에 랜덤 커널(5~13) 블러를 적용해 증강 |
| `data_augmentation/bright_img.py` | 폴더 내 jpg에 랜덤 밝기 변화를 적용해 증강 |
| `add_data.py` | 기존 데이터셋에 새 이미지+라벨을 train/val/test로 나눠 **추가 병합**(`split_cupholder`/`add_train_data`/`copy_trash_train_data`) |
| `data_split.py` | 이미지+라벨 폴더를 train/val/test로 분할 |
| `classnum_count.py` | 데이터셋의 train/val/test별 **클래스 등장 횟수 집계**. 클래스 불균형 확인용 |
| `Dockerfile` | 위 스크립트와 무관 — 팀 공용 JupyterLab 학습 컨테이너(`training` 서비스, `docker compose --profile training`). 자세한 건 루트 `README.md` 참고 |

## 모델 계보 (YOLOv8 → YOLO26)

이 폴더에 YOLOv8과 YOLO26이 같이 나와서 헷갈리기 쉬운데, **시간 순서가 다르다**.

1. **`auto_labeling_model.ipynb` → `yolov8s`** — 라벨이 하나도 없는 상태에서 시작해야 해서,
   손으로 라벨링한 소량 데이터로 `yolov8s`를 먼저 파인튜닝(`trash_auto_label`)해 1차 라벨을
   양산했다. **부트스트랩 전용**이고 운영에 올라간 적 없다.
2. **`auto_labeling2.py` → `trash_yolo26n_aug/weights/best.pt`** — 파일명의 "2"가 가리키는
   2차 라벨러. 여기서부터 **YOLO26n + 증강**으로 바뀌었다.
3. **운영 `bestTop.pt`** — 체크포인트 메타데이터를 직접 열어보면 베이스가 `yolo26n.pt`,
   런 이름이 `trash_yolo26n_aug`, 클래스가
   `TrashNormal`/`TrashPaper`/`TrashRecyclables`/`TrashCoffeecup`이다. 즉 **2번의 라벨러와
   운영 모델이 같은 학습 계보**다.

즉 라벨링과 운영이 "v8=라벨링 / 26=운영"으로 갈리는 게 아니라, **1번만 v8이고 그 뒤로는
라벨링·운영 둘 다 YOLO26**이다. 더 좋아진 모델로 다음 라벨을 뽑아 다시 학습시키는
부트스트랩 루프이기 때문 — 자동화된 버전이 `autoTraining/`이다.

프로젝트 문서 전반이 "YOLO26"으로만 서술하는 건 **운영 기준**이라 맞고, 여기 `yolov8s`가
남아있는 건 초기 데이터셋을 만든 실제 이력이라 그대로 둔다. 모델 선정 변천사
(YOLOv8-Nano/Medium → YOLO26 단독)는 `.agentfiles/decisionLog.md` 참고.

## 알려진 문제

- **`data_split.py`에 분할 함수가 두 버전 들어있다**: 8행 `split_yolo_dataset1(dataset_dir,
  val_count=10, test_count=20)`(초기 버전)과 185행 `split_yolo_dataset2(source_dir,
  dataset_dir, test_count=200, val_count=100)`(val:100/test:200로 늘린 버전). 함수명이
  달라 서로 덮어쓰지 않으며, 둘 다 파일 하단에서 자동 실행되지 않으므로 사람이 필요한 쪽을
  골라 직접 호출해야 한다.
- 파일 하단의 실행부가 주석 처리돼 있거나(`data_split.py`) 모듈 로드 시 바로 실행되는
  형태(`classnum_count.py`, `frame_extraction.py`)로 제각각이다.

## 파일명 규칙

이 폴더의 파일·함수명은 프로젝트 공통 camelCase 규칙(`.agentfiles/naming.md`)의 **예외로
snake_case를 유지**한다 — 모델팀이 Colab/외부 학습 도구 관례에 맞춰 작성했고, 이름을
바꾸면 노트북·개인 환경의 참조가 깨진다. 자세한 건 `.agentfiles/naming.md`의 "예외" 참고.

## 클래스명

학습 데이터셋의 클래스 구성은 `Docs/DATASET_DESCRIPTION.md`를 따른다. 실제 체크포인트가
내놓는 클래스명 문자열(`TrashNormal` 등)은 코드 컨벤션과 무관하게 모델이 실제로 내놓는
값과 정확히 일치시켜야 한다 — `.agentfiles/naming.md` 참고.
