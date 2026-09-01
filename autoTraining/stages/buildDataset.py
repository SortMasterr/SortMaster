"""MongoDB 배치 스냅샷을 YOLO 학습 데이터셋으로 구성합니다."""
import hashlib
import os
import shutil
import uuid
from pathlib import Path

import yaml

from common.pipelineUtilities import ManifestWriter, iterateManifest, manifestHasRows


class BuildDatasetStage:
    """동기화된 샘플을 영상 그룹 단위로 분리하고 data.yaml을 생성합니다."""

    @staticmethod
    def _splitForVideo(video: str, trainRatio: float, valRatio: float) -> str:
        value = int(hashlib.sha256(video.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
        if value < trainRatio:
            return "train"
        if value < trainRatio + valRatio:
            return "val"
        return "test"

    def build(self) -> None:
        """SyncDataset이 고정한 MongoDB 스냅샷만 사용해 학습 디렉터리를 만듭니다."""
        if not manifestHasRows(self.datasetSnapshotManifest):
            raise RuntimeError("먼저 syncDataset 단계를 실행하세요.")
        cfg = self.config["dataset"]
        trainRatio = float(cfg["trainRatio"])
        valRatio = float(cfg["valRatio"])
        testRatio = float(cfg["testRatio"])
        if any(not 0 <= ratio <= 1 for ratio in (trainRatio, valRatio, testRatio)):
            raise ValueError("dataset split 비율은 0~1 범위여야 합니다.")
        if abs(trainRatio + valRatio + testRatio - 1.0) > 1e-9:
            raise ValueError("dataset trainRatio+valRatio+testRatio 합은 1이어야 합니다.")
        goldenImages = self.goldenTest / "images"
        goldenLabels = self.goldenTest / "labels"
        if not goldenImages.is_dir() or not goldenLabels.is_dir():
            raise RuntimeError(f"고정 Golden Test가 없습니다: {goldenImages}, {goldenLabels}")

        temporaryRoot = self.datasetRoot.with_name(
            f".{self.datasetRoot.name}.{os.getpid()}-{uuid.uuid4().hex}.tmp"
        )
        counts = {"train": 0, "val": 0, "test": 0}
        try:
            for split in counts:
                (temporaryRoot / "images" / split).mkdir(parents=True, exist_ok=True)
                (temporaryRoot / "labels" / split).mkdir(parents=True, exist_ok=True)
            with ManifestWriter(temporaryRoot / "samples.jsonl") as writer:
                for row in iterateManifest(self.datasetSnapshotManifest):
                    split = self._splitForVideo(str(row["sourceGroup"]), trainRatio, valRatio)
                    imagePath = Path(row["imagePath"])
                    labelPath = Path(row["labelPath"])
                    if not imagePath.is_file() or not labelPath.is_file():
                        raise FileNotFoundError(f"스냅샷 파일이 없습니다: {imagePath}, {labelPath}")
                    targetImage = temporaryRoot / "images" / split / imagePath.name
                    targetLabel = temporaryRoot / "labels" / split / f"{imagePath.stem}.txt"
                    shutil.copy2(imagePath, targetImage)
                    shutil.copy2(labelPath, targetLabel)
                    output = dict(row)
                    output.update({"split": split, "imagePath": str(targetImage.resolve()), "labelPath": str(targetLabel.resolve())})
                    writer.write(output)
                    counts[split] += 1
            if counts["train"] == 0 or counts["val"] == 0:
                raise RuntimeError(f"train/val split에 최소 1개 샘플이 필요합니다: {counts}")
            dataYaml = {
                "path": str(self.datasetRoot.resolve()), "train": "images/train",
                "val": "images/val", "test": str(goldenImages.resolve()),
                "names": {index: name for index, name in enumerate(cfg["classes"])},
                "nc": len(cfg["classes"]),
            }
            with (temporaryRoot / "data.yaml").open("w", encoding="utf-8") as file:
                yaml.safe_dump(dataYaml, file, allow_unicode=True, sort_keys=False)
            backupRoot = self.datasetRoot.with_name(f".{self.datasetRoot.name}.previous")
            if backupRoot.exists():
                shutil.rmtree(backupRoot)
            if self.datasetRoot.exists():
                os.replace(self.datasetRoot, backupRoot)
            try:
                os.replace(temporaryRoot, self.datasetRoot)
            except Exception:
                if backupRoot.exists() and not self.datasetRoot.exists():
                    os.replace(backupRoot, self.datasetRoot)
                raise
            if backupRoot.exists():
                shutil.rmtree(backupRoot)
        finally:
            if temporaryRoot.exists():
                shutil.rmtree(temporaryRoot)
        print(f"[BUILD] MongoDB 배치 스냅샷 구성: {counts} -> {self.datasetRoot}")
        print(f"[BUILD] 고정 Golden Test: {self.goldenTest}")


def buildDataset(pipeline: BuildDatasetStage) -> None:
    pipeline.build()