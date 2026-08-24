"""7단계: 기준 모델과 후보 모델을 동일한 test split으로 비교합니다."""

import json
from pathlib import Path

from stages.autoLabeling import loadYoloModel


class EvaluateModelStage:
    """두 모델의 mAP, precision, recall 계산을 담당합니다."""

    def _evaluate_model(self, model_path: Path) -> dict[str, float]:
        """지정된 모델을 dataset_current의 고정 test split으로 평가합니다.

        mAP50은 IoU 0.5 기준 평균 정밀도이고, mAP50-95는 여러 IoU 기준을 평균한 더 엄격한
        지표입니다. precision은 오탐 억제 정도, recall은 실제 객체를 놓치지 않는 정도를 나타냅니다.
        기존 모델과 후보 모델이 완전히 같은 조건에서 평가되도록 내부 공통 함수로 사용합니다.
        """
        cfg = self.config["training"]
        metrics = loadYoloModel(model_path).val(
            data=str(self.dataset_root / "data.yaml"),
            split="test",
            imgsz=int(cfg["imgsz"]),
            device=cfg["device"],
            workers=int(cfg["workers"]),
            verbose=False,
        )
        return {
            "map50": float(metrics.box.map50),
            "map50_95": float(metrics.box.map),
            "precision": float(metrics.box.mp),
            "recall": float(metrics.box.mr),
        }

    def evaluate(self) -> None:
        """기준 모델과 새 후보 모델을 동일한 데이터와 설정으로 평가합니다.

        training_result.json에서 후보 best.pt를 찾고 두 모델의 mAP50, mAP50-95, precision,
        recall을 계산합니다. 비교 결과와 사용한 모델 경로는 evaluation.json에 저장됩니다.
        이 단계 역시 모델을 교체하지 않으며 promote 단계가 판단할 근거만 만듭니다.
        """
        if not self.training_result.exists():
            raise RuntimeError("먼저 train 단계를 실행하세요.")
        training = json.loads(self.training_result.read_text(encoding="utf-8"))
        candidate_model = Path(training["best_model"])
        result = {
            "baseline_model": str(self.base_model.resolve()),
            "candidate_model": str(candidate_model.resolve()),
            "baseline": self._evaluate_model(self.base_model),
            "candidate": self._evaluate_model(candidate_model),
        }
        self.evaluation_result.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))


def evaluateModel(pipeline: EvaluateModelStage) -> None:
    """오케스트레이터에서 모델 평가 단계를 실행합니다."""
    pipeline.evaluate()