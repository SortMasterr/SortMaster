"""8단계: 품질 기준을 통과한 후보 모델을 안전하게 승격합니다."""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from common.pipelineUtilities import resolvePath


class PromoteModelStage:
    """품질 게이트, 기존 모델 백업, 원자적 파일 교체를 담당합니다."""

    def promote(self) -> None:
        """평가 기준을 통과한 후보 모델을 운영 후보 모델로 승격합니다.

        후보 mAP50과 recall이 설정된 최대 허용 하락폭을 넘지 않는지 먼저 확인합니다.
        실패하면 기존 모델을 전혀 건드리지 않고 예외를 발생시킵니다. 통과하면 현재 모델을
        modelArchive에 시각별로 백업한 뒤 후보 파일을 임시 이름으로 복사하고 os.replace로
        교체합니다. 임시 파일 방식을 사용하여 복사 도중 중단된 불완전 모델이 노출되지 않게 합니다.
        실제 inference 서비스 반영은 별도 배포 연결이 구현된 뒤 이 결과를 사용해야 합니다.
        """
        if not self.evaluation_result.exists():
            raise RuntimeError("먼저 evaluate 단계를 실행하세요.")
        result = json.loads(self.evaluation_result.read_text(encoding="utf-8"))
        cfg = self.config["promotion"]
        baseline = result["baseline"]
        candidate = result["candidate"]
        map_ok = candidate["map50"] >= baseline["map50"] - float(cfg["maximum_map50_drop"])
        recall_ok = candidate["recall"] >= baseline["recall"] - float(cfg["maximum_recall_drop"])
        if not (map_ok and recall_ok):
            raise RuntimeError(
                "품질 게이트 실패로 모델을 교체하지 않습니다. "
                f"baseline={baseline}, candidate={candidate}"
            )

        candidate_path = Path(result["candidate_model"])
        if not candidate_path.exists():
            raise FileNotFoundError(candidate_path)
        backup_root = resolvePath(self.projectRoot, cfg["backup_directory"])
        backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.deployed_model.exists():
            backup = backup_root / f"{self.deployed_model.stem}_{timestamp}{self.deployed_model.suffix}"
            shutil.copy2(self.deployed_model, backup)
            print(f"[PROMOTE] 기존 모델 백업: {backup}")

        self.deployed_model.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.deployed_model.with_suffix(self.deployed_model.suffix + ".new")
        shutil.copy2(candidate_path, temporary)
        os.replace(temporary, self.deployed_model)
        print(f"[PROMOTE] 배포 모델 교체 완료: {self.deployed_model}")


def promoteModel(pipeline: PromoteModelStage) -> None:
    """오케스트레이터에서 모델 승격 단계를 실행합니다."""
    pipeline.promote()