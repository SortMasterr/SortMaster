"""
Trash Overflow Detection API Server
====================================

기존 video 순회 스크립트를 API 서버로 변환한 버전입니다.

- 클라이언트는 프레임(이미지) 하나씩 전송합니다.
- 서버는 session_id 별로 overflow 유지 시간 상태를 메모리에 저장/추적합니다.
- 같은 session_id로 계속 프레임을 보내면, 원래 코드의
  "overflow가 N초 이상 연속 유지되면 최종 OVERFLOW" 로직이 그대로 동작합니다.
- 매 프레임마다 기존 imshow용 오버레이(ROI 박스, 판정 텍스트 등)를 그려서
  세션별로 result/{session_id}.mp4 에 이어붙여 저장합니다.

시간 기준 (중요):
    이 서버는 두 가지 입력 방식을 모두 지원합니다.

    1) 실시간 스트림 (카메라에서 캡처 즉시 전송)
       -> timestamp 파라미터를 주지 않으면 서버가 요청이 도착한
          실제 시각(time.monotonic())을 기준으로 판정합니다.
          이 경우는 요청 간격 = 실제 경과 시간이므로 정확합니다.

    2) 녹화된 영상 파일을 프레임으로 쪼개서 빠르게(배속으로) 전송
       -> 이 경우 서버 도착 간격은 실제 영상 재생 시간과 다르므로,
          클라이언트가 각 프레임의 "영상 재생 시점(초)"을 timestamp
          파라미터로 함께 보내야 합니다. (예: frame_index / fps)
          timestamp를 보내면 서버는 그 값을 기준 시계로 사용합니다.

    같은 session_id 안에서는 두 방식을 섞지 말고 한쪽으로 통일해야
    합니다 (섞이면 시간 기준이 뒤죽박죽되어 판정이 부정확해집니다).

실행:
    pip install fastapi uvicorn python-multipart opencv-python-headless torch torchvision
    uvicorn trashoverflow_api:app --host 0.0.0.0 --port 8000

사용 예 (curl):
    # 1) 실시간 스트림 (timestamp 생략 -> 서버 실시간 기준)
    curl -X POST "http://localhost:8000/predict?session_id=cam1" \
         -F "file=@frame.jpg"

    # 2) 녹화 영상을 빠르게 전송하는 경우 (영상 재생 시점을 직접 지정)
    curl -X POST "http://localhost:8000/predict?session_id=video1&timestamp=12.4" \
         -F "file=@frame.jpg"

    # 영상 파일 저장 완료 (release), 세션 상태는 유지
    curl -X POST "http://localhost:8000/finalize/cam1"

    # 세션 상태 초기화 + 영상 파일 닫기
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

MODEL_PATH = "./bestSide2.pt"
ROI_FILE = "./roi.json"
IMAGE_SIZE = 224

OVERFLOW_SECONDS = 30.0        # overflow 연속 유지 판정 시간
NORMAL_RESET_SECONDS = 1.0     # overflow 중 잠깐 normal이어도 무시하는 시간
CONFIDENCE_THRESHOLD = 0.70

# 세션이 이 시간 동안 요청이 없으면 정리 대상으로 간주 (초)
SESSION_IDLE_TIMEOUT = 600.0

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ============================================================
# 결과 영상 저장 설정
# ============================================================
# 프레임이 HTTP로 한 장씩 들어오기 때문에 실제 촬영 fps를 알 수 없습니다.
# 저장되는 영상의 재생 속도는 이 값을 기준으로 합니다.
# (클라이언트가 실제로 보내는 주기와 다르면 재생 속도가 어긋날 수 있습니다.)

RESULT_DIR = "./result"
SAVE_FPS = 10.0
VIDEO_CODEC = "mp4v"  # .mp4 저장용 코덱

os.makedirs(RESULT_DIR, exist_ok=True)


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

        # 결과 영상 저장용
        self.video_writer = None
        self.video_path = None
        self.frame_size = None


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
            close_writer(_sessions[sid])
            del _sessions[sid]

        if session_id not in _sessions:
            _sessions[session_id] = SessionState()

        state = _sessions[session_id]
        state.last_seen = now
        return state


# ============================================================
# 핵심 판정 로직 (기존 while 루프 내부 로직을 함수로 분리)
# ============================================================

def update_overflow_state(state: SessionState, frame_overflow: bool, clock_time: float):
    """clock_time: 이번 프레임 시각의 기준값.

    - 실시간 스트림이면 time.monotonic() (서버 도착 시각)
    - 배치(빠른 전송)이면 클라이언트가 보낸 영상 재생 시점(초)

    어느 쪽이든 "이 세션 안에서 단조 증가하는 시간축"이기만 하면
    이하 로직은 동일하게 동작합니다.
    """

    if frame_overflow:
        state.normal_start_time = None

        if state.overflow_start_time is None:
            state.overflow_start_time = clock_time

        state.overflow_duration = clock_time - state.overflow_start_time

        if state.overflow_duration >= OVERFLOW_SECONDS:
            state.final_overflow = True

    else:
        if state.overflow_start_time is None:
            state.overflow_duration = 0.0
            state.final_overflow = False
            state.normal_start_time = None
        else:
            if state.normal_start_time is None:
                state.normal_start_time = clock_time

            normal_duration = clock_time - state.normal_start_time

            if normal_duration >= NORMAL_RESET_SECONDS:
                state.overflow_start_time = None
                state.normal_start_time = None
                state.overflow_duration = 0.0
                state.final_overflow = False


def draw_overlay(
    frame,
    roi,
    predicted_class,
    confidence,
    final_overflow,
    overflow_duration,
    normal_duration,
    session_id,
):
    """기존 스크립트의 imshow용 오버레이 그리기 로직을 그대로 이식."""

    result_text = "OVERFLOW" if final_overflow else "NORMAL"
    result_color = (0, 0, 255) if final_overflow else (0, 255, 0)

    x1, y1, x2, y2 = int(roi["x1"]), int(roi["y1"]), int(roi["x2"]), int(roi["y2"])

    cv2.rectangle(frame, (x1, y1), (x2, y2), result_color, 3)

    cv2.putText(
        frame, result_text, (30, 50),
        cv2.FONT_HERSHEY_SIMPLEX, 1.2, result_color, 3,
    )

    cv2.putText(
        frame, f"Model: {predicted_class} {confidence:.2f}", (30, 85),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
    )

    duration_text = f"Overflow duration: {overflow_duration:.1f}s / {OVERFLOW_SECONDS:.1f}s"
    cv2.putText(
        frame, duration_text, (30, 120),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
    )

    if normal_duration is not None:
        reset_text = f"Normal reset: {normal_duration:.1f}s / {NORMAL_RESET_SECONDS:.1f}s"
        cv2.putText(
            frame, reset_text, (30, 155),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
        )

    cv2.putText(
        frame, session_id, (30, 190),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
    )

    return frame


def get_or_create_writer(state: "SessionState", session_id: str, frame: np.ndarray):
    """세션의 첫 프레임이 들어오면 result/{session_id}.mp4 파일을 새로 연다."""

    if state.video_writer is not None:
        return state.video_writer

    height, width = frame.shape[:2]
    state.frame_size = (width, height)

    output_path = os.path.join(RESULT_DIR, f"{session_id}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*VIDEO_CODEC)

    writer = cv2.VideoWriter(output_path, fourcc, SAVE_FPS, state.frame_size)

    if not writer.isOpened():
        raise RuntimeError(f"영상 저장 파일을 열 수 없습니다: {output_path}")

    state.video_writer = writer
    state.video_path = output_path

    return writer


def close_writer(state: "SessionState"):
    if state.video_writer is not None:
        state.video_writer.release()
        state.video_writer = None


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
    clock_mode: str                # "client_timestamp" 또는 "server_walltime"
    video_path: str | None = None  # 이번 프레임이 저장된 결과 영상 경로


@app.post("/trashflowmodel/predict", response_model=PredictResponse)
async def predict(
    session_id: str,
    file: UploadFile = File(...),
    save_video: bool = True,
    timestamp: float | None = None,
):
    """
    timestamp: 배치(녹화 영상을 빠르게 전송하는 경우) 전용 파라미터.
               영상 재생 기준 이 프레임의 시점(초)을 넘겨주세요.
               (예: frame_index / fps). 실시간 스트림이면 생략하세요.
    """
    contents = await file.read()

    np_arr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="이미지를 디코딩할 수 없습니다.")

    predicted_class, confidence, frame_overflow = run_inference(frame)

    state = get_session(session_id)

    if timestamp is not None:
        clock_time = timestamp
        clock_mode = "client_timestamp"
    else:
        clock_time = time.monotonic()
        clock_mode = "server_walltime"

    update_overflow_state(state, frame_overflow, clock_time)

    normal_duration = None
    if state.normal_start_time is not None:
        normal_duration = clock_time - state.normal_start_time

    if save_video:
        annotated = draw_overlay(
            frame.copy(),
            ROI,
            predicted_class,
            confidence,
            state.final_overflow,
            state.overflow_duration,
            normal_duration,
            session_id,
        )

        writer = get_or_create_writer(state, session_id, annotated)

        # 프레임 크기가 세션 시작 때와 다르면 강제로 맞춰서 기록 (크기 불일치 시 VideoWriter 오류 방지)
        if (annotated.shape[1], annotated.shape[0]) != state.frame_size:
            annotated = cv2.resize(annotated, state.frame_size)

        writer.write(annotated)

    return PredictResponse(
        session_id=session_id,
        predicted_class=predicted_class,
        confidence=confidence,
        frame_overflow=frame_overflow,
        final_overflow=state.final_overflow,
        overflow_duration=round(state.overflow_duration, 2),
        clock_mode=clock_mode,
        video_path=state.video_path if save_video else None,
    )


@app.post("/trashflowmodel/reset/{session_id}")
def reset_session(session_id: str):
    with _sessions_lock:
        state = _sessions.pop(session_id, None)
        if state is not None:
            close_writer(state)
    return {"session_id": session_id, "reset": True}


@app.post("/trashflowmodel/finalize/{session_id}")
def finalize_session(session_id: str):
    """세션 상태는 유지한 채, 저장 중인 결과 영상만 닫아서 파일을 완성시킵니다."""
    with _sessions_lock:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail="세션이 없습니다.")
        state = _sessions[session_id]
        video_path = state.video_path
        close_writer(state)
    return {"session_id": session_id, "video_path": video_path, "finalized": True}


@app.get("/trashflowmodel/session/{session_id}")
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


@app.get("/trashflowmodel/health")
def health():
    return {"status": "ok", "device": DEVICE, "classes": CLASSES}