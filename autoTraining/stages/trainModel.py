"""6단계: 고정된 활성 모델을 초기 가중치로 사용해 후보 모델을 학습합니다."""
import os
import shutil
from datetime import datetime

from common.modelRegistry import calculateFileSha256
from common.pipelineUtilities import atomicWriteJson
from stages.autoLabeling import loadYoloModel


class TrainModelStage:
    def train(self) -> None:
        dataYaml = self.datasetRoot / "data.yaml"
        if not dataYaml.exists():
            raise RuntimeError("먼저 build 단계를 실행하세요.")
        baseline = self.getCycleModel()
        cfg = self.config["training"]
        runName = "autoFinetune-" + datetime.now().strftime("%Y%m%d_%H%M%S")
        model = loadYoloModel(baseline.resolvedPath())
        model.train(
            data=str(dataYaml), epochs=int(cfg["epochs"]), imgsz=int(cfg["imgsz"]),
            batch=int(cfg["batch"]), workers=int(cfg["workers"]), device=cfg["device"],
            amp=bool(cfg["amp"]), patience=int(cfg["patience"]),
            project=str(self.runsRoot), name=runName, exist_ok=False,
        )
        bestPath = self.runsRoot / runName / "weights" / "best.pt"
        if not bestPath.is_file():
            raise FileNotFoundError(f"학습 결과 모델이 없습니다: {bestPath}")

        candidatePath = self.candidateModels / runName / "best.pt"
        candidatePath.parent.mkdir(parents=True, exist_ok=False)
        temporaryPath = candidatePath.with_suffix(".pt.tmp")
        shutil.copy2(bestPath, temporaryPath)
        os.replace(temporaryPath, candidatePath)
        result = {
            "runName": runName,
            "baselineVersion": baseline.version,
            "baselineModel": baseline.path,
            "baselineSha256": baseline.sha256,
            "trainingArtifact": str(bestPath.resolve()),
            "candidateModel": str(candidatePath.resolve()),
            "candidateSha256": calculateFileSha256(candidatePath),
        }
        # 학습이 중단된 JSON을 Evaluate가 읽지 않도록 완료된 결과만 원자적으로 공개한다.
        atomicWriteJson(self.trainingResult, result)
        print(f"[TRAIN] 불변 후보 모델 저장: {candidatePath}")


def trainModel(pipeline: TrainModelStage) -> None:
    pipeline.train()
