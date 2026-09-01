"""8단계: 검증된 후보를 불변 레지스트리에 등록하고 활성 포인터를 교체합니다."""
import json
import math
from pathlib import Path

from common.modelRegistry import calculateFileSha256, promoteToRegistry, resolveActiveModel


class PromoteModelStage:
    def promote(self) -> None:
        if not self.evaluationResult.exists():
            raise RuntimeError("먼저 evaluate 단계를 실행하세요.")
        result = json.loads(self.evaluationResult.read_text(encoding="utf-8"))
        cfg = self.config["promotion"]
        baseline = result["baseline"]
        candidate = result["candidate"]
        metricValues = [baseline["map50"], baseline["recall"], candidate["map50"], candidate["recall"]]
        if not all(math.isfinite(float(value)) for value in metricValues):
            raise RuntimeError("평가 지표에 NaN 또는 무한대가 있어 모델을 승격하지 않습니다.")
        minimumMap50Gain = float(cfg["minimumMap50Gain"])
        minimumRecallGain = float(cfg["minimumRecallGain"])
        if candidate["map50"] < baseline["map50"] + minimumMap50Gain:
            raise RuntimeError("mAP50이 최소 향상 기준을 통과하지 못해 모델을 승격하지 않습니다.")
        if candidate["recall"] < baseline["recall"] + minimumRecallGain:
            raise RuntimeError("recall이 최소 향상 기준을 통과하지 못해 모델을 승격하지 않습니다.")

        active = resolveActiveModel(self.bootstrapModel, self.activeModelPointer)
        if active.sha256 != result["baselineSha256"]:
            raise RuntimeError("평가 후 활성 기준 모델이 변경되어 승격을 중단합니다.")
        candidatePath = Path(result["candidateModel"])
        if calculateFileSha256(candidatePath) != result["candidateSha256"]:
            raise RuntimeError("평가 후 후보 모델 파일이 변경되어 승격을 중단합니다.")
        reference = promoteToRegistry(
            candidatePath, self.modelRegistry, self.activeModelPointer,
            {"runName": result["runName"], "baselineVersion": result["baselineVersion"]},
        )
        print(f"[PROMOTE] 활성 모델: {reference.version} ({reference.path})")


def promoteModel(pipeline: PromoteModelStage) -> None:
    pipeline.promote()
