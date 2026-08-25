"""causal 이미지 생성 기능입니다."""
import re
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from common.pipelineUtilities import imageExtensions,iterateManifest

class CausalImagesMixin:
    def _getFrameIndex(self)->dict[tuple[str,int],Path]:
        """프레임 인덱스를 최초 한 번만 생성합니다."""
        cachedIndex=getattr(self,"_frameIndexCache",None)
        # 이미지 자체가 아니라 경로만 캐시하므로 반복 검색 비용은 줄이고 이미지 RAM 점유는 피한다.
        if cachedIndex is None:
            cachedIndex={(str(row["video"]),int(row["frameIndex"])):Path(row["imagePath"]) for row in iterateManifest(self.framesManifest)}
            self._frameIndexCache=cachedIndex
        return cachedIndex

    def _makeCausalInput(self,row: dict[str,Any])->np.ndarray:
        currentPath=Path(row["imagePath"])
        currentImage=cv2.imread(str(currentPath))
        if currentImage is None:
            raise FileNotFoundError(currentPath)
        frameIndex=self._getFrameIndex()
        frameStep=max(1,int(self.config["frames"]["saveEveryN"]))
        def loadPrevious(offset: int)->np.ndarray:
            path=frameIndex.get((str(row["video"]),int(row["frameIndex"])-frameStep*offset),currentPath)
            image=cv2.imread(str(path))
            if image is None:
                return currentImage
            if image.shape[:2]!=currentImage.shape[:2]:
                image=cv2.resize(image,(currentImage.shape[1],currentImage.shape[0]),interpolation=cv2.INTER_LINEAR)
            return image
        return cv2.merge([cv2.cvtColor(loadPrevious(2),cv2.COLOR_BGR2GRAY),cv2.cvtColor(loadPrevious(1),cv2.COLOR_BGR2GRAY),cv2.cvtColor(currentImage,cv2.COLOR_BGR2GRAY)])

    @staticmethod
    def _makeCausalDatasetImage(imagePath: Path,sourceImages: Path)->np.ndarray:
        currentImage=cv2.imread(str(imagePath))
        if currentImage is None:
            raise FileNotFoundError(imagePath)
        match=re.search(r"(\d+)$",imagePath.stem)
        if match is None:
            olderImage=previousImage=currentImage
        else:
            numberText=match.group(1)
            namePrefix=imagePath.stem[:-len(numberText)]
            def findFrame(offset: int)->np.ndarray:
                stem=f"{namePrefix}{int(numberText)-offset:0{len(numberText)}d}"
                path=next((sourceImages/f"{stem}{suffix}" for suffix in imageExtensions if (sourceImages/f"{stem}{suffix}").exists()),None)
                image=None if path is None else cv2.imread(str(path))
                if image is None:
                    return currentImage
                if image.shape[:2]!=currentImage.shape[:2]:
                    image=cv2.resize(image,(currentImage.shape[1],currentImage.shape[0]),interpolation=cv2.INTER_LINEAR)
                return image
            olderImage=findFrame(2)
            previousImage=findFrame(1)
        return cv2.merge([cv2.cvtColor(olderImage,cv2.COLOR_BGR2GRAY),cv2.cvtColor(previousImage,cv2.COLOR_BGR2GRAY),cv2.cvtColor(currentImage,cv2.COLOR_BGR2GRAY)])
