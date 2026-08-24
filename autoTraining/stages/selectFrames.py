"""2단계: 자동 라벨링 후보 프레임을 선별합니다."""
import shutil
from pathlib import Path
import cv2
from common.pipelineUtilities import ManifestWriter,calculateBlurScore,calculateBrightnessScore,iterateManifest,manifestHasRows

class SelectFramesStage:
    def select(self)->None:
        if not manifestHasRows(self.frames_manifest):
            raise RuntimeError("먼저 extract 단계를 실행하세요.")
        frameConfig=self.config["frames"]
        candidateEvery=max(1,int(frameConfig["candidate_every_n"]))
        minimumBlur=float(frameConfig["min_laplacian_variance"])
        minimumBrightness=float(frameConfig["min_brightness"])
        maximumBrightness=float(frameConfig["max_brightness"])
        totalCount=selectedCount=0
        # 한 번에 이미지 한 장만 읽고 판정하여 전체 프레임 배열이 RAM에 쌓이지 않게 한다.
        with ManifestWriter(self.candidates_manifest) as writer:
            for sourceRow in iterateManifest(self.frames_manifest):
                totalCount+=1
                image=cv2.imread(sourceRow["image_path"])
                if image is None:
                    continue
                blurScore=calculateBlurScore(image)
                brightness=calculateBrightnessScore(image)
                if int(sourceRow["frame_index"])%candidateEvery or blurScore<minimumBlur or not minimumBrightness<=brightness<=maximumBrightness:
                    continue
                row=dict(sourceRow)
                row.update({"blur_score":blurScore,"brightness":brightness,"candidate":True,"selection_reasons":[]})
                targetPath=self.candidates_root/str(row["video"])/Path(row["image_path"]).name
                targetPath.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(row["image_path"],targetPath)
                row["candidate_path"]=str(targetPath.resolve())
                writer.write(row)
                selectedCount+=1
        print(f"[SELECT] 라벨 후보 {selectedCount}/{totalCount}개")

def selectFrames(pipeline: SelectFramesStage)->None:
    pipeline.select()
