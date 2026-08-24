"""자동 학습의 여러 단계가 공유하는 상수와 작은 유틸리티 함수입니다."""

import json
import os
import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

imageExtensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
videoExtensions = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
chinesePattern = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def loadConfig(configPath: Path) -> dict[str, Any]:
    """UTF-8 YAML 설정을 읽고 최상위 구조가 mapping인지 확인합니다."""
    with configPath.open("r", encoding="utf-8") as configFile:
        config = yaml.safe_load(configFile)
    if not isinstance(config, dict):
        raise ValueError("pipelineConfig.yaml의 최상위 값은 mapping이어야 합니다.")
    return config


def resolvePath(projectRoot: Path, pathValue: str | Path) -> Path:
    """상대 경로를 SortMaster 루트 기준 경로로 변환합니다."""
    candidatePath = Path(pathValue)
    return candidatePath if candidatePath.is_absolute() else projectRoot / candidatePath


def readManifest(manifestPath: Path) -> list[dict[str, Any]]:
    """JSONL manifest를 읽으며 파일이 없으면 빈 목록을 반환합니다."""
    if not manifestPath.exists():
        return []
    rows = []
    with manifestPath.open("r", encoding="utf-8") as manifestFile:
        for line in manifestFile:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def writeManifest(manifestPath: Path, rows: list[dict[str, Any]]) -> None:
    """임시 파일을 완성한 뒤 교체하여 JSONL manifest를 안전하게 저장합니다."""
    manifestPath.parent.mkdir(parents=True, exist_ok=True)
    temporaryPath = manifestPath.with_suffix(manifestPath.suffix + ".tmp")
    with temporaryPath.open("w", encoding="utf-8") as manifestFile:
        for row in rows:
            manifestFile.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporaryPath, manifestPath)


def createFrameId(videoStem: str, frameIndex: int) -> str:
    """영상명과 원본 프레임 번호로 이미지와 라벨이 공유할 ID를 만듭니다."""
    return f"{videoStem}__frame_{frameIndex:08d}"


def calculateBlurScore(image: np.ndarray) -> float:
    """Laplacian 분산으로 이미지 선명도를 계산합니다."""
    grayImage = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(grayImage, cv2.CV_64F).var())


def calculateBrightnessScore(image: np.ndarray) -> float:
    """회색조 평균으로 이미지 밝기를 계산합니다."""
    grayImage = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(grayImage.mean())