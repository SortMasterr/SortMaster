"""SortMaster CCTV 자동 재학습 파이프라인의 실행 순서와 공통 상태를 관리합니다."""
from __future__ import annotations

import argparse
from pathlib import Path

from common.causalImages import CausalImagesMixin
from common.modelRegistry import loadCycleModel, pinCycleModel, resolveActiveModel
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
    """모든 stage가 공유하는 설정, 경로와 고정 기준 모델을 초기화합니다."""

    def __init__(self, configPath: Path):
        self.projectRoot = projectRoot
        self.configPath = configPath
        self.config = loadConfig(configPath)
        paths = self.config["paths"]

        self.videosDirectory = resolvePath(projectRoot, paths["videos"])
        self.workspace = resolvePath(projectRoot, paths["workspace"])
        self.baseDataset = resolvePath(projectRoot, paths["baseDataset"])
        self.bootstrapModel = resolvePath(projectRoot, paths["bootstrapModel"])
        self.modelRegistry = resolvePath(projectRoot, paths["modelRegistry"])
        self.candidateModels = resolvePath(projectRoot, paths["candidateModels"])
        self.activeModelPointer = resolvePath(projectRoot, paths["activeModelPointer"])

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
        self.cycleManifest = self.workspace / "cycleModel.json"

    def pinActiveModel(self):
        """현재 활성 모델을 새 학습 사이클의 불변 기준 모델로 고정합니다."""
        return pinCycleModel(
            self.cycleManifest,
            resolveActiveModel(self.bootstrapModel, self.activeModelPointer),
        )

    def getCycleModel(self):
        """label 단계에서 고정한 기준 모델을 해시 검증 후 반환합니다."""
        return loadCycleModel(self.cycleManifest)


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["extract", "select", "label", "review", "build", "train", "evaluate", "promote", "all"],
    )
    parser.add_argument("--config", type=Path, default=defaultConfig)
    return parser.parse_args()


def main() -> None:
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
