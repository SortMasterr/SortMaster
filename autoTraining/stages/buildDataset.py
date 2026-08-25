"""5단계: 기존 데이터와 승인 데이터를 YOLO 데이터셋으로 병합합니다."""

import hashlib
import shutil

import cv2
import yaml

from common.pipelineUtilities import imageExtensions, iterateManifest


class BuildDatasetStage:
    """데이터 복사, 영상 단위 split, data.yaml 생성을 담당합니다."""

    @staticmethod
    def _splitForVideo(video: str, trainRatio: float, valRatio: float) -> str:
        """영상 이름의 안정적인 해시로 train, val, test 중 하나를 결정합니다.

        같은 영상의 연속 프레임은 서로 매우 비슷하므로 프레임 단위 무작위 분할을 하면
        test 이미지와 거의 같은 장면이 train에 들어가 평가 점수가 과대 측정될 수 있습니다.
        영상 단위 분할과 결정적 해시를 사용하면 재실행해도 동일한 split이 만들어집니다.
        """
        value = int(hashlib.sha256(video.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
        if value < trainRatio:
            return "train"
        if value < trainRatio + valRatio:
            return "val"
        return "test"

    def build(self) -> None:
        """기존 데이터셋과 승인된 신규 데이터를 Ultralytics 형식으로 병합합니다.

        train, val, test별 images/labels 구조를 만들고 기존 라벨 중 허용된 클래스만 유지합니다.
        신규 데이터는 원본 영상 단위로 split하여 데이터 누수를 방지합니다. causal 모드에서는
        기존 이미지와 신규 이미지 모두 동일한 시간 채널 입력 형식으로 변환합니다.
        마지막으로 클래스 이름과 각 split 경로가 들어 있는 data.yaml을 생성합니다.
        Qwen 판정과 관계없이 사람의 최종 approved 데이터만 포함합니다.
        """
        # Qwen 판정은 보조 정보일 뿐이다. 사람 최종 승인 매니페스트만 학습 데이터에 포함한다.
        if not self.humanReviewsManifest.exists():
            raise RuntimeError("먼저 humanReview 단계를 완료하세요.")
        hasApprovedRows = any(
            row["humanReview"]["decision"] == "approved"
            for row in iterateManifest(self.humanReviewsManifest)
        )
        if not hasApprovedRows:
            raise RuntimeError("사람이 승인한 신규 학습 데이터가 없어 Build를 중단합니다.")
        approvedRows = (
            row for row in iterateManifest(self.humanReviewsManifest)
            if row["humanReview"]["decision"] == "approved"
        )
        approvedCount = 0
        cfg = self.config["dataset"]
        classes = cfg["classes"]
        if self.datasetRoot.exists():
            shutil.rmtree(self.datasetRoot)
        for split in ("train", "val", "test"):
            (self.datasetRoot / "images" / split).mkdir(parents=True, exist_ok=True)
            (self.datasetRoot / "labels" / split).mkdir(parents=True, exist_ok=True)

        # 기존 데이터의 box 라벨은 제거하고 trash ID 0~3만 유지한다.
        for split in ("train", "val", "test"):
            sourceImages = self.baseDataset / "images" / split
            sourceLabels = self.baseDataset / "labels" / split
            if not sourceImages.exists():
                continue
            for imagePath in sourceImages.iterdir():
                if imagePath.suffix.lower() not in imageExtensions:
                    continue
                targetImage = self.datasetRoot / "images" / split / imagePath.name
                targetLabel = self.datasetRoot / "labels" / split / f"{imagePath.stem}.txt"
                if self.config["inference"]["inputMode"] == "causal":
                    causalImage = self._makeCausalDatasetImage(imagePath, sourceImages)
                    if not cv2.imwrite(str(targetImage), causalImage):
                        raise OSError(f"causal 이미지 저장 실패: {targetImage}")
                else:
                    shutil.copy2(imagePath, targetImage)
                lines = []
                sourceLabel = sourceLabels / f"{imagePath.stem}.txt"
                if sourceLabel.exists():
                    for line in sourceLabel.read_text(encoding="utf-8").splitlines():
                        parts = line.split()
                        if parts and int(parts[0]) < len(classes):
                            lines.append(line)
                targetLabel.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        # 같은 영상이 여러 split에 섞이지 않도록 video 단위로 분리한다.
        for row in approvedRows:
            approvedCount += 1
            split = self._splitForVideo(
                row["video"], float(cfg["trainRatio"]), float(cfg["valRatio"])
            )
            name = f"new-{row['id']}"
            targetImage = self.datasetRoot / "images" / split / f"{name}.jpg"
            targetLabel = self.datasetRoot / "labels" / split / f"{name}.txt"
            # causal 모델이면 학습 입력도 causal 이미지로 저장한다.
            if self.config["inference"]["inputMode"] == "causal":
                image = self._makeCausalInput(row)
                cv2.imwrite(str(targetImage), image)
            else:
                shutil.copy2(row["imagePath"], targetImage)
            shutil.copy2(row["labelPath"], targetLabel)

        goldenImages = self.goldenTest / "images"
        goldenLabels = self.goldenTest / "labels"
        if not goldenImages.is_dir() or not goldenLabels.is_dir():
            raise RuntimeError(
                "고정 Golden Test가 없습니다. "
                f"{goldenImages}와 {goldenLabels}를 준비하세요."
            )

        dataYaml = {
            "path": str(self.datasetRoot.resolve()),
            "train": "images/train",
            "val": "images/val",
            # 기존/신규 모델의 일일 비교 기준이 흔들리지 않도록 고정 평가셋을 사용한다.
            "test": str(goldenImages.resolve()),
            "names": {index: name for index, name in enumerate(classes)},
            "nc": len(classes),
        }
        with (self.datasetRoot / "data.yaml").open("w", encoding="utf-8") as file:
            yaml.safe_dump(dataYaml, file, allow_unicode=True, sort_keys=False)
        print(f"[BUILD] 사람 승인 신규 데이터 {approvedCount}개 병합: {self.datasetRoot}")
        print(f"[BUILD] 고정 Golden Test: {self.goldenTest}")


def buildDataset(pipeline: BuildDatasetStage) -> None:
    """오케스트레이터에서 데이터셋 빌드 단계를 실행합니다."""
    pipeline.build()
