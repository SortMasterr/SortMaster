"""현재 프레임과 직전 프레임을 3채널 시간 정보로 합성하는 유틸리티입니다."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from common.pipelineUtilities import imageExtensions, iterateManifest


class CausalImagesMixin:
    def _getFrameIndex(self) -> dict[tuple[str, int], Path]:
        """프레임 매니페스트를 한 번만 훑어 ``(video, frameIndex)`` 인덱스를 만듭니다.

        실제 이미지가 아닌 경로만 캐시하므로 반복적인 JSONL 탐색 비용은 제거하면서도 하루치
        프레임 전체를 이미지로 메모리에 올리는 문제는 피합니다.
        """
        cachedIndex = getattr(self, "_frameIndexCache", None)
        if cachedIndex is None:
            cachedIndex = {
                (str(row["video"]), int(row["frameIndex"])): Path(row["imagePath"])
                for row in iterateManifest(self.framesManifest)
            }
            self._frameIndexCache = cachedIndex
        return cachedIndex

    def _makeCausalInput(
        self,
        row: dict[str, Any],
        currentImage: np.ndarray | None = None,
    ) -> np.ndarray:
        """이전 2개와 현재 프레임의 grayscale을 B/G/R 채널 위치에 합성합니다.

        호출자가 이미 현재 이미지를 디코딩했다면 ``currentImage``로 전달할 수 있습니다.
        자동 라벨링 단계에서 같은 JPEG를 두 번 읽는 병목을 없애기 위한 인자입니다.
        이전 프레임이 없거나 손상됐으면 현재 프레임으로 대체해 입력 크기를 항상 유지합니다.
        """
        currentPath = Path(row["imagePath"])
        if currentImage is None:
            currentImage = cv2.imread(str(currentPath))
        if currentImage is None:
            raise FileNotFoundError(currentPath)

        frameIndex = self._getFrameIndex()
        frameStep = max(1, int(self.config["frames"]["saveEveryN"]))

        def loadPrevious(offset: int) -> np.ndarray:
            path = frameIndex.get(
                (str(row["video"]), int(row["frameIndex"]) - frameStep * offset),
                currentPath,
            )
            image = cv2.imread(str(path))
            if image is None:
                return currentImage
            if image.shape[:2] != currentImage.shape[:2]:
                image = cv2.resize(
                    image,
                    (currentImage.shape[1], currentImage.shape[0]),
                    interpolation=cv2.INTER_LINEAR,
                )
            return image

        return cv2.merge([
            cv2.cvtColor(loadPrevious(2), cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(loadPrevious(1), cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(currentImage, cv2.COLOR_BGR2GRAY),
        ])

    @staticmethod
    def _makeCausalDatasetImage(imagePath: Path, sourceImages: Path) -> np.ndarray:
        """기존 데이터셋의 파일명 끝 번호를 이용해 이전 두 장을 찾아 합성합니다."""
        currentImage = cv2.imread(str(imagePath))
        if currentImage is None:
            raise FileNotFoundError(imagePath)
        match = re.search(r"(\d+)$", imagePath.stem)
        if match is None:
            olderImage = previousImage = currentImage
        else:
            numberText = match.group(1)
            namePrefix = imagePath.stem[:-len(numberText)]

            def findFrame(offset: int) -> np.ndarray:
                stem = f"{namePrefix}{int(numberText) - offset:0{len(numberText)}d}"
                path = next(
                    (sourceImages / f"{stem}{suffix}" for suffix in imageExtensions
                     if (sourceImages / f"{stem}{suffix}").exists()),
                    None,
                )
                image = None if path is None else cv2.imread(str(path))
                if image is None:
                    return currentImage
                if image.shape[:2] != currentImage.shape[:2]:
                    image = cv2.resize(
                        image,
                        (currentImage.shape[1], currentImage.shape[0]),
                        interpolation=cv2.INTER_LINEAR,
                    )
                return image

            olderImage = findFrame(2)
            previousImage = findFrame(1)
        return cv2.merge([
            cv2.cvtColor(olderImage, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(previousImage, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(currentImage, cv2.COLOR_BGR2GRAY),
        ])