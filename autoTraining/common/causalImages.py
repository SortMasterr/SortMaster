"""Label과 Build 단계가 함께 사용하는 causal 이미지 처리입니다."""

import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from common.pipelineUtilities import imageExtensions, readManifest


class CausalImagesMixin:
    """현재 프레임과 과거 프레임을 시간 채널 이미지로 만드는 공통 기능입니다."""

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

        all_rows = readManifest(self.frames_manifest)
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
                    for suffix in imageExtensions
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