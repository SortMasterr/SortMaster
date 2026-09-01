"""불변 모델 레지스트리, 활성 모델 포인터와 학습 사이클 고정 기능입니다."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelReference:
    version: str
    path: str
    sha256: str

    def resolvedPath(self) -> Path:
        return Path(self.path)


def calculateFileSha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomicWriteJson(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporaryPath = path.with_suffix(path.suffix + ".tmp")
    temporaryPath.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporaryPath, path)


def _validatedReference(value: dict[str, Any], source: Path) -> ModelReference:
    try:
        reference = ModelReference(
            version=str(value["version"]),
            path=str(Path(value["path"]).resolve()),
            sha256=str(value["sha256"]),
        )
    except (KeyError, TypeError) as error:
        raise ValueError(f"잘못된 모델 포인터입니다: {source}") from error
    modelPath = reference.resolvedPath()
    if not modelPath.is_file():
        raise FileNotFoundError(f"모델 포인터의 파일이 없습니다: {modelPath}")
    actualHash = calculateFileSha256(modelPath)
    if actualHash != reference.sha256:
        raise RuntimeError(f"모델 해시가 포인터와 다릅니다: {modelPath}")
    return reference


def resolveActiveModel(bootstrapModel: Path, activeModelPointer: Path) -> ModelReference:
    """승격 모델이 있으면 사용하고, 없으면 변경 불가 bootstrap 모델을 사용합니다."""
    if activeModelPointer.exists():
        value = json.loads(activeModelPointer.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"활성 모델 포인터는 JSON 객체여야 합니다: {activeModelPointer}")
        return _validatedReference(value, activeModelPointer)
    if not bootstrapModel.is_file():
        raise FileNotFoundError(f"bootstrap 모델이 없습니다: {bootstrapModel}")
    return ModelReference(
        version="bootstrap",
        path=str(bootstrapModel.resolve()),
        sha256=calculateFileSha256(bootstrapModel),
    )


def pinCycleModel(cycleManifest: Path, reference: ModelReference) -> ModelReference:
    """한 학습 사이클이 끝날 때까지 사용할 기준 모델 버전과 해시를 고정합니다."""
    value = asdict(reference)
    value["cycleId"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    value["pinnedAt"] = datetime.now(timezone.utc).isoformat()
    atomicWriteJson(cycleManifest, value)
    return reference


def loadCycleModel(cycleManifest: Path) -> ModelReference:
    if not cycleManifest.exists():
        raise RuntimeError("고정된 학습 사이클 모델이 없습니다. 먼저 label 단계를 실행하세요.")
    value = json.loads(cycleManifest.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"학습 사이클 매니페스트는 JSON 객체여야 합니다: {cycleManifest}")
    return _validatedReference(value, cycleManifest)


def promoteToRegistry(
    candidatePath: Path,
    registryDirectory: Path,
    activeModelPointer: Path,
    source: dict[str, Any],
) -> ModelReference:
    """후보를 불변 버전 파일로 복사한 뒤 활성 포인터를 원자적으로 교체합니다."""
    candidateHash = calculateFileSha256(candidatePath)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version = f"model-{timestamp}-{candidateHash[:12]}"
    registryDirectory.mkdir(parents=True, exist_ok=True)
    registryPath = registryDirectory / f"{version}.pt"
    if registryPath.exists():
        if calculateFileSha256(registryPath) != candidateHash:
            raise RuntimeError(f"같은 버전 이름에 다른 모델이 존재합니다: {registryPath}")
    else:
        temporaryPath = registryPath.with_suffix(".pt.tmp")
        shutil.copy2(candidatePath, temporaryPath)
        if calculateFileSha256(temporaryPath) != candidateHash:
            temporaryPath.unlink(missing_ok=True)
            raise RuntimeError("레지스트리 복사 후 모델 해시 검증에 실패했습니다.")
        os.replace(temporaryPath, registryPath)
    reference = ModelReference(version, str(registryPath.resolve()), candidateHash)
    pointer = asdict(reference)
    pointer.update({"promotedAt": datetime.now(timezone.utc).isoformat(), "source": source})
    atomicWriteJson(activeModelPointer, pointer)
    return reference
