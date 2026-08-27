"""YOLO 자동 라벨링에 필요한 재사용 함수와 단독 실행 CLI를 제공합니다.

기존 자동 라벨링 코드의 핵심 동작인 ``YOLO(...).predict(save_txt=True)``를 유지하면서
Windows 절대 경로와 import 시 즉시 실행되는 코드를 제거했습니다. 파이프라인에서는 단일
이미지 단위 함수들을 사용해 manifest와 causal 입력을 유지하고, 필요하면 이 파일을 직접
실행해 폴더 전체를 빠르게 자동 라벨링할 수도 있습니다.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from collections.abc import Iterator, Sequence
from typing import Any

from common.pipelineUtilities import ManifestWriter, iterateManifest, manifestHasRows

import cv2
import numpy as np


def loadYoloModel(modelPath: str | Path) -> Any:
    """가중치 파일을 확인한 뒤 Ultralytics YOLO 모델을 한 번 로드합니다."""
    resolvedModelPath = Path(modelPath).expanduser().resolve()
    if not resolvedModelPath.is_file():
        raise FileNotFoundError(f"YOLO 모델을 찾을 수 없습니다: {resolvedModelPath}")

    # ultralytics는 이 단계를 실행할 때만 필요하므로 함수 안에서 가져옵니다.
    from ultralytics import YOLO

    return YOLO(str(resolvedModelPath))


def predictImage(
    model: Any,
    imageSource: str | Path | np.ndarray,
    confidence: float = 0.5,
    imageSize: int = 640,
    device: str | int | None = None,
) -> Any:
    """이미지 한 장을 추론하고 첫 번째 Ultralytics Result 객체를 반환합니다.

    ``imageSource``에는 파일 경로뿐 아니라 causal 처리가 끝난 NumPy 이미지도 전달할 수
    있습니다. confidence는 0~1 범위여야 하며, verbose=False로 프레임마다 반복되는 로그를
    줄입니다. 모델은 호출마다 다시 로드하지 않고 상위 단계에서 한 번 만든 객체를 재사용합니다.
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence는 0과 1 사이여야 합니다.")
    if imageSize <= 0:
        raise ValueError("imageSize는 0보다 커야 합니다.")

    resultList = model.predict(
        source=imageSource,
        conf=confidence,
        imgsz=imageSize,
        device=device,
        save=False,
        save_txt=False,
        verbose=False,
    )
    if not resultList:
        raise RuntimeError("YOLO 모델이 추론 결과를 반환하지 않았습니다.")
    return resultList[0]


def extractDetections(
    result: Any,
    allowedClassIds: set[int] | None = None,
    sourceMode: str | None = None,
) -> list[dict[str, Any]]:
    """Result에서 탐지 목록을 뽑아냅니다(파일 저장은 하지 않습니다).

    라벨 파일 작성에 필요한 정규화 좌표(``xywhn``)와 검수 이미지에 필요한 픽셀
    좌표(``xyxy``)를 함께 담아, 여러 입력 모드의 결과를 합친 뒤에도 라벨을 쓸 수
    있게 합니다. ``sourceMode``를 주면 어느 입력이 찾은 박스인지 기록합니다.
    """
    detections: list[dict[str, Any]] = []
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return detections

    for classId, confidence, xywhn, xyxy in zip(
        boxes.cls.tolist(),
        boxes.conf.tolist(),
        boxes.xywhn.tolist(),
        boxes.xyxy.tolist(),
    ):
        classId = int(classId)
        if allowedClassIds is not None and classId not in allowedClassIds:
            continue
        detection = {
            "classId": classId,
            "confidence": float(confidence),
            "xyxy": [float(value) for value in xyxy],
            "xywhn": [float(value) for value in xywhn],
        }
        if sourceMode is not None:
            detection["sourceMode"] = sourceMode
        detections.append(detection)
    return detections


def _boxIou(boxA: Sequence[float], boxB: Sequence[float]) -> float:
    """두 픽셀 좌표 bbox의 IoU를 계산합니다."""
    ax1, ay1, ax2, ay2 = boxA
    bx1, by1, bx2, by2 = boxB
    intersectionWidth = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    intersectionHeight = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = intersectionWidth * intersectionHeight
    areaA = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    areaB = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = areaA + areaB - intersection
    return intersection / union if union > 0 else 0.0


def mergeDetections(
    detectionGroups: Sequence[Sequence[dict[str, Any]]],
    iouThreshold: float = 0.5,
) -> list[dict[str, Any]]:
    """여러 입력 모드의 탐지 목록을 하나로 합칩니다.

    confidence가 높은 박스부터 채택하고, 이미 채택된 박스와 ``iouThreshold``
    이상 겹치면 같은 물체를 두 입력이 각각 잡은 것으로 보고 버립니다. 클래스가
    달라도 같은 위치면 하나만 남기는데, 겹치는 라벨 두 개를 학습 데이터에 넣는
    것보다 더 확신한 쪽 하나만 두는 편이 안전하기 때문입니다.
    """
    if not 0.0 <= iouThreshold <= 1.0:
        raise ValueError("iouThreshold는 0과 1 사이여야 합니다.")

    candidates = [detection for group in detectionGroups for detection in group]
    candidates.sort(key=lambda detection: detection["confidence"], reverse=True)

    merged: list[dict[str, Any]] = []
    for candidate in candidates:
        if any(
            _boxIou(candidate["xyxy"], kept["xyxy"]) >= iouThreshold
            for kept in merged
        ):
            continue
        merged.append(candidate)
    return merged


