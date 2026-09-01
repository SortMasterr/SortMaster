import os

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import cv2
import json
import uuid
from pathlib import Path
from datetime import datetime
from ultralytics import YOLO


# ============================================================
# 1. 기본 설정
# ============================================================
MODEL_PATH = r"C:\final_project\model_result\trash_yolo26n_aug2\trash_yolo26n_aug2-2\weights\best.pt"
SOURCE = r"C:\final_project\video\위영상4.mp4"      # 시연 영상 / 웹캠 사용 시 SOURCE = 0
# SOURCE = 0
CAMERA_ID = "CAM-01"

# CPU 실시간 처리 프로필. 10 FPS 카메라보다 처리 속도를 높여 프레임이
# 대기열에 쌓이지 않게 한다.
REALTIME_MODE = True
INFERENCE_IMAGE_SIZE = 416
TRACKER_CONFIG = r"C:\final_project\code\botsort_mvp.yaml"
SAVE_OUTPUT_VIDEO = True

# Used only when SOURCE is a camera index such as 0. Exposure values depend
# on the camera driver; lower values commonly mean a shorter exposure.
CAMERA_MANUAL_EXPOSURE = True
CAMERA_EXPOSURE = -6.0
CAMERA_GAIN = 0.0

# Enhance only the image passed to YOLO. Output video and event crops keep the
# original pixels. Turn this off to make a quick A/B comparison.
ENABLE_DETECTION_ENHANCEMENT = False
CLAHE_CLIP_LIMIT = 2.0
BLUR_VARIANCE_THRESHOLD = 80.0
UNSHARP_SIGMA = 1.0
UNSHARP_AMOUNT = 0.45

# Tracking 중 낮은 confidence 탐지도 활용
# Keep this low enough for BoT-SORT to reuse weak detections from blurred
# frames. NEW_TRASH_CONFIDENCE below still prevents weak detections from
# creating brand-new event tracks.
CONFIDENCE = 0.05

# 새로운 쓰레기 Track을 우리 이벤트 시스템에 등록하는 최소 confidence
NEW_TRASH_CONFIDENCE = 0.45

# 쓰레기통 bbox 전체를 투입 영역으로 사용
MIN_INSIDE_FRAMES = 2
EXIT_RESET_FRAMES = 3

# 이벤트로 인정하기 위한 최소 관찰 조건
# 시연용: 통 밖에서 먼저 잡혀야 한다는 조건은 사용하지 않음
# YOLO가 늦게 잡아 처음 탐지 시 이미 쓰레기통 bbox 안일 수 있기 때문
MIN_TRACK_VISIBLE_FRAMES = 5

# At 10 FPS a fast object can be undetectable for a few motion-blurred frames.
# Extrapolate only an already reliable track across this short detection gap.
BLUR_GAP_BRIDGE_FRAMES = 3
MOTION_HISTORY_SIZE = 4
MIN_MOTION_PIXELS_PER_FRAME = 2.0
BIN_ENTRY_MARGIN_RATIO = 0.06

# 실제 FPS 기준 시간 설정
DISAPPEAR_CONFIRM_SECONDS = 0.5   # 약 0.5초 미탐지 시 투입 확정
TRACK_EXPIRE_SECONDS = 4.0        # 아무 통에도 안 들어간 Track 정리

# Track이 끊긴 직후 같은 통에서 새 ID로 다시 생성되는 경우를 중복으로 보기 위한 시간
# 서로 동시에 존재한 Track은 중복으로 보지 않으므로 동시 투입은 각각 인정한다.
# 아주 빠르게 같은 통에 순차 투입하는 테스트라면 값을 줄이거나 0으로 설정할 수 있다.
FRAGMENT_DUPLICATE_GAP_SECONDS = 1.5

# 이벤트 이미지 crop 여백
CROP_MARGIN_RATIO = 0.15

