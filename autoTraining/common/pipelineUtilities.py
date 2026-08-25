"""파이프라인 전 단계가 공유하는 설정, JSONL, 이미지 I/O 유틸리티입니다."""
from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

imageExtensions = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})
videoExtensions = frozenset({".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"})
chinesePattern = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def loadConfig(configPath: Path) -> dict[str, Any]:
    """UTF-8 YAML 설정을 읽고 최소한의 최상위 구조를 검증합니다."""
    with configPath.open("r", encoding="utf-8") as configFile:
        config = yaml.safe_load(configFile)
    if not isinstance(config, dict):
        raise ValueError("pipelineConfig.yaml 최상위 값은 mapping이어야 합니다.")
    return config


def resolvePath(projectRoot: Path, pathValue: str | Path) -> Path:
    """상대 경로는 프로젝트 루트 기준으로, 절대 경로는 그대로 해석합니다."""
    candidatePath = Path(pathValue).expanduser()
    return candidatePath if candidatePath.is_absolute() else projectRoot / candidatePath


def iterateManifest(manifestPath: Path) -> Iterator[dict[str, Any]]:
    """대규모 JSONL을 메모리에 올리지 않고 검증하며 한 행씩 반환합니다."""
    if not manifestPath.exists():
        return
    with manifestPath.open("r", encoding="utf-8") as manifestFile:
        for lineNumber, line in enumerate(manifestFile, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"잘못된 JSONL: {manifestPath}:{lineNumber}") from error
            if not isinstance(row, dict):
                raise ValueError(f"매니페스트 행은 객체여야 합니다: {manifestPath}:{lineNumber}")
            yield row


def manifestHasRows(manifestPath: Path) -> bool:
    """파일 전체를 읽지 않고 첫 유효 행의 존재만 확인합니다."""
    return next(iterateManifest(manifestPath), None) is not None


class ManifestWriter:
    """JSONL을 스트리밍 기록하고 성공했을 때만 기존 파일을 원자적으로 교체합니다.

    프로세스별 임시 파일을 사용하므로 같은 배치를 잘못 중복 실행해도 고정된 ``.tmp``
    파일을 서로 덮어쓰지 않습니다. flush와 fsync 뒤 교체하여 비정상 종료 시에도 기존의
    완성된 매니페스트가 최대한 보존되도록 합니다.
    """

    def __init__(self, manifestPath: Path):
        self.manifestPath = manifestPath
        token = f"{os.getpid()}-{uuid.uuid4().hex}"
        self.temporaryPath = manifestPath.with_name(f".{manifestPath.name}.{token}.tmp")
        self.manifestFile = None

    def __enter__(self) -> "ManifestWriter":
        self.manifestPath.parent.mkdir(parents=True, exist_ok=True)
        self.manifestFile = self.temporaryPath.open("x", encoding="utf-8", newline="\n")
        return self

    def write(self, row: dict[str, Any]) -> None:
        if self.manifestFile is None:
            raise RuntimeError("ManifestWriter를 with 문 안에서 사용해야 합니다.")
        self.manifestFile.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    def __exit__(self, errorType, error, traceback) -> bool:
        if self.manifestFile is not None:
            if errorType is None:
                self.manifestFile.flush()
                os.fsync(self.manifestFile.fileno())
            self.manifestFile.close()
        if errorType is None:
            os.replace(self.temporaryPath, self.manifestPath)
        else:
            self.temporaryPath.unlink(missing_ok=True)
        return False


def atomicWriteJson(path: Path, value: Any) -> None:
    """완성되지 않은 JSON을 다음 단계가 읽지 않도록 임시 파일 후 교체합니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporaryPath = path.with_name(f".{path.name}.{os.getpid()}-{uuid.uuid4().hex}.tmp")
    try:
        with temporaryPath.open("x", encoding="utf-8", newline="\n") as outputFile:
            json.dump(value, outputFile, ensure_ascii=False, indent=2)
            outputFile.write("\n")
            outputFile.flush()
            os.fsync(outputFile.fileno())
        os.replace(temporaryPath, path)
    finally:
        temporaryPath.unlink(missing_ok=True)


def createFrameId(videoKey: str, frameIndex: int) -> str:
    """영상 키와 원본 프레임 번호로 재실행 가능한 안정적 ID를 만듭니다."""
    return f"{videoKey}__frame_{frameIndex:08d}"


def calculateImageQuality(image: np.ndarray) -> tuple[float, float]:
    """한 번의 grayscale 변환으로 blur 분산과 평균 밝기를 함께 계산합니다."""
    grayImage = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurScore = float(cv2.Laplacian(grayImage, cv2.CV_64F).var())
    brightnessScore = float(grayImage.mean())
    return blurScore, brightnessScore