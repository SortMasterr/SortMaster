"""2단계: 추출된 프레임 중 학습 가치가 있는 후보를 선별합니다."""
import shutil
from pathlib import Path

import cv2

from common.pipelineUtilities import (
    ManifestWriter,
    calculateImageQuality,
    iterateManifest,
    manifestHasRows,
)


class SelectFramesStage:
    def select(self) -> None:
        """프레임 간격·선명도·밝기 조건을 통과한 이미지만 후보 폴더로 복사합니다.

        JSONL과 이미지를 한 장씩 처리하여 하루치 프레임 수가 증가해도 RAM 사용량은 거의
        일정합니다. blur와 brightness는 한 번의 grayscale 변환으로 함께 계산합니다.
        """
        if not manifestHasRows(self.framesManifest):
            raise RuntimeError("먼저 extract 단계를 실행하세요.")
        frameConfig = self.config["frames"]
        candidateEvery = max(1, int(frameConfig["candidateEveryN"]))
        minimumBlur = float(frameConfig["minLaplacianVariance"])
        minimumBrightness = float(frameConfig["minBrightness"])
        maximumBrightness = float(frameConfig["maxBrightness"])
        totalCount = selectedCount = 0

        with ManifestWriter(self.candidatesManifest) as writer:
            for sourceRow in iterateManifest(self.framesManifest):
                totalCount += 1
                # 간격 조건을 먼저 검사하면 선택 대상이 아닌 대부분의 프레임을 디코딩하지 않는다.
                if int(sourceRow["frameIndex"]) % candidateEvery:
                    continue
                image = cv2.imread(sourceRow["imagePath"])
                if image is None:
                    print(f"[WARN] 후보 이미지 읽기 실패: {sourceRow['imagePath']}")
                    continue
                blurScore, brightness = calculateImageQuality(image)
                if blurScore < minimumBlur or not minimumBrightness <= brightness <= maximumBrightness:
                    continue

                row = dict(sourceRow)
                row.update({
                    "blurScore": blurScore,
                    "brightness": brightness,
                    "candidate": True,
                    "selectionReasons": ["interval", "sharpness", "brightness"],
                })
                targetPath = self.candidatesRoot / str(row["video"]) / Path(row["imagePath"]).name
                targetPath.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(row["imagePath"], targetPath)
                row["candidatePath"] = str(targetPath.resolve())
                writer.write(row)
                selectedCount += 1
        print(f"[SELECT] 라벨 후보 {selectedCount}/{totalCount}개")


def selectFrames(pipeline: SelectFramesStage) -> None:
    pipeline.select()