# 고정 카메라 쓰레기통 ROI (x1, y1, x2, y2), 각 값은 화면 비율 0~1.
# 기존 640x480 영상에서 사용하던 통 위치를 비율로 변환한 기본값이다.
# 카메라 구도가 바뀌면 이 값만 수정하면 된다.
RULE_BASED_BIN_ROIS = {
    # 왼쪽 위 원형 커피컵 통의 투입구
    "box_coffeecup": (0.000, 0.155, 0.160, 0.345),

    # 아래쪽 세 통의 전면 투입구만 지정
    "box_recyclables": (0.105, 0.500, 0.315, 0.830),
    "box_paper": (0.430, 0.500, 0.630, 0.860),
    "box_normal": (0.755, 0.500, 0.960, 0.860),
}

# 원형/타원형 투입구는 bbox의 네 모서리를 진입 영역에서 제외한다.
ELLIPTICAL_BIN_ROIS = {"box_coffeecup"}

# 결과 영상 저장
OUTPUT_VIDEO_PATH = r"C:\Users\Woori\Videos\Trackingresult2.mp4"
OUTPUT_FPS_FALLBACK = 20.0

# 이벤트 저장
SAVE_DIR = Path("waste_events")
EVENT_LOG_FILE = SAVE_DIR / "events.jsonl"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

# Hard examples for later labeling/retraining. Images are saved without drawn
# boxes so they can be imported directly into a labeling tool.
HARD_EXAMPLE_DIR = Path("image")
SAVE_HARD_EXAMPLES = False
MAX_HARD_EXAMPLE_IMAGES = 1000
RUN_SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
HARD_EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. 클래스 / 분리배출 규칙
# ============================================================
EXPECTED_CLASS_NAMES = {
    0: "TrashNormal",
    1: "TrashPaper",
    2: "TrashRecyclables",
    3: "TrashCoffeecup",
}

TRASH_CLASS_IDS = [0, 1, 2, 3]

TRASH_CLASSES = {
    "TrashNormal",
    "TrashPaper",
    "TrashRecyclables",
    "TrashCoffeecup",
}

TRASH_TYPE_MAP = {
    "TrashNormal": "normal",
    "TrashPaper": "paper",
    "TrashRecyclables": "recyclables",
    "TrashCoffeecup": "coffeecup",
}

BIN_TYPE_MAP = {
    "box_normal": "normal",
    "box_paper": "paper",
    "box_recyclables": "recyclables",
    "box_coffeecup": "coffeecup",
}

# 커피컵은 커피컵 통 또는 재활용 통 모두 정상
VALID_BIN_MAP = {
    "normal": {"normal"},
    "paper": {"paper"},
    "recyclables": {"recyclables"},
    "coffeecup": {"coffeecup", "recyclables"},
}


# ============================================================
# 3. 모델 / 영상 초기화
# ============================================================
model = YOLO(MODEL_PATH)
print("모델 클래스:", model.names)

for class_id, expected_name in EXPECTED_CLASS_NAMES.items():
    actual_name = model.names.get(class_id)
    if actual_name != expected_name:
        print(
            f"[WARNING] class {class_id}: "
            f"expected={expected_name}, actual={actual_name}"
        )

cap = cv2.VideoCapture(SOURCE)
if not cap.isOpened():
    raise RuntimeError("카메라 또는 영상 파일을 열 수 없습니다.")

if isinstance(SOURCE, int):
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if CAMERA_MANUAL_EXPOSURE:
        # 0.25 selects manual exposure on common Windows DirectShow cameras.
        auto_ok = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        exposure_ok = cap.set(cv2.CAP_PROP_EXPOSURE, CAMERA_EXPOSURE)
        gain_ok = cap.set(cv2.CAP_PROP_GAIN, CAMERA_GAIN)

        print(
            "[CAMERA] manual exposure request: "
            f"auto={auto_ok}, exposure={exposure_ok}, gain={gain_ok}"
        )
        print(
            "[CAMERA] reported values: "
            f"auto={cap.get(cv2.CAP_PROP_AUTO_EXPOSURE):.2f}, "
            f"exposure={cap.get(cv2.CAP_PROP_EXPOSURE):.2f}, "
            f"gain={cap.get(cv2.CAP_PROP_GAIN):.2f}"
        )

frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
source_fps = float(cap.get(cv2.CAP_PROP_FPS))
output_fps = source_fps if source_fps > 1.0 else OUTPUT_FPS_FALLBACK