def writeDetectionsAsYoloLabel(
    labelPath: str | Path,
    detections: Sequence[dict[str, Any]],
) -> None:
    """탐지 목록을 YOLO txt 형식으로 저장합니다.

    각 줄은 ``classId centerX centerY width height``이며 좌표는 0~1로 정규화됩니다.
    탐지가 없더라도 빈 txt를 만들어 이미지와 라벨의 일대일 대응을 유지합니다.
    """
    resolvedLabelPath = Path(labelPath)
    resolvedLabelPath.parent.mkdir(parents=True, exist_ok=True)

    labelLines = [
        f"{int(detection['classId'])} "
        + " ".join(f"{value:.6f}" for value in detection["xywhn"])
        for detection in detections
    ]
    labelText = "\n".join(labelLines) + ("\n" if labelLines else "")
    resolvedLabelPath.write_text(labelText, encoding="utf-8")


def writeYoloLabel(
    labelPath: str | Path,
    result: Any,
    allowedClassIds: set[int] | None = None,
) -> list[dict[str, Any]]:
    """단일 Result의 bbox를 YOLO txt 형식으로 저장하고 탐지 목록을 반환합니다.

    ``allowedClassIds``를 지정하면 기존 모델에 불필요한 클래스가 있어도 학습
    데이터에서 안전하게 제외할 수 있습니다.
    """
    detections = extractDetections(result, allowedClassIds)
    writeDetectionsAsYoloLabel(labelPath, detections)
    return detections


