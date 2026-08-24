"""
배경 차분 기반 사람 존재(전경 비율) 계산.

YOLO 없이 가벼운 방식으로 "사람이 있냐 없냐"만 판단하기 위한 순수 알고리즘 —
architecture.md의 "탐지 파이프라인" 참고. 모션(움직임) 감지는 투척 시작 순간을
놓칠 수 있어 이미 기각됐고(decisionLog.md), 이 클래스는 그 대신 프레임마다
전경 픽셀 비율만 계산한다 — 임계값 비교/디바운스 등 상태 판단은
services/presenceGateService.py가 담당한다.

카메라 1대당 인스턴스 1개(MOG2 배경 모델이 프레임 순서에 의존하는 상태를 가지므로,
호출 순서를 보장하는 단일 폴링 루프에서만 사용해야 함).
"""
import cv2
import numpy as np


class PersonPresenceDetector:
    def __init__(
        self,
        history: int = 500,
        varThreshold: float = 16.0,
        detectShadows: bool = True,
    ):
        self._backgroundSubtractor = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=varThreshold,
            detectShadows=detectShadows,
        )

    def foregroundRatio(self, frame: np.ndarray) -> float:
        mask = self._backgroundSubtractor.apply(frame)
        # MOG2가 detectShadows=True일 때 그림자는 127로 표시함 — 진짜 전경(255)만
        # 카운트해서 사람 그림자로 비율이 부풀지 않게 한다.
        foregroundPixelCount = int(np.count_nonzero(mask == 255))
        totalPixelCount = mask.shape[0] * mask.shape[1]

        if totalPixelCount == 0:
            return 0.0

        return foregroundPixelCount / totalPixelCount
