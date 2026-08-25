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


def writeYoloLabel(
    labelPath: str | Path,
    result: Any,
    allowedClassIds: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Result의 bbox를 YOLO txt 형식으로 저장하고 검수용 탐지 목록을 반환합니다.

    YOLO txt의 각 줄은 ``classId centerX centerY width height``이며 좌표는 0~1로
    정규화됩니다. 탐지가 없더라도 빈 txt를 만들어 이미지와 라벨의 일대일 대응을 유지합니다.
    ``allowedClassIds``를 지정하면 기존 모델에 불필요한 클래스가 있어도 학습 데이터에서
    안전하게 제외할 수 있습니다.
    """
    resolvedLabelPath = Path(labelPath)
    resolvedLabelPath.parent.mkdir(parents=True, exist_ok=True)

    labelLines: list[str] = []
    detections: list[dict[str, Any]] = []
    boxes = getattr(result, "boxes", None)
    if boxes is not None:
        for classId, confidence, xywhn, xyxy in zip(
            boxes.cls.tolist(),
            boxes.conf.tolist(),
            boxes.xywhn.tolist(),
            boxes.xyxy.tolist(),
        ):
            classId = int(classId)
            if allowedClassIds is not None and classId not in allowedClassIds:
                continue
            centerX, centerY, width, height = xywhn
            labelLines.append(
                f"{classId} {centerX:.6f} {centerY:.6f} {width:.6f} {height:.6f}"
            )
            detections.append({
                "classId": classId,
                "confidence": float(confidence),
                "xyxy": [float(value) for value in xyxy],
            })

    labelText = "\n".join(labelLines) + ("\n" if labelLines else "")
    resolvedLabelPath.write_text(labelText, encoding="utf-8")
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
        processedCount=0
        # 후보와 추론 결과를 리스트에 보관하지 않고 이미지별 처리가 끝날 때 즉시 기록한다.
        with ManifestWriter(self.labelsManifest) as writer:
            for row in iterateManifest(self.candidatesManifest):
                rawImage=cv2.imread(row["imagePath"])
                if rawImage is None:
                    continue
                # rawImage를 전달해 causal 합성 시 현재 JPEG를 다시 디코딩하지 않는다.
                modelInput=self._makeCausalInput(row, rawImage) if inferenceConfig["inputMode"]=="causal" else rawImage
                result=predictImage(model,modelInput,float(inferenceConfig["confidence"]),int(inferenceConfig["imgsz"]),inferenceConfig.get("device"))
                labelPath=self.autoLabelsRoot/row["video"]/f"{row['id']}.txt"
                detections=writeYoloLabel(labelPath,result,allowedClassIds)
                annotatedImage=drawDetections(rawImage,detections,classes)
                annotatedPath=self.annotatedRoot/row["video"]/f"{row['id']}.jpg"
                annotatedPath.parent.mkdir(parents=True,exist_ok=True)
                if not cv2.imwrite(str(annotatedPath),annotatedImage):
                    raise OSError(f"검수 이미지 저장 실패: {annotatedPath}")
                output=dict(row)
                output.update({"labelPath":str(labelPath.resolve()),"annotatedPath":str(annotatedPath.resolve()),"detections":detections,"teacherModelVersion":baseline.version,"teacherModelSha256":baseline.sha256})
                writer.write(output)
                processedCount+=1
                if processedCount%100==0:
                    print(f"[LABEL] {processedCount}개 처리")
        del model
        print(f"[LABEL] {processedCount}개 자동 라벨 생성")
def autoLabel(pipeline: AutoLabelingStage) -> None:
    """오케스트레이터에서 자동 라벨링 단계를 실행합니다."""
    pipeline.label()