def drawDetections(
    image: np.ndarray,
    detections: Sequence[dict[str, Any]],
    classNames: Sequence[str],
) -> np.ndarray:
    """원본을 변경하지 않고 bbox, 클래스명, 신뢰도를 그린 검수 이미지를 만듭니다."""
    annotatedImage = image.copy()
    for detection in detections:
        classId = int(detection["classId"])
        if not 0 <= classId < len(classNames):
            continue
        x1, y1, x2, y2 = map(int, detection["xyxy"])
        labelText = f"{classNames[classId]} {float(detection['confidence']):.2f}"
        cv2.rectangle(annotatedImage, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            annotatedImage,
            labelText,
            (x1, max(20, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            2,
        )
    return annotatedImage


def autoLabelDirectory(
    modelPath: str | Path,
    imageDirectory: str | Path,
    labelDirectory: str | Path,
    confidence: float = 0.5,
    imageSize: int = 640,
    device: str | int | None = None,
    runName: str = "result",
) -> list[Any]:
    """기존 코드처럼 이미지 폴더 전체를 추론하고 Ultralytics가 txt를 저장하게 합니다.

    이 함수는 독립적인 일괄 라벨링 작업을 위한 호환 진입점입니다. 전체 파이프라인에서는
    프레임별 manifest와 causal 입력을 보존해야 하므로 ``predictImage``와
    ``writeYoloLabel``을 사용합니다.
    """
    resolvedImageDirectory = Path(imageDirectory).expanduser().resolve()
    resolvedLabelDirectory = Path(labelDirectory).expanduser().resolve()
    if not resolvedImageDirectory.is_dir():
        raise FileNotFoundError(f"이미지 폴더를 찾을 수 없습니다: {resolvedImageDirectory}")
    resolvedLabelDirectory.mkdir(parents=True, exist_ok=True)

    model = loadYoloModel(modelPath)
    return model.predict(
        source=str(resolvedImageDirectory),
        conf=confidence,
        imgsz=imageSize,
        device=device,
        save=False,
        save_txt=True,
        project=str(resolvedLabelDirectory),
        name=runName,
        exist_ok=True,
        verbose=False,
    )


def parseArgs() -> argparse.Namespace:
    """단독 폴더 라벨링에 필요한 명령행 인자를 읽습니다."""
    parser = argparse.ArgumentParser(description="YOLO 이미지 폴더 자동 라벨링")
    parser.add_argument("--model", type=Path, required=True, help="YOLO 가중치 파일")
    parser.add_argument("--images", type=Path, required=True, help="입력 이미지 폴더")
    parser.add_argument("--labels", type=Path, required=True, help="라벨 출력 폴더")
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--imageSize", type=int, default=640)
    parser.add_argument("--device", default=None)
    return parser.parse_args()


def main() -> None:
    """이 파일을 직접 실행했을 때 폴더 전체 자동 라벨링을 수행합니다."""
    args = parseArgs()
    results = autoLabelDirectory(
        modelPath=args.model,
        imageDirectory=args.images,
        labelDirectory=args.labels,
        confidence=args.confidence,
        imageSize=args.imageSize,
        device=args.device,
    )
    print(f"자동 라벨링 완료: {sum(1 for _ in results)}개 이미지")


if __name__ == "__main__":
    main()

class AutoLabelingStage:
    """3단계 자동 라벨링의 실제 파이프라인 구현입니다."""

    def label(self) -> None:
        """후보 이미지를 한 장씩 추론하고 즉시 기록합니다."""
        if not manifestHasRows(self.candidatesManifest):
            raise RuntimeError("먼저 select 단계를 실행하세요.")
        baseline = self.pinActiveModel()
        inferenceConfig=self.config["inference"]
        classes=self.config["dataset"]["classes"]
        allowedClassIds=set(range(len(classes)))
        ensembleInputModes=bool(inferenceConfig.get("labelEnsembleInputModes", False))
        ensembleIouThreshold=float(inferenceConfig.get("labelEnsembleIouThreshold", 0.5))
        model=loadYoloModel(baseline.resolvedPath())
        modelNames = getattr(model, "names", None)
        actualClasses = (
            [str(modelNames[index]) for index in sorted(modelNames)]
            if isinstance(modelNames, dict)
            else [str(name) for name in modelNames or []]
        )
        if actualClasses != classes:
            raise RuntimeError(
                "기준 모델 class names가 dataset.classes와 다릅니다. "
                f"model={actualClasses}, config={classes}"
            )
        print(f"[LABEL] 기준 모델 고정: {baseline.version} ({baseline.sha256[:12]})")
        if ensembleInputModes and inferenceConfig["inputMode"]=="causal":
            print(f"[LABEL] 입력 앙상블: causal + rgb (IoU {ensembleIouThreshold} 기준 병합)")
        processedCount=0
        sourceModeCounts: dict[str, int] = {}
        # 후보와 추론 결과를 리스트에 보관하지 않고 이미지별 처리가 끝날 때 즉시 기록한다.
        with ManifestWriter(self.labelsManifest) as writer:
            for row in iterateManifest(self.candidatesManifest):
                rawImage=cv2.imread(row["imagePath"])
                if rawImage is None:
                    continue
                confidence=float(inferenceConfig["confidence"])
                imageSize=int(inferenceConfig["imgsz"])
                device=inferenceConfig.get("device")
                # rawImage를 전달해 causal 합성 시 현재 JPEG를 다시 디코딩하지 않는다.
                causalInput=self._makeCausalInput(row, rawImage) if inferenceConfig["inputMode"]=="causal" else rawImage
                detectionGroups=[
                    extractDetections(
                        predictImage(model,causalInput,confidence,imageSize,device),
                        allowedClassIds,
                        sourceMode=str(inferenceConfig["inputMode"]),
                    )
                ]
                if ensembleInputModes and inferenceConfig["inputMode"]=="causal":
                    # causal 합성과 단일 BGR 원본은 서로 다른 프레임을 잡아내므로
                    # (실측 근거는 pipelineConfig.yaml 주석 참고) 둘 다 추론해 합친다.
                    detectionGroups.append(
                        extractDetections(
                            predictImage(model,rawImage,confidence,imageSize,device),
                            allowedClassIds,
                            sourceMode="rgb",
                        )
                    )
                detections=mergeDetections(detectionGroups,ensembleIouThreshold)
                labelPath=self.autoLabelsRoot/row["video"]/f"{row['id']}.txt"
                writeDetectionsAsYoloLabel(labelPath,detections)
                annotatedImage=drawDetections(rawImage,detections,classes)
                annotatedPath=self.annotatedRoot/row["video"]/f"{row['id']}.jpg"
                annotatedPath.parent.mkdir(parents=True,exist_ok=True)
                if not cv2.imwrite(str(annotatedPath),annotatedImage):
                    raise OSError(f"검수 이미지 저장 실패: {annotatedPath}")
                output=dict(row)
                output.update({"labelPath":str(labelPath.resolve()),"annotatedPath":str(annotatedPath.resolve()),"detections":detections,"teacherModelVersion":baseline.version,"teacherModelSha256":baseline.sha256})
                writer.write(output)
                for detection in detections:
                    mode=detection.get("sourceMode","unknown")
                    sourceModeCounts[mode]=sourceModeCounts.get(mode,0)+1
                processedCount+=1
                if processedCount%100==0:
                    print(f"[LABEL] {processedCount}개 처리")
        del model
        print(f"[LABEL] {processedCount}개 자동 라벨 생성")
        if sourceModeCounts:
            # 앙상블이 실제로 기여했는지(=rgb가 causal이 놓친 박스를 추가했는지)
            # 매 실행마다 눈으로 확인할 수 있게 남긴다.
            print(f"[LABEL] 채택된 박스 출처: {sourceModeCounts}")
def autoLabel(pipeline: AutoLabelingStage) -> None:
    """오케스트레이터에서 자동 라벨링 단계를 실행합니다."""
    pipeline.label()
