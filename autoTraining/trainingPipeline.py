"""SortMaster CCTV 자동 재학습 파이프라인의 실행 순서와 공통 상태를 관리합니다.

실제 단계 로직은 stages 폴더에 있으며 이 파일은 설정 로드, 작업 경로 초기화,
CLI 단계 선택과 실행 순서만 담당합니다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common.causalImages import CausalImagesMixin
from common.pipelineUtilities import loadConfig, resolvePath
from stages.autoLabeling import AutoLabelingStage, autoLabel
from stages.buildDataset import BuildDatasetStage, buildDataset
from stages.evaluateModel import EvaluateModelStage, evaluateModel
from stages.extractFrames import ExtractFramesStage, extractFrames
from stages.promoteModel import PromoteModelStage, promoteModel
from stages.reviewLabels import ReviewLabelsStage, reviewLabels
from stages.selectFrames import SelectFramesStage, selectFrames
from stages.trainModel import TrainModelStage, trainModel

projectRoot = Path(__file__).resolve().parents[1]
defaultConfig = Path(__file__).with_name("pipelineConfig.yaml")


class TrainingPipeline(
    CausalImagesMixin,
    ExtractFramesStage,
    SelectFramesStage,
    AutoLabelingStage,
    ReviewLabelsStage,
    BuildDatasetStage,
    TrainModelStage,
    EvaluateModelStage,
    PromoteModelStage,
):
    """모든 stage가 공유하는 설정과 파일 경로를 초기화합니다."""

    def __init__(self, configPath: Path):
        self.projectRoot = projectRoot
        self.configPath = configPath
        self.config = loadConfig(configPath)
        paths = self.config["paths"]

        self.videos_dir = resolvePath(projectRoot, paths["videos"])
        self.workspace = resolvePath(projectRoot, paths["workspace"])
        self.base_dataset = resolvePath(projectRoot, paths["base_dataset"])
        self.baseAutolabelModel = resolvePath(projectRoot, paths["baseAutolabelModel"])
        self.newAutolabelModel = resolvePath(projectRoot, paths["newAutolabelModel"])
        self.deployed_model = resolvePath(projectRoot, paths["deployed_model"])

        self.frames_root = self.workspace / "frames_all"
        self.candidates_root = self.workspace / "candidates"
        self.auto_labels_root = self.workspace / "auto_labels"
        self.annotated_root = self.workspace / "annotated"
        self.approved_root = self.workspace / "approved"
        self.manual_root = self.workspace / "manual_review"
        self.rejected_root = self.workspace / "rejected"
        self.dataset_root = self.workspace / "dataset_current"
        self.runs_root = self.workspace / "runs"

        self._frameIndexCache = None

        self.frames_manifest = self.workspace / "frames.jsonl"
        self.candidates_manifest = self.workspace / "candidates.jsonl"
        self.labels_manifest = self.workspace / "labels.jsonl"
        self.reviews_manifest = self.workspace / "reviews.jsonl"
        self.training_result = self.workspace / "training_result.json"
        self.evaluation_result = self.workspace / "evaluation.json"


def parseArgs() -> argparse.Namespace:
    """실행할 단계와 선택적인 설정 파일 경로를 읽습니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["extract", "select", "label", "review", "build", "train", "evaluate", "promote", "all"],
    )
    parser.add_argument("--config", type=Path, default=defaultConfig)
    return parser.parse_args()


def main() -> None:
    """선택된 단계를 명시된 순서로 실행합니다."""
    args = parseArgs()
    pipeline = TrainingPipeline(args.config.resolve())
    stageHandlers = {
        "extract": extractFrames,
        "select": selectFrames,
        "label": autoLabel,
        "review": reviewLabels,
        "build": buildDataset,
        "train": trainModel,
        "evaluate": evaluateModel,
        "promote": promoteModel,
    }
    selectedStages = list(stageHandlers) if args.stage == "all" else [args.stage]
    for stageName in selectedStages:
        print(f"\n===== {stageName.upper()} =====")
        stageHandlers[stageName](pipeline)


if __name__ == "__main__":
    main()