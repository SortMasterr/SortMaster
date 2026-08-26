"""SIDE(ELEV-SIDE) 넘침 판정 — GPU 서버에서 상시 실행되는 독립 스크립트.

models/trashdetect/tracking2.py(TOP)와 완전히 동일한 패턴: 로컬 백엔드가 상시 서빙 중인
MJPEG 스트림(GET /api/stream/ELEV-SIDE)을 SSH 역터널로 구독해서 MobileNet_V3_Small로
직접 판정하고, 결과를 POST /api/binStates로 로컬 백엔드에 푸시한다(로컬 백엔드가 프레임을
보내거나 이 스크립트를 호출하는 게 아니라, 이 스크립트가 먼저 판정 후 백엔드를 호출하는
방향 — TOP과 동일).

한때 "SIDE는 GPU 서버 미사용, 로컬 백엔드가 CPU로 직접 추론"으로 확정했었으나(그때 만든
services/overflowDetectionService.py), TOP과 아키텍처를 일관되게 맞추기 위해 다시
뒤집음(decisionLog.md 참고). GPU 자원 자체가 꼭 필요해서가 아니라(MobileNet_V3_Small은
CPU로도 충분히 빠름) 판정 위치를 TOP과 통일하기 위한 결정 — GPU 서버가 CUDA를 사용 가능하면
자동으로 쓰고, 아니어도 CPU로 정상 동작한다.

모델 가중치(bestSide.pt)/ROI 설정(roi.json)이 없으면 시작 시 바로 실패한다(tracking2.py의
"기대 계약과 다르면 즉시 실패" 원칙과 동일) — 팀원에게 받아 이 스크립트와 같은 디렉터리에
둘 것.
"""
import json
import os
import time
import uuid

import cv2
import numpy as np
import requests
import torch
from torch import nn
from torchvision import models, transforms


# ============================================================
# 1. 기본 설정
# ============================================================
MODEL_PATH = "bestSide.pt"
ROI_PATH = "roi.json"
DEFAULT_IMAGE_SIZE = 224

# SSH 역터널이 GPU 서버 루프백에 열어주는 주소 — docker-compose.yml이 network_mode: host로
# 호스트 네트워크를 공유하므로 컨테이너 안 127.0.0.1도 그대로 유효함(tracking2.py와 동일
# 이유, host.docker.internal은 SSH -R이 루프백에만 리스닝해서 "Connection refused" 남).
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")

# 로컬 백엔드가 상시 서빙 중인 SIDE MJPEG 스트림 — TOP(tracking2.py)과 같은 SSH 역터널
# (-R 8299:localhost:8047, gpuServerOps.md 참고)로 그대로 구독. 별도 포트/터널 불필요.
SOURCE = f"http://{BACKEND_HOST}:8299/api/stream/ELEV-SIDE"

# 실시간 네트워크 스트림이라 끊길 수 있음 — 끊기면 재연결 시도(tracking2.py와 동일 패턴)
IS_LIVE_STREAM_SOURCE = (
    isinstance(SOURCE, str) and SOURCE.startswith("http")
)
STREAM_RECONNECT_DELAY_SECONDS = 2.0

CAMERA_ID = "ELEV-SIDE"

# 물리 통 4개(binId) 중 이 모델/roi.json이 실제로 보고 있는 통 하나 — roi.json이 현재
# 단일 ROI만 지원해서 우선 통 1개로 매핑(decisionLog.md 참고, 통 4개 각각 독립 판정하려면
# ROI를 나누고 모델을 통별로 돌려야 함 — TBD). 실제 설치 후 카메라 구도에 맞게 조정 필요.
BIN_ID = "bin-side-01"
BIN_TYPE = "normal"

# 로컬 백엔드 주소 — GPU 서버 포트는 팀 공유 규칙상 99로 끝나야 해서 8047을 그대로 못 씀.
# SSH 역터널(-R 8299:localhost:8047)로 도커 PC의 8047을 GPU 서버의 8299로 매핑해서 접속
BACKEND_URL = f"http://{BACKEND_HOST}:8299/api/binStates"

OVERFLOW_SECONDS = 30.0
NORMAL_RESET_SECONDS = 1.0
CONFIDENCE_THRESHOLD = 0.70
SAMPLE_INTERVAL_SECONDS = 1.0
MODEL_VERSION = "trashoverflow-mobilenet_v3_small-v1"


# ============================================================
# 2. 모델 / ROI 로드
# ============================================================
with open(ROI_PATH, "r", encoding="utf-8") as roiFile:
    roi = json.load(roiFile)

for _key in ("x1", "y1", "x2", "y2"):
    if _key not in roi:
        raise RuntimeError(f"roi.json에 {_key}가 없습니다.")

device = "cuda" if torch.cuda.is_available() else "cpu"
checkpoint = torch.load(MODEL_PATH, map_location=device)

model = models.mobilenet_v3_small(weights=None)
model.classifier[3] = nn.Linear(model.classifier[3].in_features, 2)
model.load_state_dict(checkpoint["model_state_dict"])
model = model.to(device)
model.eval()

