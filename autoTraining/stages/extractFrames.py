"""1단계: CCTV 영상에서 프레임을 추출합니다."""
import cv2
from common.pipelineUtilities import ManifestWriter,createFrameId,videoExtensions

class ExtractFramesStage:
    def extract(self)->None:
        frameConfig=self.config["frames"]
        saveEvery=max(1,int(frameConfig["saveEveryN"]))
        jpegQuality=int(frameConfig["jpegQuality"])
        videoPaths=sorted(path for path in self.videosDirectory.rglob("*") if path.is_file() and path.suffix.lower() in videoExtensions)
        if not videoPaths:
            raise FileNotFoundError(f"영상이 없습니다: {self.videosDirectory}")
        totalCount=0
        # 추출 결과를 list에 누적하지 않고 프레임 저장 직후 JSONL 한 행을 기록한다.
        with ManifestWriter(self.framesManifest) as writer:
            for videoPath in videoPaths:
                videoKey=videoPath.stem
                outputDirectory=self.framesRoot/videoKey
                outputDirectory.mkdir(parents=True,exist_ok=True)
                capture=cv2.VideoCapture(str(videoPath))
                if not capture.isOpened():
                    print(f"[WARN] 영상 열기 실패: {videoPath}")
                    continue
                sourceFps=float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
                sourceIndex=savedCount=0
                try:
                    while True:
                        succeeded,frameImage=capture.read()
                        if not succeeded:
                            break
                        if sourceIndex%saveEvery:
                            sourceIndex+=1
                            continue
                        itemId=createFrameId(videoKey,sourceIndex)
                        imagePath=outputDirectory/f"{itemId}.jpg"
                        if not cv2.imwrite(str(imagePath),frameImage,[cv2.IMWRITE_JPEG_QUALITY,jpegQuality]):
                            raise OSError(f"프레임 저장 실패: {imagePath}")
                        writer.write({"id":itemId,"video":videoKey,"videoPath":str(videoPath.resolve()),"frameIndex":sourceIndex,"timestampSeconds":sourceIndex/sourceFps if sourceFps>0 else None,"fps":sourceFps,"imagePath":str(imagePath.resolve())})
                        savedCount+=1
                        totalCount+=1
                        sourceIndex+=1
                finally:
                    capture.release()
                print(f"[EXTRACT] {videoPath.name}: {savedCount} frames")
        # 새 frames.jsonl이 생성됐으므로 이전 causal 경로 인덱스를 무효화한다.
        self._frameIndexCache=None
        print(f"[EXTRACT] 전체 {totalCount}개 프레임 보존: {self.framesRoot}")

def extractFrames(pipeline: ExtractFramesStage)->None:
    pipeline.extract()
