import cv2
import json
import uuid
from pathlib import Path
from datetime import datetime
from statistics import median
from ultralytics import YOLO


# ============================================================
# 1. 기본 설정
# ============================================================
MODEL_PATH = "bestTop.pt"
SOURCE = "mvpTop.mp4"      # 시연 영상 / 웹캠 사용 시 SOURCE = 0
# SOURCE = 0
CAMERA_ID = "CAM-01"

# Tracking 중 낮은 confidence 탐지도 활용
CONFIDENCE = 0.25

# 새로운 쓰레기 Track을 우리 이벤트 시스템에 등록하는 최소 confidence
NEW_TRASH_CONFIDENCE = 0.45

# 쓰레기통 위치를 처음에 잡을 때 사용할 confidence
BIN_CONFIDENCE = 0.30

# 쓰레기통 bbox 전체를 투입 영역으로 사용
MIN_INSIDE_FRAMES = 2
EXIT_RESET_FRAMES = 3

# 이벤트로 인정하기 위한 최소 관찰 조건
# 시연용: 통 밖에서 먼저 잡혀야 한다는 조건은 사용하지 않음
# YOLO가 늦게 잡아 처음 탐지 시 이미 쓰레기통 bbox 안일 수 있기 때문
MIN_TRACK_VISIBLE_FRAMES = 5

# 실제 FPS 기준 시간 설정
DISAPPEAR_CONFIRM_SECONDS = 1.0   # 시연용: 약 1초 미탐지 시 투입 확정
TRACK_EXPIRE_SECONDS = 4.0        # 아무 통에도 안 들어간 Track 정리

# Track이 끊긴 직후 같은 통에서 새 ID로 다시 생성되는 경우를 중복으로 보기 위한 시간
# 서로 동시에 존재한 Track은 중복으로 보지 않으므로 동시 투입은 각각 인정한다.
# 아주 빠르게 같은 통에 순차 투입하는 테스트라면 값을 줄이거나 0으로 설정할 수 있다.
FRAGMENT_DUPLICATE_GAP_SECONDS = 1.5

# 이벤트 이미지 crop 여백
CROP_MARGIN_RATIO = 0.15

# 고정 카메라: 시작 시 쓰레기통 bbox를 여러 프레임에서 수집 후 고정
BIN_CALIBRATION_FRAMES = 25
BIN_MIN_SAMPLES = 8
BIN_CALIBRATION_MAX_FRAMES = 100

# 결과 영상 저장
OUTPUT_VIDEO_PATH = "result_tracking_demo.mp4"
OUTPUT_FPS_FALLBACK = 20.0

# 이벤트 저장
SAVE_DIR = Path("waste_events")
EVENT_LOG_FILE = SAVE_DIR / "events.jsonl"
SAVE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. 클래스 / 분리배출 규칙
# ============================================================
EXPECTED_CLASS_NAMES = {
    0: "trash_normal",
    1: "trash_paper",
    2: "trash_recyclables",
    3: "trash_coffeecup",
    4: "box_normal",
    5: "box_paper",
    6: "box_recyclables",
    7: "box_coffeecup",
}

TRASH_CLASS_IDS = [0, 1, 2, 3]
BIN_CLASS_IDS = [4, 5, 6, 7]

TRASH_CLASSES = {
    "trash_normal",
    "trash_paper",
    "trash_recyclables",
    "trash_coffeecup",
}

BIN_CLASSES = {
    "box_normal",
    "box_paper",
    "box_recyclables",
    "box_coffeecup",
}