classes = checkpoint.get("classes", ["normal", "overflow"])
imageSize = checkpoint.get("image_size", DEFAULT_IMAGE_SIZE)

transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((imageSize, imageSize)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    ),
])

print(f"[MODEL] device={device}, classes={classes}")

cap = cv2.VideoCapture(SOURCE)
if not cap.isOpened():
    raise RuntimeError("SIDE 스트림을 열 수 없습니다.")


# ============================================================
# 3. 판정 상태
# ============================================================
sessionId = f"side-{int(time.time())}"
overflowStartTime = None
normalStartTime = None
finalOverflow = False
overflowDuration = 0.0
previousFinalOverflow = False


# ============================================================
# 4. 유틸 함수
# ============================================================
def crop_roi(frame):
    height, width = frame.shape[:2]
    x1 = max(0, min(int(roi["x1"]), width))
    y1 = max(0, min(int(roi["y1"]), height))
    x2 = max(0, min(int(roi["x2"]), width))
    y2 = max(0, min(int(roi["y2"]), height))

    if x2 <= x1 or y2 <= y1:
        raise ValueError("ROI 좌표가 잘못되었습니다.")

    return frame[y1:y2, x1:x2]


def run_inference(frame):
    roi_image = crop_roi(frame)
    image = transform(roi_image).unsqueeze(0).to(device)

    with torch.no_grad():
        output = model(image)
        probabilities = torch.softmax(output, dim=1)[0]

    predicted_index = torch.argmax(probabilities).item()
    confidence = probabilities[predicted_index].item()
    predicted_class = classes[predicted_index]

    frame_overflow = (
        predicted_class == "overflow"
        and confidence >= CONFIDENCE_THRESHOLD
    )

    return predicted_class, confidence, frame_overflow


def update_overflow_state(frame_overflow, clock_time):
    global overflowStartTime, normalStartTime
    global finalOverflow, overflowDuration

    if frame_overflow:
        normalStartTime = None

        if overflowStartTime is None:
            overflowStartTime = clock_time

        overflowDuration = clock_time - overflowStartTime

        if overflowDuration >= OVERFLOW_SECONDS:
            finalOverflow = True
    else:
        if overflowStartTime is None:
            overflowDuration = 0.0
            finalOverflow = False
            normalStartTime = None
        else:
            if normalStartTime is None:
                normalStartTime = clock_time

            if clock_time - normalStartTime >= NORMAL_RESET_SECONDS:
                overflowStartTime = None
                normalStartTime = None
                overflowDuration = 0.0
                finalOverflow = False


def report_bin_state(confidence):
    update = {
        "binId": BIN_ID,
        "cameraId": CAMERA_ID,
        "binType": BIN_TYPE,
        "sessionId": sessionId,
        "currentState": "FULL" if finalOverflow else "NORMAL",
        "confidenceScore": confidence,
        "overflowDuration": overflowDuration,
        "overflowThreshold": OVERFLOW_SECONDS,
        "detectionId": str(uuid.uuid4()),
        "modelVersion": MODEL_VERSION,
    }

    try:
        response = requests.post(BACKEND_URL, json=update, timeout=3)
        print(f"[BACKEND] POST {BACKEND_URL} -> {response.status_code}")
    except requests.RequestException as error:
        # 네트워크 문제로 전송이 실패해도 판정 루프 자체는 계속 돈다
        print(f"[BACKEND] 전송 실패: {error}")


# ============================================================
# 5. 메인 루프
# ============================================================
try:
    while True:
        ret, frame = cap.read()

        if not ret:
            if IS_LIVE_STREAM_SOURCE:
                print(
                    f"[STREAM] '{SOURCE}' 프레임 수신 실패, "
                    f"{STREAM_RECONNECT_DELAY_SECONDS:.0f}초 후 재연결 시도"
                )
                cap.release()
                time.sleep(STREAM_RECONNECT_DELAY_SECONDS)
                cap = cv2.VideoCapture(SOURCE)
                continue

            print("영상 입력이 종료되었습니다.")
            break

        predictedClass, confidence, frameOverflow = run_inference(
            np.asarray(frame)
        )
        update_overflow_state(frameOverflow, time.monotonic())

        print(
            f"[SIDE] class={predictedClass}, conf={confidence:.2f}, "
            f"overflow={finalOverflow} "
            f"({overflowDuration:.1f}s/{OVERFLOW_SECONDS:.0f}s)"
        )

        if finalOverflow != previousFinalOverflow:
            report_bin_state(confidence)
            previousFinalOverflow = finalOverflow

        # 넘침 판정은 매 프레임 볼 필요 없음(1초 간격이면 충분) — 그만큼 쉬어서
        # CPU를 아낀다. 스트림 자체는 그대로 흘려보내지 말고 다음 read() 전까지 대기.
        time.sleep(SAMPLE_INTERVAL_SECONDS)

finally:
    cap.release()
    print("SIDE 넘침 판정 루프 종료")