DISAPPEAR_CONFIRM_FRAMES = max(
    1,
    int(round(output_fps * DISAPPEAR_CONFIRM_SECONDS)),
)

TRACK_EXPIRE_FRAMES = max(
    DISAPPEAR_CONFIRM_FRAMES + 1,
    int(round(output_fps * TRACK_EXPIRE_SECONDS)),
)

FRAGMENT_DUPLICATE_GAP_FRAMES = max(
    0,
    int(round(output_fps * FRAGMENT_DUPLICATE_GAP_SECONDS)),
)

print(f"입력/저장 FPS: {output_fps:.2f}")
print(
    f"투입 확정 대기: {DISAPPEAR_CONFIRM_FRAMES} frames "
    f"(~{DISAPPEAR_CONFIRM_SECONDS:.1f}s)"
)
print(
    f"Track 만료: {TRACK_EXPIRE_FRAMES} frames "
    f"(~{TRACK_EXPIRE_SECONDS:.1f}s)"
)
print(
    f"Track fragment 중복 간격: {FRAGMENT_DUPLICATE_GAP_FRAMES} frames "
    f"(~{FRAGMENT_DUPLICATE_GAP_SECONDS:.1f}s)"
)

video_writer = None

if SAVE_OUTPUT_VIDEO:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    video_writer = cv2.VideoWriter(
        OUTPUT_VIDEO_PATH,
        fourcc,
        output_fps,
        (frame_width, frame_height),
    )

    if not video_writer.isOpened():
        raise RuntimeError("결과 영상 저장 파일을 열 수 없습니다.")

    print(
        f"결과 영상 저장 시작: {OUTPUT_VIDEO_PATH} "
        f"({frame_width}x{frame_height}, {output_fps:.2f} FPS)"
    )
else:
    print("[REALTIME] 결과 영상 인코딩 비활성화")


# ============================================================
# 4. 런타임 상태
# ============================================================
# 쓰레기통은 모델이 탐지하지 않고 고정된 화면 비율 ROI를 사용한다.
def normalized_roi_to_bbox(roi):
    x1, y1, x2, y2 = roi
    return (
        int(round(x1 * frame_width)),
        int(round(y1 * frame_height)),
        int(round(x2 * frame_width)),
        int(round(y2 * frame_height)),
    )


bin_boxes = {
    name: normalized_roi_to_bbox(roi)
    for name, roi in RULE_BASED_BIN_ROIS.items()
}

print("[BIN] 룰 기반 쓰레기통 ROI 적용")
for name, bbox in bin_boxes.items():
    print(f"  - {name}: {bbox}")

# key = ByteTrack 내부 raw ID
active_tracks = {}
completed_tracks = set()

# 화면에 보여줄 간단한 T1, T2, T3 ... 번호
next_display_id = 1

# 실제 최종 투입 이벤트 개수
confirmed_event_count = 0

# 최근 확정 Track의 실제 관찰 구간을 통별로 저장
# 같은 물체가 Track ID만 끊겨 재생성된 경우를 구분하는 데 사용
last_confirmed_track_by_bin = {}

frame_index = 0
saved_hard_example_keys = set()
saved_hard_example_count = 0


# ============================================================
# 5. 공통 유틸 함수
# ============================================================
def point_inside_box(x, y, bbox):
    x1, y1, x2, y2 = bbox
    return x1 <= x <= x2 and y1 <= y <= y2


def point_inside_bin_roi(x, y, bin_class, bbox, margin_ratio=0.0):
    """Check a rectangular ROI or the coffee-bin elliptical opening."""
    test_bbox = (
        expand_bbox(bbox, margin_ratio)
        if margin_ratio > 0.0
        else bbox
    )

    if bin_class not in ELLIPTICAL_BIN_ROIS:
        return point_inside_box(x, y, test_bbox)

    x1, y1, x2, y2 = test_bbox
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    radius_x = max(1.0, (x2 - x1) / 2.0)
    radius_y = max(1.0, (y2 - y1) / 2.0)

    return (
        ((x - center_x) / radius_x) ** 2
        + ((y - center_y) / radius_y) ** 2
        <= 1.0
    )


