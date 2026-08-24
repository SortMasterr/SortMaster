"""SortMaster의 CCTV 기반 YOLO 자동 재학습 파이프라인입니다.

이 파일은 아래 여덟 단계를 순서대로 연결하는 메인 오케스트레이터입니다.

1. extract: CCTV 영상에서 프레임 이미지를 추출합니다.
2. select: 흐림, 밝기, 시간 간격을 기준으로 학습 후보를 고릅니다.
3. label: 현재 운영 중인 YOLO 모델로 후보 이미지에 자동 라벨을 만듭니다.
4. review: Qwen-VL이 자동 라벨을 검수하고 승인, 수동 검수, 거절로 분류합니다.
5. build: 기존 데이터와 승인된 신규 데이터를 하나의 YOLO 데이터셋으로 병합합니다.
6. train: 기존 가중치에서 시작해 후보 모델을 추가 학습합니다.
7. evaluate: 기존 모델과 후보 모델을 동일한 test 데이터로 비교합니다.
8. promote: 정해진 품질 기준을 통과한 후보 모델만 운영 후보 위치로 교체합니다.

각 단계의 결과는 autoTraining/workspace에 이미지와 JSONL manifest로 남습니다.
따라서 한 단계가 실패해도 완료된 앞 단계를 반복하지 않고 실패 지점부터 재실행할 수 있습니다.
경로와 임계값은 코드에 고정하지 않고 pipelineConfig.yaml에서 관리합니다.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from stages.autoLabel import autoLabel
from stages.buildDataset import buildDataset
from stages.evaluateModel import evaluateModel
from stages.extractFrames import extractFrames
from stages.promoteModel import promoteModel
from stages.reviewLabels import reviewLabels
from stages.selectFrames import selectFrames
from stages.trainModel import trainModel

# 처리 순서:
# extract -> select -> label -> review -> build -> train -> evaluate -> promote
# 각 단계는 workspace의 JSONL manifest를 통해 이전 단계 결과를 이어받습니다.
# 단계별 실행이 가능하므로 중간 실패 시 처음부터 다시 시작할 필요가 없습니다.


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).with_name("pipelineConfig.yaml")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
CHINESE_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    if not isinstance(config, dict):
        raise ValueError("config.yaml의 최상위 값은 object여야 합니다.")
    return config


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def jsonl_read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def file_id(video_stem: str, frame_index: int) -> str:
    return f"{video_stem}__frame_{frame_index:08d}"


def blur_score(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def brightness_score(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(gray.mean())


class TrainingPipeline:
    """자동 학습에 필요한 설정, 경로, 단계별 처리 로직을 한곳에서 관리합니다.

    객체를 만들 때 pipelineConfig.yaml을 읽어 입력 영상, 기존 데이터셋, 모델,
    작업 폴더의 실제 경로를 계산합니다. 각 공개 메서드(extract, select 등)는
    CLI에서 독립적으로 실행할 수 있는 하나의 파이프라인 단계를 의미합니다.

    workspace에 저장되는 manifest는 이미지 경로와 처리 결과를 연결하는 작업 장부입니다.
    파일을 단순히 폴더 사이에서 복사하는 것보다 처리 이력을 추적하고 재실행하기 쉽습니다.
    """

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = load_config(config_path)
        # 설정의 paths 값은 SortMaster 루트 기준 상대 경로로 작성할 수 있습니다.
        # 여기서 한 번 절대 경로로 바꾸어 두면 이후 단계가 어느 폴더에서 실행되더라도
        # 동일한 파일을 가리키며, Windows 개발 환경과 Linux 컨테이너 사이의 차이도 줄어듭니다.
        paths = self.config["paths"]
        self.videos_dir = resolve_path(paths["videos"])
        self.workspace = resolve_path(paths["workspace"])
        self.base_dataset = resolve_path(paths["base_dataset"])
        self.base_model = resolve_path(paths["base_model"])
        self.deployed_model = resolve_path(paths["deployed_model"])

        # 아래 폴더는 최종 데이터가 아니라 단계별 작업 결과를 보관하는 공간입니다.
        # 폴더와 함께 JSONL manifest를 유지하여 이미지가 어떤 영상·프레임에서 왔고
        # 어느 단계에서 승인 또는 제외됐는지를 나중에 역추적할 수 있습니다.
        self.frames_root = self.workspace / "frames_all"
        self.candidates_root = self.workspace / "candidates"
        self.auto_labels_root = self.workspace / "auto_labels"
        self.annotated_root = self.workspace / "annotated"
        self.reviews_root = self.workspace / "llm_review"
        self.approved_root = self.workspace / "approved"
        self.manual_root = self.workspace / "manual_review"
        self.rejected_root = self.workspace / "rejected"
        self.dataset_root = self.workspace / "dataset_current"
        self.runs_root = self.workspace / "runs"

        self.frames_manifest = self.workspace / "frames.jsonl"
        self.candidates_manifest = self.workspace / "candidates.jsonl"
        self.labels_manifest = self.workspace / "labels.jsonl"
        self.reviews_manifest = self.workspace / "reviews.jsonl"
        self.training_result = self.workspace / "training_result.json"
        self.evaluation_result = self.workspace / "evaluation.json"

    def extract(self) -> None:
        """CCTV 영상을 프레임 이미지로 분해합니다.

        입력:
            pipelineConfig.yaml의 paths.videos 아래에 있는 지원 영상 파일.
        처리:
            영상을 처음부터 순서대로 읽고 save_every_n 간격의 프레임을 JPG로 저장합니다.
            기본값이 1이면 모든 프레임을 저장합니다.
        출력:
            workspace/frames_all/{영상명}/ 아래의 JPG 이미지와 frames.jsonl.
            manifest에는 원본 영상, 프레임 번호, FPS, 영상 시간, 이미지 경로가 기록됩니다.
        주의:
            이 단계에서는 흐리거나 어두운 프레임도 삭제하지 않습니다. 이후 causal 입력이
            과거 프레임을 참조할 수 있도록 원본 시간 순서를 보존하는 것이 목적입니다.
        """
        frame_config = self.config["frames"]
        save_every = max(1, int(frame_config["save_every_n"]))
        jpeg_quality = int(frame_config["jpeg_quality"])
        videos = sorted(
            path
            for path in self.videos_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        )
        if not videos:
            raise FileNotFoundError(f"영상이 없습니다: {self.videos_dir}")

        rows: list[dict[str, Any]] = []
        for video_path in videos:
            video_key = video_path.stem
            output_dir = self.frames_root / video_key
            output_dir.mkdir(parents=True, exist_ok=True)
            capture = cv2.VideoCapture(str(video_path))
            if not capture.isOpened():
                print(f"[WARN] 영상 열기 실패: {video_path}")
                continue

            source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            source_index = 0
            saved = 0
            try:
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if source_index % save_every != 0:
                        source_index += 1
                        continue

                    item_id = file_id(video_key, source_index)
                    image_path = output_dir / f"{item_id}.jpg"
                    if not cv2.imwrite(
                        str(image_path),
                        frame,
                        [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
                    ):
                        raise OSError(f"프레임 저장 실패: {image_path}")

                    rows.append({
                        "id": item_id,
                        "video": video_key,
                        "video_path": str(video_path.resolve()),
                        "frame_index": source_index,
                        "timestamp_seconds": (
                            source_index / source_fps if source_fps > 0 else None
                        ),
                        "fps": source_fps,
                        "image_path": str(image_path.resolve()),
                    })
                    saved += 1
                    source_index += 1
            finally:
                capture.release()
            print(f"[EXTRACT] {video_path.name}: {saved} frames")

        jsonl_write(self.frames_manifest, rows)
        print(f"[EXTRACT] 전체 {len(rows)}개 프레임 보존: {self.frames_root}")

    def select(self) -> None:
        """추출된 전체 프레임에서 자동 라벨링할 학습 후보를 고릅니다.

        frames.jsonl을 읽고 프레임 간격, Laplacian 분산 기반 선명도, 평균 밝기를 검사합니다.
        조건을 통과한 이미지만 workspace/candidates로 복사하며 candidates.jsonl에 선택 이유와
        측정값을 기록합니다. 탈락한 원본은 frames_all에 그대로 남아 있으므로 복구 가능합니다.
        이 단계는 거의 동일한 연속 프레임을 모두 라벨링하는 비용을 줄이기 위한 과정입니다.
        """
        rows = jsonl_read(self.frames_manifest)
        if not rows:
            raise RuntimeError("먼저 extract 단계를 실행하세요.")

        cfg = self.config["frames"]
        every = max(1, int(cfg["candidate_every_n"]))
        min_blur = float(cfg["min_laplacian_variance"])
        min_brightness = float(cfg["min_brightness"])
        max_brightness = float(cfg["max_brightness"])
        selected: list[dict[str, Any]] = []

        for row in rows:
            image = cv2.imread(row["image_path"])
            if image is None:
                continue
            blur = blur_score(image)
            brightness = brightness_score(image)
            row = dict(row)
            row.update({"blur_score": blur, "brightness": brightness})

            reasons = []
            if row["frame_index"] % every != 0:
                reasons.append("sampling_stride")
            if blur < min_blur:
                reasons.append("too_blurry_for_label_target")
            if not min_brightness <= brightness <= max_brightness:
                reasons.append("brightness_out_of_range")

            row["candidate"] = not reasons
            row["selection_reasons"] = reasons
            if row["candidate"]:
                target = self.candidates_root / row["video"] / Path(row["image_path"]).name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(row["image_path"], target)
                row["candidate_path"] = str(target.resolve())
                selected.append(row)

        jsonl_write(self.candidates_manifest, selected)
        print(f"[SELECT] 라벨 후보 {len(selected)}/{len(rows)}개")
        print("[SELECT] 제외된 흐린 프레임도 frames_all에 시간 문맥으로 남아 있습니다.")

    def _make_causal_input(self, row: dict[str, Any]) -> np.ndarray:
        """한 시점에서 이용 가능한 현재·과거 프레임만으로 causal 입력을 만듭니다.

        t-2, t-1, t 프레임을 각각 회색조로 바꾼 뒤 B/G/R 세 채널처럼 합칩니다.
        미래 프레임을 사용하지 않기 때문에 실제 운영 추론 조건과 학습 조건이 일치합니다.
        앞쪽 프레임이 없거나 읽기에 실패하면 현재 프레임으로 대체하여 크기를 유지합니다.
        """
        current_path = Path(row["image_path"])
        current = cv2.imread(str(current_path))
        if current is None:
            raise FileNotFoundError(current_path)

        all_rows = jsonl_read(self.frames_manifest)
        index = {
            (item["video"], int(item["frame_index"])): Path(item["image_path"])
            for item in all_rows
        }
        step = max(1, int(self.config["frames"]["save_every_n"]))

        def previous_image(offset: int) -> np.ndarray:
            path = index.get(
                (row["video"], int(row["frame_index"]) - step * offset),
                current_path,
            )
            image = cv2.imread(str(path))
            if image is None:
                return current
            if image.shape[:2] != current.shape[:2]:
                image = cv2.resize(
                    image,
                    (current.shape[1], current.shape[0]),
                    interpolation=cv2.INTER_LINEAR,
                )
            return image

        older = previous_image(2)
        previous = previous_image(1)
        return cv2.merge([
            cv2.cvtColor(older, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(current, cv2.COLOR_BGR2GRAY),
        ])

    @staticmethod
    def _make_causal_dataset_image(image_path: Path, source_images: Path) -> np.ndarray:
        """기존 데이터셋 이미지도 학습 입력과 같은 causal 형식으로 변환합니다."""
        current = cv2.imread(str(image_path))
        if current is None:
            raise FileNotFoundError(image_path)
        match = re.search(r"(\d+)$", image_path.stem)
        if match is None:
            older = previous = current
        else:
            number_text = match.group(1)
            width = len(number_text)
            prefix = image_path.stem[: -width]

            def find_frame(offset: int) -> np.ndarray:
                candidate_stem = f"{prefix}{int(number_text) - offset:0{width}d}"
                candidates = [
                    source_images / f"{candidate_stem}{suffix}"
                    for suffix in IMAGE_EXTENSIONS
                ]
                candidate_path = next((path for path in candidates if path.exists()), None)
                if candidate_path is None:
                    return current
                frame = cv2.imread(str(candidate_path))
                if frame is None:
                    return current
                if frame.shape[:2] != current.shape[:2]:
                    frame = cv2.resize(
                        frame,
                        (current.shape[1], current.shape[0]),
                        interpolation=cv2.INTER_LINEAR,
                    )
                return frame

            older = find_frame(2)
            previous = find_frame(1)

        return cv2.merge([
            cv2.cvtColor(older, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(current, cv2.COLOR_BGR2GRAY),
        ])

    @staticmethod
    def _write_yolo_label(path: Path, result, allowed_ids: set[int]) -> list[dict[str, Any]]:
        """Ultralytics 탐지 결과를 표준 YOLO 라벨 파일로 변환합니다.

        각 줄은 classId, 중심 x/y, 너비, 높이를 0~1 정규화 좌표로 저장합니다.
        학습 대상이 아닌 클래스는 allowed_ids로 걸러냅니다. 동시에 Qwen-VL 검수 화면을
        만들 수 있도록 confidence와 픽셀 xyxy 좌표를 Python 사전 목록으로 반환합니다.
        객체가 없으면 빈 txt 파일을 만들어 이미지와 라벨의 대응 관계를 유지합니다.
        """
        detections = []
        lines = []
        if result.boxes is not None:
            for class_id, confidence, xywhn, xyxy in zip(
                result.boxes.cls.tolist(),
                result.boxes.conf.tolist(),
                result.boxes.xywhn.tolist(),
                result.boxes.xyxy.tolist(),
            ):
                class_id = int(class_id)
                if class_id not in allowed_ids:
                    continue
                x, y, width, height = xywhn
                lines.append(
                    f"{class_id} {x:.6f} {y:.6f} {width:.6f} {height:.6f}"
                )
                detections.append({
                    "class_id": class_id,
                    "confidence": float(confidence),
                    "xyxy": [float(value) for value in xyxy],
                })
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return detections

    def label(self) -> None:
        """현재 기준 모델을 이용해 후보 이미지의 초안 라벨을 생성합니다.

        input_mode가 causal이면 시간 채널 이미지를, rgb이면 원본 이미지를 모델에 전달합니다.
        결과는 workspace/auto_labels의 YOLO txt 파일로 저장하고, 사람이 쉽게 확인하도록
        bbox와 클래스·신뢰도를 그린 이미지를 workspace/annotated에 별도로 저장합니다.
        labels.jsonl은 원본 이미지, 라벨, 시각화 이미지, 탐지 결과를 하나의 레코드로 연결합니다.
        이 라벨은 아직 확정 라벨이 아니며 반드시 review 단계를 거쳐야 합니다.
        """
        from ultralytics import YOLO

        rows = jsonl_read(self.candidates_manifest)
        if not rows:
            raise RuntimeError("먼저 select 단계를 실행하세요.")
        if not self.base_model.exists():
            raise FileNotFoundError(f"기존 모델이 없습니다: {self.base_model}")

        cfg = self.config["inference"]
        classes = self.config["dataset"]["classes"]
        allowed_ids = set(range(len(classes)))
        model = YOLO(str(self.base_model))
        output_rows = []

        for number, row in enumerate(rows, 1):
            raw = cv2.imread(row["image_path"])
            if raw is None:
                continue
            if cfg["input_mode"] == "causal":
                model_input = self._make_causal_input(row)
            else:
                model_input = raw

            result = model.predict(
                model_input,
                conf=float(cfg["confidence"]),
                imgsz=int(cfg["imgsz"]),
                device=cfg.get("device"),
                verbose=False,
            )[0]
            label_path = self.auto_labels_root / row["video"] / f"{row['id']}.txt"
            detections = self._write_yolo_label(label_path, result, allowed_ids)

            annotated = raw.copy()
            for detection in detections:
                x1, y1, x2, y2 = map(int, detection["xyxy"])
                name = classes[detection["class_id"]]
                text = f"{name} {detection['confidence']:.2f}"
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    annotated, text, (x1, max(20, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2,
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

        jsonl_write(self.labels_manifest, output_rows)
        print(f"[LABEL] {len(output_rows)}개 자동 라벨 생성")

    def _ollama_request(self, method: str, endpoint: str, payload=None) -> dict[str, Any]:
        """Ollama의 HTTP API를 호출하는 최소 공통 함수입니다.

        base_url과 timeout은 설정에서 읽습니다. 요청 본문이 있으면 UTF-8 JSON으로 직렬화하고,
        네트워크 오류는 어느 서버 연결이 실패했는지 알 수 있는 RuntimeError로 변환합니다.
        모델 선택과 실제 이미지 검수 요청이 동일한 통신 처리를 공유하도록 분리했습니다.
        """
        base_url = self.config["ollama"]["base_url"].rstrip("/")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            base_url + endpoint,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        timeout = float(self.config["ollama"]["timeout_seconds"])
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as error:
            raise RuntimeError(f"Ollama 연결 실패: {base_url} ({error})") from error

    def _resolve_ollama_model(self) -> str:
        """설정된 모델을 사용하거나 설치된 Qwen-VL 모델을 자동으로 선택합니다."""
        configured = str(self.config["ollama"].get("model", "auto"))
        if configured.lower() != "auto":
            return configured
        response = self._ollama_request("GET", "/api/tags")
        names = [str(model.get("name", "")) for model in response.get("models", [])]
        candidates = [name for name in names if "qwen" in name.lower() and "vl" in name.lower()]
        if not candidates:
            raise RuntimeError(
                "Ollama에서 Qwen-VL 모델을 찾지 못했습니다. ollama list 결과의 "
                "비전 모델명을 config.yaml의 ollama.model에 입력하세요. "
                f"설치 모델: {names}"
            )
        print(f"[OLLAMA] 자동 선택 모델: {candidates[0]}")
        return candidates[0]

    def _review_schema(self) -> dict[str, Any]:
        """Qwen-VL이 자유 문장 대신 반환해야 하는 JSON 구조를 정의합니다.

        decision은 approved, manual_review, rejected 중 하나여야 하며, predicted_class와
        issues도 허용 목록 안에서만 선택할 수 있습니다. 구조를 제한하면 자연어 표현 차이로
        자동 처리 로직이 흔들리는 문제를 줄이고 잘못된 응답을 수동 검수로 보낼 수 있습니다.
        """
        classes = self.config["dataset"]["classes"]
        return {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["approved", "rejected", "manual_review"],
                },
                "predicted_class": {
                    "type": "string",
                    "enum": classes + ["none", "multiple"],
                },
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "none", "wrong_class", "missing_object", "extra_box",
                            "bad_bbox", "too_blurry", "too_dark", "multiple_objects",
                        ],
                    },
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["decision", "predicted_class", "issues", "confidence"],
            "additionalProperties": False,
        }

    def _validate_review(self, content: str) -> dict[str, Any]:
        """Qwen-VL 응답을 신뢰하기 전에 형식과 값의 범위를 검증합니다.

        JSON 파싱 가능 여부, 허용된 decision과 class인지, issues 목록이 유효한지,
        confidence가 0~1인지 확인합니다. 예상하지 못한 자연어·문자나 잘못된 값은 예외로
        처리하여 review 단계의 재시도 또는 manual_review 안전 경로로 보내게 합니다.
        """
        if CHINESE_PATTERN.search(content):
            raise ValueError("중국어 문자가 포함됨")
        review = json.loads(content)
        schema = self._review_schema()
        if review.get("decision") not in schema["properties"]["decision"]["enum"]:
            raise ValueError("허용되지 않은 decision")
        if review.get("predicted_class") not in schema["properties"]["predicted_class"]["enum"]:
            raise ValueError("허용되지 않은 class")
        allowed_issues = set(schema["properties"]["issues"]["items"]["enum"])
        if not isinstance(review.get("issues"), list) or not set(review["issues"]) <= allowed_issues:
            raise ValueError("허용되지 않은 issues")
        confidence = float(review.get("confidence", -1))
        if not 0 <= confidence <= 1:
            raise ValueError("confidence 범위 오류")
        review["confidence"] = confidence
        return review

    def _review_one(self, model: str, row: dict[str, Any]) -> dict[str, Any]:
        """한 프레임의 자동 라벨이 학습에 사용 가능한지 Qwen-VL에 질문합니다.

        원본 이미지와 bbox 시각화 이미지를 함께 보내 객체의 실제 모습과 YOLO 예측을 비교하게
        합니다. 모델에는 허용 클래스, 기존 탐지 좌표와 신뢰도, 출력 JSON 스키마를 전달합니다.
        반환값은 후속 단계가 사용할 decision, predicted_class, issues, confidence 정보입니다.
        Qwen-VL은 bbox를 직접 수정하지 않으며 애매한 항목은 사람이 고치도록 분류만 합니다.
        """
        classes = self.config["dataset"]["classes"]
        detections = [
            {
                "class": classes[item["class_id"]],
                "confidence": round(item["confidence"], 4),
                "xyxy": [round(value, 1) for value in item["xyxy"]],
            }
            for item in row["detections"]
        ]
        prompt = (
            "첫 번째 이미지는 원본 CCTV 프레임이고 두 번째 이미지는 YOLO bbox 표시본이다. "
            "쓰레기 클래스와 bbox가 타당한지 검수하라. 쓰레기통은 검수 대상이 아니다. "
            "반드시 제공된 JSON schema만 출력하고 중국어 및 자연어 설명을 출력하지 마라. "
            f"허용 클래스: {classes}. YOLO 결과: {json.dumps(detections)}"
        )
        images = [
            base64.b64encode(Path(row["image_path"]).read_bytes()).decode("ascii"),
            base64.b64encode(Path(row["annotated_path"]).read_bytes()).decode("ascii"),
        ]
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": images}],
            "stream": False,
            "think": False,
            "format": self._review_schema(),
            "options": {"temperature": 0, "seed": SEED if "SEED" in globals() else 42},
        }
        response = self._ollama_request("POST", "/api/chat", payload)
        return self._validate_review(response["message"]["content"])

    def review(self) -> None:
        """labels.jsonl의 자동 라벨을 Qwen-VL로 검수하고 상태별 폴더로 분류합니다.

        approved는 조건을 만족하면 build에 포함될 수 있는 데이터입니다. manual_review는
        클래스나 bbox를 사람이 확인·수정해야 하므로 자동 학습에서 제외됩니다. rejected는
        흐림, 잘못된 객체 등 학습에 부적합한 데이터입니다. API 실패나 잘못된 응답도 무리하게
        승인하지 않고 재시도한 뒤 manual_review로 보내는 보수적인 정책을 사용합니다.
        전체 판단 결과는 reviews.jsonl에 남겨 검수 근거를 추적할 수 있습니다.
        """
        rows = jsonl_read(self.labels_manifest)
        if not rows:
            raise RuntimeError("먼저 label 단계를 실행하세요.")
        model = self._resolve_ollama_model()
        retries = int(self.config["ollama"]["retries"])
        minimum = float(self.config["ollama"]["minimum_review_confidence"])
        outputs = []

        for number, row in enumerate(rows, 1):
            review = None
            errors = []
            for attempt in range(retries + 1):
                try:
                    review = self._review_one(model, row)
                    break
                except (ValueError, RuntimeError, KeyError, json.JSONDecodeError) as error:
                    errors.append(f"attempt {attempt + 1}: {error}")
                    time.sleep(min(2 ** attempt, 5))

            if review is None:
                review = {
                    "decision": "manual_review",
                    "predicted_class": "none",
                    "issues": ["bad_bbox"],
                    "confidence": 0.0,
                }
            if review["confidence"] < minimum:
                review["decision"] = "manual_review"
            if any(issue in {
                "wrong_class", "bad_bbox", "missing_object", "extra_box", "multiple_objects"
            }
                   for issue in review["issues"]):
                review["decision"] = "manual_review"

            output = dict(row)
            output.update({"review": review, "review_errors": errors, "ollama_model": model})
            outputs.append(output)

            queue_root = {
                "approved": self.approved_root,
                "rejected": self.rejected_root,
                "manual_review": self.manual_root,
            }[review["decision"]]
            queue_dir = queue_root / row["video"]
            queue_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(row["image_path"], queue_dir / f"{row['id']}.jpg")
            shutil.copy2(row["annotated_path"], queue_dir / f"{row['id']}__annotated.jpg")
            shutil.copy2(row["label_path"], queue_dir / f"{row['id']}.txt")

            if number % 25 == 0:
                print(f"[REVIEW] {number}/{len(rows)}")

        jsonl_write(self.reviews_manifest, outputs)
        counts = {name: 0 for name in ("approved", "rejected", "manual_review")}
        for row in outputs:
            counts[row["review"]["decision"]] += 1
        print(f"[REVIEW] {counts}")

    @staticmethod
    def _split_for_video(video: str, train_ratio: float, val_ratio: float) -> str:
        """영상 이름의 안정적인 해시로 train, val, test 중 하나를 결정합니다.

        같은 영상의 연속 프레임은 서로 매우 비슷하므로 프레임 단위 무작위 분할을 하면
        test 이미지와 거의 같은 장면이 train에 들어가 평가 점수가 과대 측정될 수 있습니다.
        영상 단위 분할과 결정적 해시를 사용하면 재실행해도 동일한 split이 만들어집니다.
        """
        value = int(hashlib.sha256(video.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
        if value < train_ratio:
            return "train"
        if value < train_ratio + val_ratio:
            return "val"
        return "test"

    def build(self) -> None:
        """기존 데이터셋과 승인된 신규 데이터를 Ultralytics 형식으로 병합합니다.

        train, val, test별 images/labels 구조를 만들고 기존 라벨 중 허용된 클래스만 유지합니다.
        신규 데이터는 원본 영상 단위로 split하여 데이터 누수를 방지합니다. causal 모드에서는
        기존 이미지와 신규 이미지 모두 동일한 시간 채널 입력 형식으로 변환합니다.
        마지막으로 클래스 이름과 각 split 경로가 들어 있는 data.yaml을 생성합니다.
        manual_review와 rejected 데이터는 명시적으로 승인되기 전까지 포함하지 않습니다.
        """
        rows = [
            row for row in jsonl_read(self.reviews_manifest)
            if row["review"]["decision"] == "approved"
        ]
        cfg = self.config["dataset"]
        classes = cfg["classes"]
        if self.dataset_root.exists():
            shutil.rmtree(self.dataset_root)
        for split in ("train", "val", "test"):
            (self.dataset_root / "images" / split).mkdir(parents=True, exist_ok=True)
            (self.dataset_root / "labels" / split).mkdir(parents=True, exist_ok=True)

        # 기존 데이터의 box 라벨은 제거하고 trash ID 0~3만 유지한다.
        for split in ("train", "val", "test"):
            source_images = self.base_dataset / "images" / split
            source_labels = self.base_dataset / "labels" / split
            if not source_images.exists():
                continue
            for image_path in source_images.iterdir():
                if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                target_image = self.dataset_root / "images" / split / image_path.name
                target_label = self.dataset_root / "labels" / split / f"{image_path.stem}.txt"
                if self.config["inference"]["input_mode"] == "causal":
                    causal_image = self._make_causal_dataset_image(image_path, source_images)
                    if not cv2.imwrite(str(target_image), causal_image):
                        raise OSError(f"causal 이미지 저장 실패: {target_image}")
                else:
                    shutil.copy2(image_path, target_image)
                lines = []
                source_label = source_labels / f"{image_path.stem}.txt"
                if source_label.exists():
                    for line in source_label.read_text(encoding="utf-8").splitlines():
                        parts = line.split()
                        if parts and int(parts[0]) < len(classes):
                            lines.append(line)
                target_label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        # 같은 영상이 여러 split에 섞이지 않도록 video 단위로 분리한다.
        for row in rows:
            split = self._split_for_video(
                row["video"], float(cfg["train_ratio"]), float(cfg["val_ratio"])
            )
            name = f"new__{row['id']}"
            target_image = self.dataset_root / "images" / split / f"{name}.jpg"
            target_label = self.dataset_root / "labels" / split / f"{name}.txt"
            # causal 모델이면 학습 입력도 causal 이미지로 저장한다.
            if self.config["inference"]["input_mode"] == "causal":
                image = self._make_causal_input(row)
                cv2.imwrite(str(target_image), image)
            else:
                shutil.copy2(row["image_path"], target_image)
            shutil.copy2(row["label_path"], target_label)

        data_yaml = {
            "path": str(self.dataset_root.resolve()),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "names": {index: name for index, name in enumerate(classes)},
            "nc": len(classes),
        }
        with (self.dataset_root / "data.yaml").open("w", encoding="utf-8") as file:
            yaml.safe_dump(data_yaml, file, allow_unicode=True, sort_keys=False)
        print(f"[BUILD] 승인 신규 데이터 {len(rows)}개 병합: {self.dataset_root}")

    def train(self) -> None:
        """기준 모델을 초기 가중치로 사용하여 후보 YOLO 모델을 추가 학습합니다.

        epochs, image size, batch, GPU device, workers, AMP, patience는 pipelineConfig.yaml에서
        읽습니다. 학습 결과는 실행 시각이 포함된 workspace/runs 하위 폴더에 저장됩니다.
        이후 단계가 정확한 best.pt를 찾을 수 있도록 training_result.json에 절대 경로를 기록합니다.
        이 단계는 운영 모델을 직접 변경하지 않습니다.
        """
        from ultralytics import YOLO

        data_yaml = self.dataset_root / "data.yaml"
        if not data_yaml.exists():
            raise RuntimeError("먼저 build 단계를 실행하세요.")
        cfg = self.config["training"]
        run_name = "auto_finetune_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        model = YOLO(str(self.base_model))
        model.train(
            data=str(data_yaml),
            epochs=int(cfg["epochs"]),
            imgsz=int(cfg["imgsz"]),
            batch=int(cfg["batch"]),
            workers=int(cfg["workers"]),
            device=cfg["device"],
            amp=bool(cfg["amp"]),
            patience=int(cfg["patience"]),
            project=str(self.runs_root),
            name=run_name,
            exist_ok=False,
        )
        best_path = self.runs_root / run_name / "weights" / "best.pt"
        result = {"run_name": run_name, "best_model": str(best_path.resolve())}
        self.training_result.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[TRAIN] 새 모델: {best_path}")

    def _evaluate_model(self, model_path: Path) -> dict[str, float]:
        """지정된 모델을 dataset_current의 고정 test split으로 평가합니다.

        mAP50은 IoU 0.5 기준 평균 정밀도이고, mAP50-95는 여러 IoU 기준을 평균한 더 엄격한
        지표입니다. precision은 오탐 억제 정도, recall은 실제 객체를 놓치지 않는 정도를 나타냅니다.
        기존 모델과 후보 모델이 완전히 같은 조건에서 평가되도록 내부 공통 함수로 사용합니다.
        """
        from ultralytics import YOLO

        cfg = self.config["training"]
        metrics = YOLO(str(model_path)).val(
            data=str(self.dataset_root / "data.yaml"),
            split="test",
            imgsz=int(cfg["imgsz"]),
            device=cfg["device"],
            workers=int(cfg["workers"]),
            verbose=False,
        )
        return {
            "map50": float(metrics.box.map50),
            "map50_95": float(metrics.box.map),
            "precision": float(metrics.box.mp),
            "recall": float(metrics.box.mr),
        }

    def evaluate(self) -> None:
        """기준 모델과 새 후보 모델을 동일한 데이터와 설정으로 평가합니다.

        training_result.json에서 후보 best.pt를 찾고 두 모델의 mAP50, mAP50-95, precision,
        recall을 계산합니다. 비교 결과와 사용한 모델 경로는 evaluation.json에 저장됩니다.
        이 단계 역시 모델을 교체하지 않으며 promote 단계가 판단할 근거만 만듭니다.
        """
        if not self.training_result.exists():
            raise RuntimeError("먼저 train 단계를 실행하세요.")
        training = json.loads(self.training_result.read_text(encoding="utf-8"))
        candidate_model = Path(training["best_model"])
        result = {
            "baseline_model": str(self.base_model.resolve()),
            "candidate_model": str(candidate_model.resolve()),
            "baseline": self._evaluate_model(self.base_model),
            "candidate": self._evaluate_model(candidate_model),
        }
        self.evaluation_result.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    def promote(self) -> None:
        """평가 기준을 통과한 후보 모델을 운영 후보 모델로 승격합니다.

        후보 mAP50과 recall이 설정된 최대 허용 하락폭을 넘지 않는지 먼저 확인합니다.
        실패하면 기존 모델을 전혀 건드리지 않고 예외를 발생시킵니다. 통과하면 현재 모델을
        modelArchive에 시각별로 백업한 뒤 후보 파일을 임시 이름으로 복사하고 os.replace로
        교체합니다. 임시 파일 방식을 사용하여 복사 도중 중단된 불완전 모델이 노출되지 않게 합니다.
        실제 inference 서비스 반영은 별도 배포 연결이 구현된 뒤 이 결과를 사용해야 합니다.
        """
        if not self.evaluation_result.exists():
            raise RuntimeError("먼저 evaluate 단계를 실행하세요.")
        result = json.loads(self.evaluation_result.read_text(encoding="utf-8"))
        cfg = self.config["promotion"]
        baseline = result["baseline"]
        candidate = result["candidate"]
        map_ok = candidate["map50"] >= baseline["map50"] - float(cfg["maximum_map50_drop"])
        recall_ok = candidate["recall"] >= baseline["recall"] - float(cfg["maximum_recall_drop"])
        if not (map_ok and recall_ok):
            raise RuntimeError(
                "품질 게이트 실패로 모델을 교체하지 않습니다. "
                f"baseline={baseline}, candidate={candidate}"
            )

        candidate_path = Path(result["candidate_model"])
        if not candidate_path.exists():
            raise FileNotFoundError(candidate_path)
        backup_root = resolve_path(cfg["backup_directory"])
        backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.deployed_model.exists():
            backup = backup_root / f"{self.deployed_model.stem}_{timestamp}{self.deployed_model.suffix}"
            shutil.copy2(self.deployed_model, backup)
            print(f"[PROMOTE] 기존 모델 백업: {backup}")

        self.deployed_model.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.deployed_model.with_suffix(self.deployed_model.suffix + ".new")
        shutil.copy2(candidate_path, temporary)
        os.replace(temporary, self.deployed_model)
        print(f"[PROMOTE] 배포 모델 교체 완료: {self.deployed_model}")


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["extract", "select", "label", "review", "build", "train", "evaluate", "promote", "all"],
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args()


def main() -> None:
    args = parseArgs()
    pipeline = TrainingPipeline(args.config.resolve())
    # CLI 이름과 단계별 어댑터 함수를 연결합니다. 문자열 getattr 대신 명시적인 표를 사용하면
    # 허용되지 않은 메서드 호출을 막고, 새 단계를 추가할 위치도 한눈에 확인할 수 있습니다.
    stageHandlers = {
        "extract": extractFrames,
        "select": selectFrames,
        "label": autoLabel,
        "review": reviewLabels,
        "build": buildDataset,
        "train": trainModel,
        "evaluate": evaluateModel,
        "promote": promoteModel,
    }
    selectedStages = list(stageHandlers) if args.stage == "all" else [args.stage]
    for stageName in selectedStages:
        print(f"\n===== {stageName.upper()} =====")
        stageHandlers[stageName](pipeline)


if __name__ == "__main__":
    main()
