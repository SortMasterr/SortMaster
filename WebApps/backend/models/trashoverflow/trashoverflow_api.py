"""
Trash Overflow Detection API Server
====================================

기존 video 순회 스크립트를 API 서버로 변환한 버전입니다.

- 클라이언트는 프레임(이미지) 하나씩 전송합니다.
- 서버는 session_id 별로 overflow 유지 시간 상태를 메모리에 저장/추적합니다.
- 같은 session_id로 계속 프레임을 보내면, 원래 코드의
  "overflow가 30초 이상 연속 유지되면 최종 OVERFLOW" 로직이 그대로 동작합니다.

실행:
    pip install fastapi uvicorn python-multipart opencv-python-headless torch torchvision
    uvicorn api_server:app --host 0.0.0.0 --port 8000

사용 예 (curl):
    curl -X POST "http://localhost:8000/predict?session_id=cam1" \
         -F "file=@frame.jpg"

    curl -X POST "http://localhost:8000/reset/cam1"
"""

import os
import io
import json
import time
import threading

import cv2
import numpy as np
import torch

from torch import nn
from torchvision import models, transforms

from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel


# ============================================================
# 설정 (기존 스크립트와 동일)
# ============================================================

MODEL_PATH = "./best.pt"
ROI_FILE = "./roi.json"
IMAGE_SIZE = 224

OVERFLOW_SECONDS = 10.0        # overflow 연속 유지 판정 시간
NORMAL_RESET_SECONDS = 1.0     # overflow 중 잠깐 normal이어도 무시하는 시간
CONFIDENCE_THRESHOLD = 0.70

# 세션이 이 시간 동안 요청이 없으면 정리 대상으로 간주 (초)
SESSION_IDLE_TIMEOUT = 600.0

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# ============================================================
# ROI 로드 (기존 로직 그대로)
# ============================================================

def load_roi():
    if not os.path.exists(ROI_FILE):
        raise FileNotFoundError(f"{ROI_FILE}가 없습니다.")

    with open(ROI_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        raise RuntimeError("roi.json이 비어 있습니다.")

    try:
        roi = json.loads(content)
    except json.JSONDecodeError:
        raise RuntimeError("roi.json이 올바른 JSON 형식이 아닙니다.")

    for key in ("x1", "y1", "x2", "y2"):
        if key not in roi:
            raise RuntimeError(f"roi.json에 {key}가 없습니다.")

    return roi


def crop_roi(frame, roi):
    height, width = frame.shape[:2]

    x1 = max(0, min(int(roi["x1"]), width))
    y1 = max(0, min(int(roi["y1"]), height))
    x2 = max(0, min(int(roi["x2"]), width))
    y2 = max(0, min(int(roi["y2"]), height))

    if x2 <= x1 or y2 <= y1:
        raise RuntimeError("ROI 좌표가 잘못되었습니다.")

    return frame[y1:y2, x1:x2]


# ============================================================
# 모델 로드 (기존 로직 그대로)
# ============================================================

def load_model():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"{MODEL_PATH}가 없습니다.")

    checkpoint = torch.load(MODEL_PATH, map_location=DEVICE)

    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 2)
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(DEVICE)
    model.eval()

    classes = checkpoint.get("classes", ["normal", "overflow"])
    image_size = checkpoint.get("image_size", IMAGE_SIZE)

    return model, classes, image_size


# ============================================================
# 전역 리소스 로드 (서버 시작 시 1회)
# ============================================================

ROI = load_roi()
MODEL, CLASSES, RESOLVED_IMAGE_SIZE = load_model()

TRANSFORM = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((RESOLVED_IMAGE_SIZE, RESOLVED_IMAGE_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    ),
])


# ============================================================
# 세션별 상태 저장소
# ============================================================
# session_id 하나가 카메라/영상 스트림 하나에 대응한다고 생각하면 됩니다.
# 같은 session_id로 계속 프레임을 보내야 30초 유지 로직이 이어집니다.

