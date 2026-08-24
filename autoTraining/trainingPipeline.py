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

        self.videosDirectory = resolvePath(projectRoot, paths["videos"])
        self.workspace = resolvePath(projectRoot, paths["workspace"])
        self.baseDataset = resolvePath(projectRoot, paths["baseDataset"])
        self.baseAutoLabelModel = resolvePath(projectRoot, paths["baseAutoLabelModel"])
        self.newAutoLabelModel = resolvePath(projectRoot, paths["newAutoLabelModel"])
        self.deployedModel = resolvePath(projectRoot, paths["deployedModel"])

        self.framesRoot = self.workspace / "framesAll"
        self.candidatesRoot = self.workspace / "candidates"
        self.autoLabelsRoot = self.workspace / "autoLabels"
        self.annotatedRoot = self.workspace / "annotated"
        self.approvedRoot = self.workspace / "approved"
        self.manualRoot = self.workspace / "manualReview"
        self.rejectedRoot = self.workspace / "rejected"
        self.datasetRoot = self.workspace / "datasetCurrent"
        self.runsRoot = self.workspace / "runs"

        self._frameIndexCache = None

        self.framesManifest = self.workspace / "frames.jsonl"
        self.candidatesManifest = self.workspace / "candidates.jsonl"
        self.labelsManifest = self.workspace / "labels.jsonl"
        self.reviewsManifest = self.workspace / "reviews.jsonl"
        self.trainingResult = self.workspace / "trainingResult.json"
        self.evaluationResult = self.workspace / "evaluation.json"


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