def save_hard_example(frame, reason, raw_track_id):
    """Save one raw frame per track/reason for future model retraining."""
    global saved_hard_example_count

    if not SAVE_HARD_EXAMPLES or frame is None:
        return

    if saved_hard_example_count >= MAX_HARD_EXAMPLE_IMAGES:
        return

    key = (reason, raw_track_id)
    if key in saved_hard_example_keys:
        return

    safe_track_id = "none" if raw_track_id is None else str(raw_track_id)
    filename = (
        f"{RUN_SESSION_ID}_frame_{frame_index:06d}_"
        f"track_{safe_track_id}_{reason}.jpg"
    )
    image_path = HARD_EXAMPLE_DIR / filename

    if cv2.imwrite(str(image_path), frame):
        saved_hard_example_keys.add(key)
        saved_hard_example_count += 1
        print(f"[HARD-EXAMPLE] {image_path}")


_detection_clahe = cv2.createCLAHE(
    clipLimit=CLAHE_CLIP_LIMIT,
    tileGridSize=(8, 8),
)


def prepare_detection_frame(frame):
    """Improve local contrast and sharpen only genuinely soft frames."""
    if not ENABLE_DETECTION_ENHANCEMENT:
        return frame

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)
    lightness = _detection_clahe.apply(lightness)
    enhanced = cv2.cvtColor(
        cv2.merge((lightness, channel_a, channel_b)),
        cv2.COLOR_LAB2BGR,
    )

    gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

    if blur_score < BLUR_VARIANCE_THRESHOLD:
        soft = cv2.GaussianBlur(enhanced, (0, 0), UNSHARP_SIGMA)
        enhanced = cv2.addWeighted(
            enhanced,
            1.0 + UNSHARP_AMOUNT,
            soft,
            -UNSHARP_AMOUNT,
            0,
        )

    return enhanced


def find_entry_bin(x, y):
    """
    쓰레기통 YOLO bbox 전체를 투입 영역으로 사용한다.
    쓰레기통 bbox끼리 겹치지 않는다는 MVP 전제.
    """
    candidates = [
        (bin_class, bbox)
        for bin_class, bbox in bin_boxes.items()
        if point_inside_bin_roi(x, y, bin_class, bbox)
    ]

    if not candidates:
        return None

    # ROI가 조금 겹치면 더 작은(구체적인) 영역을 우선한다.
    return min(
        candidates,
        key=lambda item: (
            (item[1][2] - item[1][0])
            * (item[1][3] - item[1][1])
        ),
    )[0]


def expand_bbox(bbox, margin_ratio):
    """Expand a bin ROI slightly to tolerate sparse 10 FPS observations."""
    x1, y1, x2, y2 = bbox
    margin_x = int(max(1, x2 - x1) * margin_ratio)
    margin_y = int(max(1, y2 - y1) * margin_ratio)

    return (
        max(0, x1 - margin_x),
        max(0, y1 - margin_y),
        min(frame_width - 1, x2 + margin_x),
        min(frame_height - 1, y2 + margin_y),
    )


def predict_missing_bottom_center(track, target_frame):
    """Linearly extrapolate a reliable track across a very short blur gap."""
    history = track["motion_history"]
    if len(history) < 2:
        return None

    first_frame, first_x, first_y = history[0]
    last_frame, last_x, last_y = history[-1]
    elapsed = last_frame - first_frame

    if elapsed <= 0:
        return None

    velocity_x = (last_x - first_x) / elapsed
    velocity_y = (last_y - first_y) / elapsed
    speed = (velocity_x ** 2 + velocity_y ** 2) ** 0.5

    if speed < MIN_MOTION_PIXELS_PER_FRAME:
        return None

    gap = target_frame - last_frame
    return (
        int(round(last_x + velocity_x * gap)),
        int(round(last_y + velocity_y * gap)),
    )


def find_predicted_entry_bin(x, y):
    """Use a small tolerance only for short, motion-blurred detection gaps."""
    for bin_class, bbox in bin_boxes.items():
        if point_inside_bin_roi(
            x,
            y,
            bin_class,
            bbox,
            BIN_ENTRY_MARGIN_RATIO,
        ):
            return bin_class
    return None


