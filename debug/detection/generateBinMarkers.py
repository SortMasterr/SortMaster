import argparse
from pathlib import Path

import cv2
import numpy as np


def generateMarkers(outputDirectory: Path, markerSize: int) -> None:
    outputDirectory.mkdir(parents=True, exist_ok=True)
    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_4X4_50
    )

    for markerId in (0, 1, 2):
        markerMargin = max(20, markerSize // 10)
        markerCore = cv2.aruco.generateImageMarker(
            dictionary,
            markerId,
            markerSize,
        )
        markerImage = np.full(
            (
                markerSize + markerMargin * 2,
                markerSize + markerMargin * 2,
            ),
            255,
            dtype=np.uint8,
        )
        markerImage[
            markerMargin:markerMargin + markerSize,
            markerMargin:markerMargin + markerSize,
        ] = markerCore
        outputPath = outputDirectory / f"binMarker{markerId}.png"

        if not cv2.imwrite(str(outputPath), markerImage):
            raise RuntimeError(f"마커 이미지를 저장하지 못했습니다: {outputPath}")

        print(outputPath)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="쓰레기통 3개에 부착할 ArUco 마커(0, 1, 2)를 생성합니다.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("debug/detection/generatedBinMarkers"),
    )
    parser.add_argument(
        "--size",
        type=int,
        default=600,
    )
    arguments = parser.parse_args()

    if arguments.size < 100:
        parser.error("--size는 100 이상이어야 합니다.")

    generateMarkers(arguments.output, arguments.size)


if __name__ == "__main__":
    main()
