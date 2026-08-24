"""6단계: 병합 데이터셋으로 후보 YOLO 모델을 추가 학습합니다."""

import json
from datetime import datetime

from stages.autoLabeling import loadYoloModel


class TrainModelStage:
    """Ultralytics 학습 실행과 best.pt 위치 기록을 담당합니다."""

    def train(self) -> None:
        """기준 모델을 초기 가중치로 사용하여 후보 YOLO 모델을 추가 학습합니다.

        epochs, image size, batch, GPU device, workers, AMP, patience는 pipelineConfig.yaml에서
        읽습니다. 학습 결과는 실행 시각이 포함된 workspace/runs 하위 폴더에 저장됩니다.
        이후 단계가 정확한 best.pt를 찾을 수 있도록 training_result.json에 절대 경로를 기록합니다.
        이 단계는 운영 모델을 직접 변경하지 않습니다.
        """
        data_yaml = self.dataset_root / "data.yaml"
        if not data_yaml.exists():
            raise RuntimeError("먼저 build 단계를 실행하세요.")
        cfg = self.config["training"]
        run_name = "auto_finetune_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        model = loadYoloModel(self.base_model)
        model.train(
            data=str(data_yaml),
            epochs=int(cfg["epochs"]),
            imgsz=int(cfg["imgsz"]),
            batch=int(cfg["batch"]),
            workers=int(cfg["workers"]),
            device=cfg["device"],
            amp=bool(cfg["amp"]),
            patience=int(cfg["patience"]),
            project=str(self.runs_root),
            name=run_name,
            exist_ok=False,
        )
        best_path = self.runs_root / run_name / "weights" / "best.pt"
        result = {"run_name": run_name, "best_model": str(best_path.resolve())}
        self.training_result.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[TRAIN] 새 모델: {best_path}")


def trainModel(pipeline: TrainModelStage) -> None:
    """오케스트레이터에서 모델 학습 단계를 실행합니다."""
    pipeline.train()