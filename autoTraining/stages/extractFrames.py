"""1단계: 하루치 CCTV 영상에서 일정 간격으로 프레임을 추출합니다."""
import hashlib
import re
from pathlib import Path

import cv2

from common.pipelineUtilities import (
    ManifestWriter,
    createFrameId,
    iterateManifest,
    manifestHasRows,
    videoExtensions,
)


class ExtractFramesStage:
    def _createVideoKey(self, videoPath: Path) -> str:
        """입력 루트 기준 경로로 충돌하지 않는 짧고 재현 가능한 영상 키를 만듭니다.

        서로 다른 카메라 폴더에 ``record.mp4``가 동시에 있어도 기존 stem 방식처럼 출력 폴더와
        프레임 ID가 섞이지 않습니다. 사람이 로그를 읽기 쉽도록 stem을 남기고 상대 경로 해시를
        덧붙입니다.
        """
        relativeName = videoPath.relative_to(self.videosDirectory).as_posix()
        safeStem = re.sub(r"[^A-Za-z0-9._-]+", "-", videoPath.stem).strip("-.") or "video"
        shortHash = hashlib.sha256(relativeName.encode("utf-8")).hexdigest()[:10]
        return f"{safeStem}-{shortHash}"

    def extract(self) -> None:
        """지원 영상들을 순회하며 JPG와 ``frames.jsonl``을 스트리밍 생성합니다."""
        frameConfig = self.config["frames"]
        saveEvery = max(1, int(frameConfig["saveEveryN"]))
        jpegQuality = int(frameConfig["jpegQuality"])
        if not 1 <= jpegQuality <= 100:
            raise ValueError("frames.jpegQuality는 1~100이어야 합니다.")

        if self.config["eventStore"].get("source", "gridFs") == "gridFs":
            if not manifestHasRows(self.collectedMediaManifest):
                raise RuntimeError("먼저 collect 단계를 실행하세요.")
            # GridFS 모드에서는 수집 매니페스트만 신뢰한다. 이전 재실행의 고아 파일이나
            # 사용자가 수동으로 넣은 파일이 같은 학습 배치에 섞이는 것을 방지한다.
            videoPaths = sorted(
                Path(row["mediaPath"])
                for row in iterateManifest(self.collectedMediaManifest)
            )
        else:
            videoPaths = sorted(
                path for path in self.videosDirectory.rglob("*")
                if path.is_file() and path.suffix.lower() in videoExtensions
            )
        if not videoPaths:
            raise FileNotFoundError(f"영상이 없습니다: {self.videosDirectory}")

        totalCount = openedVideoCount = 0
        # 프레임 저장 직후 한 행을 기록하므로 영상 전체의 메타데이터를 RAM에 누적하지 않는다.
        with ManifestWriter(self.framesManifest) as writer:
            for videoPath in videoPaths:
                videoKey = self._createVideoKey(videoPath)
                outputDirectory = self.framesRoot / videoKey
                outputDirectory.mkdir(parents=True, exist_ok=True)
                capture = cv2.VideoCapture(str(videoPath))
                if not capture.isOpened():
                    print(f"[WARN] 영상 열기 실패: {videoPath}")
                    continue

                openedVideoCount += 1
                sourceFps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
                sourceIndex = savedCount = 0
                try:
                    while True:
                        succeeded, frameImage = capture.read()
                        if not succeeded:
                            break
                        if sourceIndex % saveEvery == 0:
                            itemId = createFrameId(videoKey, sourceIndex)
                            imagePath = outputDirectory / f"{itemId}.jpg"
                            if not cv2.imwrite(
                                str(imagePath), frameImage,
                                [cv2.IMWRITE_JPEG_QUALITY, jpegQuality],
                            ):
                                raise OSError(f"프레임 저장 실패: {imagePath}")
                            writer.write({
                                "id": itemId,
                                "video": videoKey,
                                "videoPath": str(videoPath.resolve()),
                                "frameIndex": sourceIndex,
                                "timestampSeconds": sourceIndex / sourceFps if sourceFps > 0 else None,
                                "fps": sourceFps,
                                "imagePath": str(imagePath.resolve()),
                            })
                            savedCount += 1
                            totalCount += 1
                        sourceIndex += 1
                finally:
                    capture.release()
                print(f"[EXTRACT] {videoPath.name}: {savedCount} frames")

        if openedVideoCount == 0 or totalCount == 0:
            raise RuntimeError("열 수 있는 영상 또는 저장된 프레임이 없어 Extract를 완료할 수 없습니다.")
        # 새 매니페스트가 만들어졌으므로 causal 경로 인덱스를 다음 사용 시 다시 생성한다.
        self._frameIndexCache = None
        print(f"[EXTRACT] 전체 {totalCount}개 프레임 보존: {self.framesRoot}")


def extractFrames(pipeline: ExtractFramesStage) -> None:
    pipeline.extract()