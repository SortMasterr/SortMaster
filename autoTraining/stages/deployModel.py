"""승격 모델을 tracking2.py가 사용하는 bestTop.pt 이름으로 배포·롤백합니다."""
import json
import os
import shutil
from pathlib import Path

from common.modelRegistry import calculateFileSha256, resolveActiveModel
from common.pipelineUtilities import resolvePath


class DeployModelStage:
    """승격과 운영 반영을 분리하고 복사 전후 해시를 검증합니다."""

    def deploy(self) -> None:
        active = resolveActiveModel(self.bootstrapModel, self.activeModelPointer)
        target = resolvePath(self.projectRoot, self.config["deployment"]["targetModel"])
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        shutil.copy2(active.resolvedPath(), temporary)
        if calculateFileSha256(temporary) != active.sha256:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("운영 모델 복사 후 해시 검증에 실패했습니다.")
        os.replace(temporary, target)
        deployment = {
            "version": active.version,
            "path": str(target.resolve()),
            "sha256": active.sha256,
            "restartRequired": True,
        }
        self.deploymentResult.write_text(json.dumps(deployment, indent=2), encoding="utf-8")
        print(f"[DEPLOY] {active.version} -> {target}")
        print("[DEPLOY] tracking2.py 재시작과 smoke test가 필요합니다.")

    def rollback(self, version: str) -> None:
        source = self.modelRegistry / f"{version}.pt"
        if not source.is_file():
            raise FileNotFoundError(f"롤백 모델이 없습니다: {source}")
        target = resolvePath(self.projectRoot, self.config["deployment"]["targetModel"])
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".rollback")
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
        print(f"[ROLLBACK] {version} -> {target}")
        print("[ROLLBACK] tracking2.py 재시작과 smoke test가 필요합니다.")


def deployModel(pipeline: DeployModelStage) -> None:
    pipeline.deploy()