def crop_with_margin(frame, bbox):
    """이벤트 기록용 쓰레기 crop."""
    x1, y1, x2, y2 = bbox

    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)

    mx = int(box_w * CROP_MARGIN_RATIO)
    my = int(box_h * CROP_MARGIN_RATIO)

    h, w = frame.shape[:2]

    cx1 = max(0, x1 - mx)
    cy1 = max(0, y1 - my)
    cx2 = min(w, x2 + mx)
    cy2 = min(h, y2 + my)

    crop = frame[cy1:cy2, cx1:cx2]

    return crop.copy() if crop.size > 0 else None


# ============================================================
# 6. 쓰레기 종류 결정 / 정상·오투입 판정
# ============================================================
def add_class_score(track, class_name, confidence):
    """
    같은 Track에서 프레임별 쓰레기 class confidence를 누적한다.
    한두 프레임 분류가 흔들려도 전체 Track 기준으로 최종 종류를 결정한다.
    """
    if class_name not in TRASH_CLASSES:
        return

    track["class_scores"][class_name] = (
        track["class_scores"].get(class_name, 0.0)
        + float(confidence)
    )


def get_final_trash_type(track):
    if not track["class_scores"]:
        return None

    final_class = max(
        track["class_scores"],
        key=track["class_scores"].get,
    )

    return TRASH_TYPE_MAP[final_class]


def judge_disposal(detected_class, bin_id):
    allowed_bins = VALID_BIN_MAP.get(detected_class)

    if allowed_bins is None:
        return "unknown"

    return "correct" if bin_id in allowed_bins else "incorrect"


# ============================================================
# 7. 이벤트 생성
# ============================================================
def create_disposal_event(raw_track_id, bin_class, track):
    """AI 모듈에서 백엔드로 넘길 최종 이벤트 JSON 생성."""
    event_id = str(uuid.uuid4())

    detected_class = get_final_trash_type(track)
    bin_id = BIN_TYPE_MAP[bin_class]
    result = judge_disposal(detected_class, bin_id)

    image_path = None

    if track["best_crop"] is not None:
        image_path = SAVE_DIR / f"{event_id}.jpg"
        cv2.imwrite(str(image_path), track["best_crop"])

    return {
        "eventId": event_id,

        # ByteTrack 내부 ID.
        # 절대 쓰레기 개수로 사용하면 안 됨.
        "trackId": raw_track_id,

        "timestamp": datetime.now().astimezone().isoformat(),
        "cameraId": CAMERA_ID,
        "detectedClass": detected_class,
        "binId": bin_id,
        "result": result,
        "imagePath": str(image_path) if image_path else None,
    }


# ============================================================
# 8. 백엔드 전달 함수
# ============================================================
def handle_disposal_event(event):
    """
    ★ 백엔드 연동 시 주로 수정할 함수 ★

    현재:
        - 콘솔 출력
        - JSONL 저장

    추후:
        - FastAPI POST 추가

    주의:
        쓰레기 개수는 trackId 값이 아니라
        실제 생성된 eventId 개수로 계산해야 한다.
    """
    print("\n========================================")
    print("★ 쓰레기 투입 이벤트 ★")
    print(json.dumps(event, indent=2, ensure_ascii=False))
    print("========================================\n")

    with EVENT_LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")

    # FastAPI 연동 예시
    # import requests
    # response = requests.post(
    #     "http://127.0.0.1:8000/api/events",
    #     json=event,
    #     timeout=3,
    # )
    # print(response.status_code)