TRASH_TYPE_MAP = {
    "trash_normal": "normal",
    "trash_paper": "paper",
    "trash_recyclables": "recyclables",
    "trash_coffeecup": "coffeecup",
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


# ============================================================
# 4. 런타임 상태
# ============================================================
# 쓰레기통은 ByteTrack 대상이 아니다.
# 처음 몇 프레임에서 predict()로 위치만 잡고 이후 고정한다.
bin_boxes = {}
bin_box_samples = {name: [] for name in BIN_CLASSES}
bin_boxes_locked = False

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


# ============================================================
# 5. 공통 유틸 함수
# ============================================================
def point_inside_box(x, y, bbox):
    x1, y1, x2, y2 = bbox
    return x1 <= x <= x2 and y1 <= y <= y2


def find_entry_bin(x, y):
    """
    쓰레기통 YOLO bbox 전체를 투입 영역으로 사용한다.
    쓰레기통 bbox끼리 겹치지 않는다는 MVP 전제.
    """
    for bin_class, bbox in bin_boxes.items():
        if point_inside_box(x, y, bbox):
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


def median_bbox(samples):
    """여러 프레임 bbox의 좌표별 중앙값."""
    if not samples:
        return None

    return (
        int(median([b[0] for b in samples])),
        int(median([b[1] for b in samples])),
        int(median([b[2] for b in samples])),
        int(median([b[3] for b in samples])),
    )


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
# 9. 쓰레기통 초기 위치 보정
# ============================================================
def update_bin_calibration(frame):
    """
    ByteTrack을 쓰지 않고 YOLO predict()로 쓰레기통만 찾는다.

    중요:
        classes=[4,5,6,7]
        → 쓰레기통에는 Track ID를 발급하지 않는다.
    """
    global bin_boxes_locked

    results = model.predict(
        source=frame,
        classes=BIN_CLASS_IDS,
        conf=BIN_CONFIDENCE,
        agnostic_nms=True,
        verbose=False,
    )

    result = results[0]

    if result.boxes is None or len(result.boxes) == 0:
        return

    boxes = result.boxes.xyxy.cpu().numpy()
    classes = result.boxes.cls.cpu().numpy()
    confidences = result.boxes.conf.cpu().numpy()

    # 한 프레임에서 같은 종류 통이 여러 개 나오면 confidence 가장 높은 것 사용
    best_bins = {}

    for box, cls, conf in zip(boxes, classes, confidences):
        class_name = model.names[int(cls)]

        if class_name not in BIN_CLASSES:
            continue

        bbox = tuple(map(int, box))
        previous = best_bins.get(class_name)

        if previous is None or float(conf) > previous["confidence"]:
            best_bins[class_name] = {
                "bbox": bbox,
                "confidence": float(conf),
            }

    for bin_name, data in best_bins.items():
        bin_box_samples[bin_name].append(data["bbox"])

        stable_box = median_bbox(bin_box_samples[bin_name])
        if stable_box is not None:
            bin_boxes[bin_name] = stable_box

    enough_samples = all(
        len(bin_box_samples[name]) >= BIN_MIN_SAMPLES
        for name in BIN_CLASSES
    )

    normal_lock = (
        frame_index >= BIN_CALIBRATION_FRAMES
        and enough_samples
    )

    forced_lock = frame_index >= BIN_CALIBRATION_MAX_FRAMES

    if normal_lock or forced_lock:
        for bin_name in BIN_CLASSES:
            stable_box = median_bbox(bin_box_samples[bin_name])

            if stable_box is not None:
                bin_boxes[bin_name] = stable_box

        missing_bins = [
            name for name in BIN_CLASSES
            if name not in bin_boxes
        ]

        if missing_bins:
            print(
                "[WARNING] 다음 쓰레기통 bbox를 충분히 찾지 못했습니다:",
                missing_bins,
            )

        bin_boxes_locked = True

        print("[BIN] 쓰레기통 bbox 고정 완료")
        for name, bbox in bin_boxes.items():
            print(f"  - {name}: {bbox}")


# ============================================================
# 10. 쓰레기통 화면 표시
# ============================================================
def draw_bins(frame):
    for bin_name, bbox in bin_boxes.items():
        x1, y1, x2, y2 = bbox

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

        # =====================================================
        # 11-1. 시작 시 쓰레기통 위치만 predict()로 보정
        # =====================================================
        if not bin_boxes_locked:
            update_bin_calibration(frame)
            draw_bins(frame)

            cv2.putText(
                frame,
                "Calibrating bins...",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )

            video_writer.write(frame)
            cv2.imshow("YOLO26 + BoT-SORT ReID Waste MVP", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            # 쓰레기통 고정이 끝난 다음 프레임부터 trash Tracking 시작
            continue

        # =====================================================
        # 11-2. 쓰레기만 YOLO + BoT-SORT + ReID
        # =====================================================
        # ★ 가장 중요한 수정
        # classes=[0,1,2,3]
        # 쓰레기통 4~7은 ByteTrack에 들어가지 않는다.
        results = model.track(
            source=frame,
            persist=True,
            tracker="botsort_mvp.yaml",
            classes=TRASH_CLASS_IDS,
            conf=CONFIDENCE,
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
                    }

                    print(
                        f"[TRIGGER] T{display_id} "
                        f"(ByteTrack={raw_track_id}), "
                        f"class={class_name}, conf={float(conf):.2f}"
                    )

                track = active_tracks[raw_track_id]
                current_trash_ids.add(raw_track_id)

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
        video_writer.write(frame)
        cv2.imshow("YOLO26 + BoT-SORT ReID Waste MVP", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break


finally:
    cap.release()
    video_writer.release()
    cv2.destroyAllWindows()

    print(f"결과 영상 저장 완료: {OUTPUT_VIDEO_PATH}")
    print(f"최종 확정 이벤트 수: {confirmed_event_count}")