class SessionState:
    def __init__(self):
        self.overflow_start_time = None
        self.normal_start_time = None
        self.final_overflow = False
        self.overflow_duration = 0.0
        self.last_seen = time.monotonic()


_sessions: dict[str, SessionState] = {}
_sessions_lock = threading.Lock()


def get_session(session_id: str) -> SessionState:
    with _sessions_lock:
        # 오래된 세션 정리 (요청 처리 김에 가볍게)
        now = time.monotonic()
        stale = [
            sid for sid, s in _sessions.items()
            if now - s.last_seen > SESSION_IDLE_TIMEOUT
        ]
        for sid in stale:
            del _sessions[sid]

        if session_id not in _sessions:
            _sessions[session_id] = SessionState()

        state = _sessions[session_id]
        state.last_seen = now
        return state


# ============================================================
# 핵심 판정 로직 (기존 while 루프 내부 로직을 함수로 분리)
# ============================================================

def update_overflow_state(state: SessionState, frame_overflow: bool):
    now = time.monotonic()

    if frame_overflow:
        state.normal_start_time = None

        if state.overflow_start_time is None:
            state.overflow_start_time = now

        state.overflow_duration = now - state.overflow_start_time

        if state.overflow_duration >= OVERFLOW_SECONDS:
            state.final_overflow = True

    else:
        if state.overflow_start_time is None:
            state.overflow_duration = 0.0
            state.final_overflow = False
            state.normal_start_time = None
        else:
            if state.normal_start_time is None:
                state.normal_start_time = now

            normal_duration = now - state.normal_start_time

            if normal_duration >= NORMAL_RESET_SECONDS:
                state.overflow_start_time = None
                state.normal_start_time = None
                state.overflow_duration = 0.0
                state.final_overflow = False


def run_inference(frame: np.ndarray):
    roi_image = crop_roi(frame, ROI)
    image = TRANSFORM(roi_image).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        output = MODEL(image)
        probabilities = torch.softmax(output, dim=1)[0]

    predicted_index = torch.argmax(probabilities).item()
    confidence = probabilities[predicted_index].item()
    predicted_class = CLASSES[predicted_index]

    frame_overflow = (
        predicted_class == "overflow"
        and confidence >= CONFIDENCE_THRESHOLD
    )

    return predicted_class, confidence, frame_overflow


# ============================================================
# FastAPI 앱
# ============================================================

app = FastAPI(title="Trash Overflow Detection API")


class PredictResponse(BaseModel):
    session_id: str
    predicted_class: str
    confidence: float
    frame_overflow: bool          # 이번 프레임 단독 판정
    final_overflow: bool          # 세션 누적 기준 최종 판정
    overflow_duration: float
    overflow_threshold: float = OVERFLOW_SECONDS


@app.post("/predict", response_model=PredictResponse)
async def predict(session_id: str, file: UploadFile = File(...)):
    contents = await file.read()

    np_arr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="이미지를 디코딩할 수 없습니다.")

    predicted_class, confidence, frame_overflow = run_inference(frame)

    state = get_session(session_id)
    update_overflow_state(state, frame_overflow)

    return PredictResponse(
        session_id=session_id,
        predicted_class=predicted_class,
        confidence=confidence,
        frame_overflow=frame_overflow,
        final_overflow=state.final_overflow,
        overflow_duration=round(state.overflow_duration, 2),
    )


@app.post("/reset/{session_id}")
def reset_session(session_id: str):
    with _sessions_lock:
        _sessions.pop(session_id, None)
    return {"session_id": session_id, "reset": True}


@app.get("/session/{session_id}")
def get_session_status(session_id: str):
    with _sessions_lock:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail="세션이 없습니다.")
        state = _sessions[session_id]
        return {
            "session_id": session_id,
            "final_overflow": state.final_overflow,
            "overflow_duration": round(state.overflow_duration, 2),
        }


@app.get("/health")
def health():
    return {"status": "ok", "device": DEVICE, "classes": CLASSES}