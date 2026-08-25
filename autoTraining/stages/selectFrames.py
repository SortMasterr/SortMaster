"""2단계: 자동 라벨링 후보 프레임을 선별합니다."""
import shutil
from pathlib import Path
import cv2
from common.pipelineUtilities import ManifestWriter,calculateBlurScore,calculateBrightnessScore,iterateManifest,manifestHasRows

class SelectFramesStage:
    def select(self)->None:
        if not manifestHasRows(self.framesManifest):
            raise RuntimeError("먼저 extract 단계를 실행하세요.")
        frameConfig=self.config["frames"]
        candidateEvery=max(1,int(frameConfig["candidateEveryN"]))
        minimumBlur=float(frameConfig["minLaplacianVariance"])
        minimumBrightness=float(frameConfig["minBrightness"])
        maximumBrightness=float(frameConfig["maxBrightness"])
        totalCount=selectedCount=0
        # 한 번에 이미지 한 장만 읽고 판정하여 전체 프레임 배열이 RAM에 쌓이지 않게 한다.
        with ManifestWriter(self.candidatesManifest) as writer:
            for sourceRow in iterateManifest(self.framesManifest):
                totalCount+=1
                image=cv2.imread(sourceRow["imagePath"])
                if image is None:
                    continue
                blurScore=calculateBlurScore(image)
                brightness=calculateBrightnessScore(image)
                if int(sourceRow["frameIndex"])%candidateEvery or blurScore<minimumBlur or not minimumBrightness<=brightness<=maximumBrightness:
                    continue
                row=dict(sourceRow)
                row.update({"blurScore":blurScore,"brightness":brightness,"candidate":True,"selectionReasons":[]})
                targetPath=self.candidatesRoot/str(row["video"])/Path(row["imagePath"]).name
                targetPath.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(row["imagePath"],targetPath)
                row["candidatePath"]=str(targetPath.resolve())
                writer.write(row)
                selectedCount+=1
        print(f"[SELECT] 라벨 후보 {selectedCount}/{totalCount}개")

def selectFrames(pipeline: SelectFramesStage)->None:
    pipeline.select()
