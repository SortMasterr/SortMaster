"""파이프라인 공통 설정, JSONL, 이미지 유틸리티입니다."""
from __future__ import annotations
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
import cv2
import numpy as np
import yaml

imageExtensions={".jpg",".jpeg",".png",".bmp",".webp"}
videoExtensions={".mp4",".avi",".mov",".mkv",".webm",".m4v"}
chinesePattern=re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

def loadConfig(configPath: Path)->dict[str,Any]:
    with configPath.open("r",encoding="utf-8") as configFile:
        config=yaml.safe_load(configFile)
    if not isinstance(config,dict):
        raise ValueError("pipelineConfig.yaml 최상위 값은 mapping이어야 합니다.")
    return config

def resolvePath(projectRoot: Path,pathValue: str|Path)->Path:
    candidatePath=Path(pathValue)
    return candidatePath if candidatePath.is_absolute() else projectRoot/candidatePath

def iterateManifest(manifestPath: Path)->Iterator[dict[str,Any]]:
    # 대규모 JSONL 전체를 list로 만들지 않아 프레임 수가 늘어도 메모리 사용을 일정하게 유지한다.
    """JSONL을 메모리에 모두 올리지 않고 한 행씩 반환합니다."""
    if not manifestPath.exists():
        return
    with manifestPath.open("r",encoding="utf-8") as manifestFile:
        for lineNumber,line in enumerate(manifestFile,1):
            if not line.strip():
                continue
            try:
                row=json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"잘못된 JSONL: {manifestPath}:{lineNumber}") from error
            if not isinstance(row,dict):
                raise ValueError(f"매니페스트 행은 객체여야 합니다: {manifestPath}:{lineNumber}")
            yield row

def manifestHasRows(manifestPath: Path)->bool:
    return next(iterateManifest(manifestPath),None) is not None

# 처리 도중 실패했을 때 기존 정상 매니페스트가 손상되지 않도록 임시 파일을 사용한다.
class ManifestWriter:
    """한 행씩 임시 파일에 쓰고 성공할 때만 기존 매니페스트를 교체합니다."""
    def __init__(self,manifestPath: Path):
        self.manifestPath=manifestPath
        self.temporaryPath=manifestPath.with_suffix(manifestPath.suffix+".tmp")
        self.manifestFile=None
    def __enter__(self)->"ManifestWriter":
        self.manifestPath.parent.mkdir(parents=True,exist_ok=True)
        self.manifestFile=self.temporaryPath.open("w",encoding="utf-8")
        return self
    def write(self,row: dict[str,Any])->None:
        if self.manifestFile is None:
            raise RuntimeError("ManifestWriter를 with 문 안에서 사용해야 합니다.")
        self.manifestFile.write(json.dumps(row,ensure_ascii=False)+"\n")
    def __exit__(self,errorType,error,traceback)->bool:
        if self.manifestFile is not None:
            self.manifestFile.close()
        if errorType is None:
            os.replace(self.temporaryPath,self.manifestPath)
        else:
            self.temporaryPath.unlink(missing_ok=True)
        return False

def createFrameId(videoStem: str,frameIndex: int)->str:
    return f"{videoStem}__frame_{frameIndex:08d}"

def calculateBlurScore(image: np.ndarray)->float:
    grayImage=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(grayImage,cv2.CV_64F).var())

def calculateBrightnessScore(image: np.ndarray)->float:
    grayImage=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    return float(grayImage.mean())
