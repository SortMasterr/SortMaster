"""YOLO 자동 라벨링에 필요한 재사용 함수와 단독 실행 CLI를 제공합니다.

기존 auto_labeling.py의 핵심 동작인 ``YOLO(...).predict(save_txt=True)``를 유지하면서
Windows 절대 경로와 import 시 즉시 실행되는 코드를 제거했습니다. 파이프라인에서는 단일
이미지 단위 함수들을 사용해 manifest와 causal 입력을 유지하고, 필요하면 이 파일을 직접
실행해 폴더 전체를 빠르게 자동 라벨링할 수도 있습니다.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

from common.pipelineUtilities import readManifest, writeManifest

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
                "class_id": classId,
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
        classId = int(detection["class_id"])
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
    print(f"자동 라벨링 완료: {len(results)}개 이미지")


if __name__ == "__main__":
    main()

class AutoLabelingStage:
    """3단계 자동 라벨링의 실제 파이프라인 구현입니다."""

    def label(self) -> None:
        """현재 기준 모델을 이용해 후보 이미지의 초안 라벨을 생성합니다.

        input_mode가 causal이면 시간 채널 이미지를, rgb이면 원본 이미지를 모델에 전달합니다.
        결과는 workspace/auto_labels의 YOLO txt 파일로 저장하고, 사람이 쉽게 확인하도록
        bbox와 클래스·신뢰도를 그린 이미지를 workspace/annotated에 별도로 저장합니다.
        labels.jsonl은 원본 이미지, 라벨, 시각화 이미지, 탐지 결과를 하나의 레코드로 연결합니다.
        이 라벨은 아직 확정 라벨이 아니며 반드시 review 단계를 거쳐야 합니다.
        """
        rows = readManifest(self.candidates_manifest)
        if not rows:
            raise RuntimeError("먼저 select 단계를 실행하세요.")
        if not self.base_model.exists():
            raise FileNotFoundError(f"기존 모델이 없습니다: {self.base_model}")

        cfg = self.config["inference"]
        classes = self.config["dataset"]["classes"]
        allowed_ids = set(range(len(classes)))
        model = loadYoloModel(self.base_model)
        output_rows = []

        for number, row in enumerate(rows, 1):
            raw = cv2.imread(row["image_path"])
            if raw is None:
                continue
            if cfg["input_mode"] == "causal":
                model_input = self._make_causal_input(row)
            else:
                model_input = raw

            result = predictImage(
                model=model,
                imageSource=model_input,
                confidence=float(cfg["confidence"]),
                imageSize=int(cfg["imgsz"]),
                device=cfg.get("device"),
            )
            label_path = self.auto_labels_root / row["video"] / f"{row['id']}.txt"
            detections = writeYoloLabel(
                labelPath=label_path,
                result=result,
                allowedClassIds=allowed_ids,
            )

            annotated = drawDetections(
                image=raw,
                detections=detections,
                classNames=classes,
            )
            annotated_path = self.annotated_root / row["video"] / f"{row['id']}.jpg"
            annotated_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(annotated_path), annotated)

            output = dict(row)
            output.update({
                "label_path": str(label_path.resolve()),
                "annotated_path": str(annotated_path.resolve()),
                "detections": detections,
            })
            output_rows.append(output)
            if number % 100 == 0:
                print(f"[LABEL] {number}/{len(rows)}")

        writeManifest(self.labels_manifest, output_rows)
        print(f"[LABEL] {len(output_rows)}개 자동 라벨 생성")


def autoLabel(pipeline: AutoLabelingStage) -> None:
    """오케스트레이터에서 자동 라벨링 단계를 실행합니다."""
    pipeline.label()