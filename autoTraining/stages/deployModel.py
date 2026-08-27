"""승격 모델을 tracking2.py가 사용하는 bestTop.pt 이름으로 배포·롤백합니다."""
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from common.modelRegistry import calculateFileSha256, resolveActiveModel
from common.pipelineUtilities import atomicWriteJson, resolvePath
from stages.autoLabeling import loadYoloModel, predictImage


class DeployModelStage:
    """승격과 운영 반영을 분리하고 복사 전후 해시를 검증합니다."""

    def _smokeTestModel(self, modelPath: Path, device=None) -> dict:
        deploymentConfig = self.config["deployment"]
        imageSize = int(
            deploymentConfig.get("smokeImageSize", self.config["inference"]["imgsz"])
        )
        if imageSize <= 0:
            raise ValueError("smokeImageSize는 0보다 커야 합니다.")
        smokeDevice = (
            device
            if device is not None
            else deploymentConfig.get("smokeDevice", "cpu")
        )
        expectedNames = {
            index: name
            for index, name in enumerate(self.config["dataset"]["classes"])
        }
        model = loadYoloModel(modelPath)
        actualNames = {
            int(index): str(name)
            for index, name in dict(model.names).items()
        }
        if actualNames != expectedNames:
            raise RuntimeError(
                "운영 모델 클래스 계약 불일치: "
                f"expected={expectedNames}, actual={actualNames}"
            )

        smokeImage = np.zeros((imageSize, imageSize, 3), dtype=np.uint8)
        result = predictImage(
            model,
            smokeImage,
            confidence=float(self.config["inference"]["confidence"]),
            imageSize=imageSize,
            device=smokeDevice,
        )
        boxes = getattr(result, "boxes", None)
        detectionCount = len(boxes) if boxes is not None else 0
        return {
            "passed": True,
            "modelSha256": calculateFileSha256(modelPath),
            "classNames": actualNames,
            "imageSize": imageSize,
            "device": smokeDevice,
            "detectionCount": detectionCount,
        }

    def smokeTest(self, device=None) -> dict:
        target = resolvePath(self.projectRoot, self.config["deployment"]["targetModel"])
        if not target.is_file():
            raise FileNotFoundError(f"운영 모델이 없습니다: {target}")
        result = self._smokeTestModel(target, device=device)
        result.update({
            "path": str(target.resolve()),
            "testedAt": datetime.now(timezone.utc).isoformat(),
        })
        atomicWriteJson(self.smokeTestResult, result)
        print(f"[SMOKE TEST] passed: {target}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    def deploy(self) -> None:
        active = resolveActiveModel(self.bootstrapModel, self.activeModelPointer)
        target = resolvePath(self.projectRoot, self.config["deployment"]["targetModel"])
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.stem}.deploy-{os.getpid()}{target.suffix}")
        shutil.copy2(active.resolvedPath(), temporary)
        if calculateFileSha256(temporary) != active.sha256:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("운영 모델 복사 후 해시 검증에 실패했습니다.")
        try:
            smokeTest = self._smokeTestModel(temporary)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        os.replace(temporary, target)
        deployment = {
            "version": active.version,
            "path": str(target.resolve()),
            "sha256": active.sha256,
            "restartRequired": True,
            "smokeTest": smokeTest,
        }
        atomicWriteJson(self.deploymentResult, deployment)
        print(f"[DEPLOY] {active.version} -> {target}")
        print("[DEPLOY] 모델 smoke test 통과. tracking2.py 재시작이 필요합니다.")

    def rollback(self, version: str) -> None:
        source = self.modelRegistry / f"{version}.pt"
        if not source.is_file():
            raise FileNotFoundError(f"롤백 모델이 없습니다: {source}")
        target = resolvePath(self.projectRoot, self.config["deployment"]["targetModel"])
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.stem}.rollback-{os.getpid()}{target.suffix}")
        shutil.copy2(source, temporary)
        try:
            self._smokeTestModel(temporary)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        os.replace(temporary, target)
        print(f"[ROLLBACK] {version} -> {target}")
        print("[ROLLBACK] 모델 smoke test 통과. tracking2.py 재시작이 필요합니다.")


def deployModel(pipeline: DeployModelStage) -> None:
    pipeline.deploy()
