"""2단계: 추출 프레임에서 자동 라벨링 후보를 선별합니다."""

from pathlib import Path
import shutil

import cv2

from common.pipelineUtilities import calculateBlurScore, calculateBrightnessScore, readManifest, writeManifest


class SelectFramesStage:
    """프레임 품질과 샘플링 기준을 적용하는 실제 구현입니다."""

    def select(self) -> None:
        """추출된 전체 프레임에서 자동 라벨링할 학습 후보를 고릅니다.

        frames.jsonl을 읽고 프레임 간격, Laplacian 분산 기반 선명도, 평균 밝기를 검사합니다.
        조건을 통과한 이미지만 workspace/candidates로 복사하며 candidates.jsonl에 선택 이유와
        측정값을 기록합니다. 탈락한 원본은 frames_all에 그대로 남아 있으므로 복구 가능합니다.
        이 단계는 거의 동일한 연속 프레임을 모두 라벨링하는 비용을 줄이기 위한 과정입니다.
        """
        rows = readManifest(self.frames_manifest)
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
            blur = calculateBlurScore(image)
            brightness = calculateBrightnessScore(image)
            row = dict(row)
            row.update({"calculateBlurScore": blur, "brightness": brightness})

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

        writeManifest(self.candidates_manifest, selected)
        print(f"[SELECT] 라벨 후보 {len(selected)}/{len(rows)}개")
        print("[SELECT] 제외된 흐린 프레임도 frames_all에 시간 문맥으로 남아 있습니다.")


def selectFrames(pipeline: SelectFramesStage) -> None:
    """오케스트레이터에서 후보 선별 단계를 실행합니다."""
    pipeline.select()