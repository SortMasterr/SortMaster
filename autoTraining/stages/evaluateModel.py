"""7단계: 학습 사이클에 고정된 기준 모델과 후보 모델을 비교합니다."""
import json
from pathlib import Path

from common.modelRegistry import calculateFileSha256
from stages.autoLabeling import loadYoloModel


class EvaluateModelStage:
    def _evaluateModel(self, modelPath: Path) -> dict[str, float]:
        cfg = self.config["training"]
        metrics = loadYoloModel(modelPath).val(
            data=str(self.datasetRoot / "data.yaml"), split="test",
            imgsz=int(cfg["imgsz"]), device=cfg["device"],
            workers=int(cfg["workers"]), verbose=False,
        )
        return {
            "map50": float(metrics.box.map50), "map50To95": float(metrics.box.map),
            "precision": float(metrics.box.mp), "recall": float(metrics.box.mr),
        }

    def evaluate(self) -> None:
        if not self.trainingResult.exists():
            raise RuntimeError("먼저 train 단계를 실행하세요.")
        baseline = self.getCycleModel()
        training = json.loads(self.trainingResult.read_text(encoding="utf-8"))
        candidateModel = Path(training["candidateModel"])
        candidateHash = calculateFileSha256(candidateModel)
        if training.get("baselineSha256") != baseline.sha256:
            raise RuntimeError("학습 기준 모델과 현재 사이클 기준 모델이 다릅니다.")
        if training.get("candidateSha256") != candidateHash:
            raise RuntimeError("학습 후 후보 모델 파일이 변경되었습니다.")
        result = {
            "runName": training["runName"],
            "baselineVersion": baseline.version,
            "baselineModel": baseline.path,
            "baselineSha256": baseline.sha256,
            "candidateModel": str(candidateModel.resolve()),
            "candidateSha256": candidateHash,
            "baseline": self._evaluateModel(baseline.resolvedPath()),
            "candidate": self._evaluateModel(candidateModel),
        }
        self.evaluationResult.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def evaluateModel(pipeline: EvaluateModelStage) -> None:
    pipeline.evaluate()