# ============================================================
# 9. 쓰레기통 화면 표시
# ============================================================
def draw_bins(frame):
    for bin_name, bbox in bin_boxes.items():
        x1, y1, x2, y2 = bbox

        if bin_name in ELLIPTICAL_BIN_ROIS:
            center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            axes = (max(1, int((x2 - x1) / 2)), max(1, int((y2 - y1) / 2)))
            cv2.ellipse(
                frame,
                center,
                axes,
                0,
                0,
                360,
                (255, 255, 0),
                2,
            )
        else:
            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (255, 255, 0),
                2,
            )

        cv2.putText(
            frame,
            BIN_TYPE_MAP[bin_name],
            (x1, max(20, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 0),
            2,
        )


# ============================================================
# 11. 메인 루프
# ============================================================
try:
    while True:
        ret, frame = cap.read()

        if not ret:
            print("영상 입력이 종료되었습니다.")
            break

        frame_index += 1
        clean_frame = frame.copy()
        detection_frame = prepare_detection_frame(clean_frame)

        # 쓰레기만 YOLO + BoT-SORT + ReID로 추적한다.
        # 쓰레기통은 위에서 지정한 고정 ROI를 사용한다.
        results = model.track(
            source=detection_frame,
            persist=True,
            tracker=TRACKER_CONFIG,
            classes=TRASH_CLASS_IDS,
            conf=CONFIDENCE,
            imgsz=INFERENCE_IMAGE_SIZE,
            agnostic_nms=True,
            verbose=False,
        )

        result = results[0]

        # 현재 화면에 실제로 보이는 '등록된' 쓰레기 Track
        current_trash_ids = set()

        if result.boxes is not None and len(result.boxes) > 0:
            boxes = result.boxes.xyxy.cpu().numpy()
            classes = result.boxes.cls.cpu().numpy()
            confidences = result.boxes.conf.cpu().numpy()

            track_ids = (
                result.boxes.id.cpu().numpy()
                if result.boxes.id is not None
                else [None] * len(boxes)
            )

            # =================================================
            # 12. 쓰레기 탐지 / Tracking
            # =================================================
            for box, cls, conf, raw_track_id in zip(
                boxes,
                classes,
                confidences,
                track_ids,
            ):
                class_name = model.names[int(cls)]

                if class_name not in TRASH_CLASSES:
                    continue

                if raw_track_id is None:
                    continue

                raw_track_id = int(raw_track_id)
                x1, y1, x2, y2 = map(int, box)

                if raw_track_id in completed_tracks:
                    continue

                # =============================================
                # 13. 새로운 쓰레기 Track 등록
                # =============================================
                if raw_track_id not in active_tracks:
                    if float(conf) < NEW_TRASH_CONFIDENCE:
                        save_hard_example(
                            clean_frame,
                            "low_confidence",
                            raw_track_id,
                        )
                        # 약하게 순간적으로 잡힌 새 ID는 이벤트 객체로 등록하지 않음
                        continue

                    display_id = next_display_id
                    next_display_id += 1

                    active_tracks[raw_track_id] = {
                        "display_id": display_id,
                        "class_scores": {},

                        # 이벤트 신뢰성 조건
                        "visible_frames": 0,
                        "first_seen_frame": frame_index,
                        "last_seen_frame": frame_index,
                        "seen_outside_bin": False,
                        "outside_seen_frames": 0,

                        # 현재 후보 쓰레기통 상태
                        "inside_bin": None,
                        "inside_frames": 0,
                        "outside_frames": 0,

                        # Track 유지/종료 상태
                        "missing_frames": 0,
                        "best_confidence": -1.0,
                        "best_crop": None,
                        "last_bbox": (x1, y1, x2, y2),
                        "motion_history": [],
                        "blur_bridge_frames": 0,
                    }

                    print(
                        f"[TRIGGER] T{display_id} "
                        f"(ByteTrack={raw_track_id}), "
                        f"class={class_name}, conf={float(conf):.2f}"
                    )

                track = active_tracks[raw_track_id]
                current_trash_ids.add(raw_track_id)

                previous_type = get_final_trash_type(track)
                current_detection_type = TRASH_TYPE_MAP[class_name]

                if (
                    previous_type is not None
                    and previous_type != current_detection_type
                ):
                    save_hard_example(
                        clean_frame,
                        "class_changed",
                        raw_track_id,
                    )

                # =============================================
                # 14. 쓰레기 종류 누적 판정
                # =============================================
                add_class_score(track, class_name, conf)

                track["visible_frames"] += 1
                track["last_seen_frame"] = frame_index
                track["missing_frames"] = 0
                track["last_bbox"] = (x1, y1, x2, y2)

                # =============================================
                # 15. 이벤트 이미지용 best crop
                # =============================================
                if float(conf) > track["best_confidence"]:
                    crop = crop_with_margin(
                        frame,
                        (x1, y1, x2, y2),
                    )

                    if crop is not None:
                        track["best_confidence"] = float(conf)
                        track["best_crop"] = crop

                # =============================================
                # 16. 어느 쓰레기통 bbox 안에 있는지 판정
                # =============================================
                # 쓰레기 bbox의 하단 중앙점 사용
                bottom_x = int((x1 + x2) / 2)
                bottom_y = y2

                track["motion_history"].append(
                    (frame_index, bottom_x, bottom_y)
                )
                track["motion_history"] = track["motion_history"][
                    -MOTION_HISTORY_SIZE:
                ]
                track["blur_bridge_frames"] = 0

                current_bin = find_entry_bin(
                    bottom_x,
                    bottom_y,
                )

                if current_bin is not None:
                    track["outside_frames"] = 0

                    if track["inside_bin"] == current_bin:
                        track["inside_frames"] += 1
                    else:
                        # 다른 통으로 이동하면 후보 통 변경
                        track["inside_bin"] = current_bin
                        track["inside_frames"] = 1

                else:
                    # 중요: 통 안에서 갑자기 생긴 오탐 Track은 이벤트로 인정하지 않는다.
                    # 실제 쓰레기라면 먼저 쓰레기통 밖에서 관찰된 뒤 통으로 이동해야 한다.
                    track["seen_outside_bin"] = True
                    track["outside_seen_frames"] += 1
                    track["outside_frames"] += 1

                    if track["outside_frames"] >= EXIT_RESET_FRAMES:
                        # 이전 통에서 다시 나왔다면 후보 취소
                        track["inside_bin"] = None
                        track["inside_frames"] = 0

                # =============================================
                # 17. 쓰레기 화면 표시
                # =============================================
                current_type = get_final_trash_type(track)
                display_id = track["display_id"]

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2,
                )

                # 화면에는 ByteTrack 299 같은 숫자 대신 T1, T2 사용
                label = f"T{display_id} {current_type or 'unknown'}"

                if track["inside_bin"] is not None:
                    label += f" -> {BIN_TYPE_MAP[track['inside_bin']]}"

                cv2.putText(
                    frame,
                    label,
                    (x1, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                )

                cv2.circle(
                    frame,
                    (bottom_x, bottom_y),
                    5,
                    (0, 0, 255),
                    -1,
                )

        # =====================================================
        # 18. 고정된 쓰레기통 bbox 표시
        # =====================================================
        draw_bins(frame)

        # =====================================================
        # 19. 현재 프레임에서 사라진 쓰레기 확인
        # =====================================================
        for raw_track_id in list(active_tracks.keys()):
            if raw_track_id in current_trash_ids:
                continue

            track = active_tracks[raw_track_id]
            track["missing_frames"] += 1

            if (
                track["missing_frames"] == 1
                and track["visible_frames"] >= MIN_TRACK_VISIBLE_FRAMES
            ):
                save_hard_example(
                    clean_frame,
                    "track_missing",
                    raw_track_id,
                )

            # If YOLO completely misses a few blurred frames, project the last
            # observed motion into the bin. It cannot create a new track.
            if (
                track["visible_frames"] >= MIN_TRACK_VISIBLE_FRAMES
                and track["missing_frames"] <= BLUR_GAP_BRIDGE_FRAMES
            ):
                predicted_point = predict_missing_bottom_center(
                    track,
                    frame_index,
                )

                if predicted_point is not None:
                    predicted_bin = find_predicted_entry_bin(*predicted_point)

                    if predicted_bin is not None:
                        if track["inside_bin"] == predicted_bin:
                            track["inside_frames"] += 1
                        else:
                            track["inside_bin"] = predicted_bin
                            track["inside_frames"] = 1

                        track["outside_frames"] = 0
                        track["blur_bridge_frames"] += 1

            valid_bin_candidate = (
                # 시연용 완화 조건:
                # YOLO가 늦게 잡아서 처음 탐지부터 통 내부일 수 있으므로
                # "통 밖에서 먼저 관찰" 조건은 사용하지 않는다.

                # 너무 짧게 잡힌 순간 오탐은 제거
                track["visible_frames"] >= MIN_TRACK_VISIBLE_FRAMES

                # 마지막으로 특정 쓰레기통 내부에 충분히 들어가 있었는지
                and track["inside_bin"] is not None
                and track["inside_frames"] >= MIN_INSIDE_FRAMES
            )

            # ================================================
            # 20. 최종 투입 확정
            # ================================================
            if (
                valid_bin_candidate
                and track["missing_frames"] >= DISAPPEAR_CONFIRM_FRAMES
            ):
                bin_class = track["inside_bin"]

                # ------------------------------------------------
                # Track fragment 중복 제거
                #
                # 이전 Track과 현재 Track이 동시에 존재했던 구간이 있으면
                # 서로 다른 실제 쓰레기일 수 있으므로 둘 다 인정한다.
                #
                # 이전 Track이 끝난 직후 현재 Track이 새 ID로 시작됐고
                # 같은 쓰레기통으로 들어갔다면 ID-switch/fragment 가능성이 높아
                # MVP에서는 중복 이벤트로 제거한다.
                # ------------------------------------------------
                previous_track = last_confirmed_track_by_bin.get(bin_class)
                likely_fragment_duplicate = False

                if (
                    FRAGMENT_DUPLICATE_GAP_FRAMES > 0
                    and previous_track is not None
                ):
                    intervals_overlap = not (
                        track["first_seen_frame"] > previous_track["last_seen_frame"]
                        or track["last_seen_frame"] < previous_track["first_seen_frame"]
                    )

                    fragment_gap = (
                        track["first_seen_frame"]
                        - previous_track["last_seen_frame"]
                    )

                    likely_fragment_duplicate = (
                        not intervals_overlap
                        and 0 <= fragment_gap <= FRAGMENT_DUPLICATE_GAP_FRAMES
                    )

                if likely_fragment_duplicate:
                    print(
                        f"[FRAGMENT-SKIP] T{track['display_id']} "
                        f"(ByteTrack={raw_track_id}) / "
                        f"bin={BIN_TYPE_MAP[bin_class]} / "
                        f"gap={fragment_gap} frames"
                    )

                    completed_tracks.add(raw_track_id)
                    del active_tracks[raw_track_id]
                    continue

                event = create_disposal_event(
                    raw_track_id,
                    bin_class,
                    track,
                )

                handle_disposal_event(event)

                last_confirmed_track_by_bin[bin_class] = {
                    "first_seen_frame": track["first_seen_frame"],
                    "last_seen_frame": track["last_seen_frame"],
                    "confirmed_frame": frame_index,
                }

                confirmed_event_count += 1
                completed_tracks.add(raw_track_id)
                del active_tracks[raw_track_id]
                continue

            # ================================================
            # 21. 아무 통에도 들어가지 않고 사라진 Track 제거
            # ================================================
            if (
                not valid_bin_candidate
                and track["missing_frames"] >= TRACK_EXPIRE_FRAMES
            ):
                print(
                    f"[EXPIRE] T{track['display_id']} "
                    f"(ByteTrack={raw_track_id}) - 투입 확인 안 됨"
                )

                del active_tracks[raw_track_id]

        # =====================================================
        # 22. 화면 상태 표시
        # =====================================================
        cv2.putText(
            frame,
            f"Visible trash: {len(current_trash_ids)}",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )

        cv2.putText(
            frame,
            f"Confirmed events: {confirmed_event_count}",
            (20, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
        )

        cv2.putText(
            frame,
            f"Tracked memory: {len(active_tracks)}",
            (20, 84),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

        # =====================================================
        # 23. 결과 영상 저장 / 화면 출력
        # =====================================================
        if video_writer is not None:
            video_writer.write(frame)

        cv2.imshow("YOLO + ByteTrack Waste Realtime", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break


finally:
    cap.release()
    if video_writer is not None:
        video_writer.release()
    cv2.destroyAllWindows()

    if video_writer is not None:
        print(f"결과 영상 저장 완료: {OUTPUT_VIDEO_PATH}")
    print(f"최종 확정 이벤트 수: {confirmed_event_count}")
    print(f"Hard example 저장 수: {saved_hard_example_count}")
