"""6단계: 병합 데이터셋으로 후보 YOLO 모델을 추가 학습합니다."""

import json
import os
import shutil
from datetime import datetime

from stages.autoLabeling import loadYoloModel


class TrainModelStage:
    """Ultralytics 학습 실행과 best.pt 위치 기록을 담당합니다."""

    def train(self) -> None:
        """기준 모델을 초기 가중치로 사용하여 후보 YOLO 모델을 추가 학습합니다.

        epochs, image size, batch, GPU device, workers, AMP, patience는 pipelineConfig.yaml에서
        읽습니다. 학습 결과는 실행 시각이 포함된 workspace/runs 하위 폴더에 저장됩니다.
        이후 단계가 정확한 best.pt를 찾을 수 있도록 trainingResult.json에 절대 경로를 기록합니다.
        이 단계는 운영 모델을 직접 변경하지 않습니다.
        """
        dataYaml = self.datasetRoot / "data.yaml"
        if not dataYaml.exists():
            raise RuntimeError("먼저 build 단계를 실행하세요.")
        cfg = self.config["training"]
        runName = "autoFinetune-" + datetime.now().strftime("%Y%m%d_%H%M%S")
        model = loadYoloModel(self.baseAutoLabelModel)
        model.train(
            data=str(dataYaml),
            epochs=int(cfg["epochs"]),
            imgsz=int(cfg["imgsz"]),
            batch=int(cfg["batch"]),
            workers=int(cfg["workers"]),
            device=cfg["device"],
            amp=bool(cfg["amp"]),
            patience=int(cfg["patience"]),
            project=str(self.runsRoot),
            name=runName,
            exist_ok=False,
        )
        bestPath = self.runsRoot / runName / "weights" / "best.pt"
        if not bestPath.is_file():
            raise FileNotFoundError(f"학습 결과 모델이 없습니다: {bestPath}")

        # 실행별 best.pt는 runs에 보존하고, 다음 단계가 참조하는 고정 경로에도 복사합니다.
        self.newAutoLabelModel.parent.mkdir(parents=True, exist_ok=True)
        temporaryPath = self.newAutoLabelModel.with_suffix(".pt.new")
        shutil.copy2(bestPath, temporaryPath)
        os.replace(temporaryPath, self.newAutoLabelModel)

        result = {
            "runName": runName,
            "trainingArtifact": str(bestPath.resolve()),
            "bestModel": str(self.newAutoLabelModel.resolve()),
        }
        self.trainingResult.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[TRAIN] 실행 결과: {bestPath}")
        print(f"[TRAIN] 신규 모델 저장: {self.newAutoLabelModel}")


def trainModel(pipeline: TrainModelStage) -> None:
    """오케스트레이터에서 모델 학습 단계를 실행합니다."""
    pipeline.train()