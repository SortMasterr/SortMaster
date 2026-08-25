"""SortMaster 일일 자동 재학습 파이프라인의 단계, 배치와 모델 상태를 관리합니다."""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from common.causalImages import CausalImagesMixin
from common.modelRegistry import loadCycleModel, pinCycleModel, resolveActiveModel
from common.pipelineUtilities import loadConfig, resolvePath
from stages.autoLabeling import AutoLabelingStage, autoLabel
from stages.buildDataset import BuildDatasetStage, buildDataset
from stages.deployModel import DeployModelStage, deployModel
from stages.evaluateModel import EvaluateModelStage, evaluateModel
from stages.extractFrames import ExtractFramesStage, extractFrames
from stages.humanReview import HumanReviewStage, validateHumanReview
from stages.promoteModel import PromoteModelStage, promoteModel
from stages.reviewLabels import ReviewLabelsStage, reviewLabels
from stages.selectFrames import SelectFramesStage, selectFrames
from stages.trainModel import TrainModelStage, trainModel

projectRoot = Path(__file__).resolve().parents[1]
defaultConfig = Path(__file__).with_name("pipelineConfig.yaml")
batchIdPattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class TrainingPipeline(
    CausalImagesMixin, ExtractFramesStage, SelectFramesStage, AutoLabelingStage,
    ReviewLabelsStage, HumanReviewStage, BuildDatasetStage, TrainModelStage,
    EvaluateModelStage, PromoteModelStage, DeployModelStage,
):
    """한 batchId의 산출물을 격리하고 같은 기준 모델을 전체 사이클에 고정합니다."""

    def __init__(self, configPath: Path, batchId: str):
        if not batchIdPattern.fullmatch(batchId):
            raise ValueError("batchId는 영문·숫자로 시작하고 영문·숫자·점·밑줄·하이픈만 허용합니다.")
        self.projectRoot = projectRoot
        self.configPath = configPath
        self.config = loadConfig(configPath)
        self.batchId = batchId
        paths = self.config["paths"]

        self.videosRoot = resolvePath(projectRoot, paths["videos"])
        # 하루치 입력을 다른 배치가 다시 처리하지 않도록 batchId 하위만 읽는다.
        self.videosDirectory = self.videosRoot / batchId
        self.workspaceRoot = resolvePath(projectRoot, paths["workspace"])
        self.workspace = self.workspaceRoot / "batches" / batchId
        self.baseDataset = resolvePath(projectRoot, paths["baseDataset"])
        self.goldenTest = resolvePath(projectRoot, paths["goldenTest"])
        self.bootstrapModel = resolvePath(projectRoot, paths["bootstrapModel"])
        self.modelRegistry = resolvePath(projectRoot, paths["modelRegistry"])
        self.candidateModels = resolvePath(projectRoot, paths["candidateModels"]) / batchId
        self.activeModelPointer = resolvePath(projectRoot, paths["activeModelPointer"])

        self.framesRoot = self.workspace / "framesAll"
        self.candidatesRoot = self.workspace / "candidates"
        self.autoLabelsRoot = self.workspace / "autoLabels"
        self.annotatedRoot = self.workspace / "annotated"
        self.humanReviewRoot = self.workspace / "humanReview"
        # Qwen 분류별 사본은 검수 편의를 위한 뷰이며 Build의 승인 근거는 humanReviews.jsonl이다.
        self.approvedRoot = self.humanReviewRoot / "qwenApproved"
        self.manualRoot = self.humanReviewRoot / "qwenManualReview"
        self.rejectedRoot = self.humanReviewRoot / "qwenRejected"
        self.datasetRoot = self.workspace / "datasetCurrent"
        self.runsRoot = self.workspace / "runs"
        self._frameIndexCache = None

        self.framesManifest = self.workspace / "frames.jsonl"
        self.candidatesManifest = self.workspace / "candidates.jsonl"
        self.labelsManifest = self.workspace / "labels.jsonl"
        self.reviewsManifest = self.workspace / "reviews.jsonl"
        self.humanReviewQueue = self.workspace / "humanReviewQueue.jsonl"
        self.humanDecisionsManifest = self.workspace / "humanDecisions.jsonl"
        self.humanReviewsManifest = self.workspace / "humanReviews.jsonl"
        self.trainingResult = self.workspace / "trainingResult.json"
        self.evaluationResult = self.workspace / "evaluation.json"
        self.deploymentResult = self.workspace / "deployment.json"
        self.cycleManifest = self.workspace / "cycleModel.json"

    def pinActiveModel(self):
        return pinCycleModel(
            self.cycleManifest,
            resolveActiveModel(self.bootstrapModel, self.activeModelPointer),
        )

    def getCycleModel(self):
        return loadCycleModel(self.cycleManifest)


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=[
        "extract", "select", "label", "review", "humanReview", "build", "train",
        "evaluate", "promote", "deploy", "rollback", "prepareDailyBatch",
        "continueAfterHumanReview",
    ])
    parser.add_argument("--config", type=Path, default=defaultConfig)
    parser.add_argument("--batchId", default=date.today().isoformat())
    parser.add_argument("--version", help="rollback할 registry 모델 버전")
    return parser.parse_args()


def main() -> None:
    args = parseArgs()
    pipeline = TrainingPipeline(args.config.resolve(), args.batchId)
    stageHandlers = {
        "extract": extractFrames, "select": selectFrames, "label": autoLabel,
        "review": reviewLabels, "humanReview": validateHumanReview,
        "build": buildDataset, "train": trainModel, "evaluate": evaluateModel,
        "promote": promoteModel, "deploy": deployModel,
    }
    groupedStages = {
        # 사람 검수 전까지만 자동 실행하고 반드시 멈춘다.
        "prepareDailyBatch": ["extract", "select", "label", "review"],
        # 모든 사람 결정이 검증돼야 데이터셋 생성과 평가로 넘어간다. 승격은 별도 승인이다.
        "continueAfterHumanReview": ["humanReview", "build", "train", "evaluate"],
    }
    if args.stage == "rollback":
        if not args.version:
            raise ValueError("rollback에는 --version이 필요합니다.")
        pipeline.rollback(args.version)
        return
    selectedStages = groupedStages.get(args.stage, [args.stage])
    for stageName in selectedStages:
        print(f"\n===== {stageName.upper()} batchId={args.batchId} =====")
        stageHandlers[stageName](pipeline)


if __name__ == "__main__":
    main()
