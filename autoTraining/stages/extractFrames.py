"""1단계: CCTV 영상에서 프레임과 frames manifest를 생성합니다."""

import cv2

from common.pipelineUtilities import createFrameId, videoExtensions, writeManifest


class ExtractFramesStage:
    """프레임 추출 단계의 실제 구현입니다."""

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
            if path.is_file() and path.suffix.lower() in videoExtensions
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

                    item_id = createFrameId(video_key, source_index)
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

        writeManifest(self.frames_manifest, rows)
        print(f"[EXTRACT] 전체 {len(rows)}개 프레임 보존: {self.frames_root}")


def extractFrames(pipeline: ExtractFramesStage) -> None:
    """오케스트레이터에서 프레임 추출 단계를 실행합니다."""
    pipeline.extract()