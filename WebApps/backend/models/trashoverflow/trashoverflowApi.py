"""
Trash Overflow Detection API Server
====================================

기존 video 순회 스크립트를 API 서버로 변환한 버전입니다.

[이번 수정 사항 요약]
  1) 모델을 ResNet18 -> MobileNet_V3_Small로 교체
  2) 전체 스캔하여 실행을 막던 오타/네이밍 버그 수정
     (torch.isAvailable, os.makedirs existOk, cv2 상수 오타,
      torch.noGrad, FastAPI responseModel/statusCode 키워드 오타,
      path parameter 이름 불일치, 미정의 EventCreate/event_service 참조)
  3) 동영상 입력을 흑백으로 전처리한 뒤 predict 하는 옵션 추가
     (전역 스위치 + 요청별 오버라이드 가능)

- 클라이언트는 프레임(이미지) 하나씩 전송합니다.
- 서버는 session_id 별로 overflow 유지 시간 상태를 메모리에 저장/추적합니다.
- 같은 session_id로 계속 프레임을 보내면, 원래 코드의
  "overflow가 N초 이상 연속 유지되면 최종 OVERFLOW" 로직이 그대로 동작합니다.
- 매 프레임마다 기존 imshow용 오버레이(ROI 박스, 판정 텍스트 등)를 그려서
  세션별로 result/{session_id}.mp4 에 이어붙여 저장합니다.
  (흑백 전처리는 모델 입력에만 적용되고, 저장 영상은 원본 컬러 그대로입니다.)

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

흑백 전처리:
    USEGRAYSCALEPREPROCESS = True 로 두면 모든 요청에서 기본적으로
    ROI 크롭 이미지를 흑백으로 변환한 뒤 모델에 넣습니다.
    요청마다 다르게 쓰고 싶다면 predict 호출 시 쿼리 파라미터로
    ?grayscale=true 또는 ?grayscale=false 를 넘기면 전역 설정을 덮어씁니다.

실행:
    pip install fastapi uvicorn python-multipart opencv-python-headless torch torchvision
    uvicorn trashoverflow_api:app --host 0.0.0.0 --port 8000

사용 예 (curl):
    # 1) 실시간 스트림 (timestamp 생략 -> 서버 실시간 기준, 전역 흑백 설정 사용)
    curl -X POST "http://localhost:8000/trashflowmodel/predict?sessionId=cam1" \
         -F "file=@frame.jpg"

    # 2) 녹화 영상을 빠르게 전송하는 경우 (영상 재생 시점을 직접 지정, 이번 요청만 흑백 강제)
    curl -X POST "http://localhost:8000/trashflowmodel/predict?sessionId=video1&timestamp=12.4&grayscale=true" \
         -F "file=@frame.jpg"

    # 영상 파일 저장 완료 (release), 세션 상태는 유지
    curl -X POST "http://localhost:8000/trashflowmodel/finalize/cam1"

    # 세션 상태 초기화 + 영상 파일 닫기
    curl -X POST "http://localhost:8000/trashflowmodel/reset/cam1"
"""

import os
import io
import json
import time
import logging
import threading

import cv2
import numpy as np
import torch

from torch import nn
from torchvision import models, transforms

from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel


logger = logging.getLogger("trashoverflow_api")
logging.basicConfig(level=logging.INFO)


# ============================================================
# 설정
# ============================================================

MODELPATH = "./bestSide.pt"   # MobileNet_V3_Small로 학습된 체크포인트 경로로 교체 필요
ROIFILE = "./roi.json"
IMAGESIZE = 224

OVERFLOWSECONDS = 30.0        # overflow 연속 유지 판정 시간
NORMALRESETSECONDS = 1.0     # overflow 중 잠깐 normal이어도 무시하는 시간
CONFIDENCETHRESHOLD = 0.70

# 세션이 이 시간 동안 요청이 없으면 정리 대상으로 간주 (초)
SESSIONIDLETIMEOUT = 600.0

# [버그 수정 #1] torch.isAvailable() -> torch.cuda.is_available()
# (존재하지 않는 메서드라 import 시점에 바로 AttributeError로 죽던 부분)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ============================================================
# 흑백 전처리 설정 [신규 기능]
# ============================================================
# True로 두면 모델에 들어가는 ROI 이미지를 흑백으로 변환한 뒤 추론합니다.
# (저장되는 확인용 영상은 이 설정과 무관하게 항상 원본 컬러입니다.)
# 요청 단위로 끄고 켜고 싶으면 /predict 호출 시 grayscale=true/false 쿼리
# 파라미터를 쓰세요. (생략 시 이 전역값을 기본으로 사용)
USEGRAYSCALEPREPROCESS = False


# ============================================================
# 결과 영상 저장 설정
# ============================================================
# 프레임이 HTTP로 한 장씩 들어오기 때문에 실제 촬영 fps를 알 수 없습니다.
# 저장되는 영상의 재생 속도는 이 값을 기준으로 합니다.
# (클라이언트가 실제로 보내는 주기와 다르면 재생 속도가 어긋날 수 있습니다.)

RESULTDIR = "./result"
SAVEFPS = 10.0
VIDEOCODEC = "mp4v"  # .mp4 저장용 코덱

# [버그 수정 #2] existOk -> exist_ok
os.makedirs(RESULTDIR, exist_ok=True)


# ============================================================
# ROI 로드 (기존 로직 그대로)
# ============================================================

def loadRoi():
    if not os.path.exists(ROIFILE):
        raise FileNotFoundError(f"{ROIFILE}가 없습니다.")

    with open(ROIFILE, "r", encoding="utf-8") as f:
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


def cropRoi(frame, roi):
    height, width = frame.shape[:2]

    x1 = max(0, min(int(roi["x1"]), width))
    y1 = max(0, min(int(roi["y1"]), height))
    x2 = max(0, min(int(roi["x2"]), width))
    y2 = max(0, min(int(roi["y2"]), height))

    if x2 <= x1 or y2 <= y1:
        raise RuntimeError("ROI 좌표가 잘못되었습니다.")

    return frame[y1:y2, x1:x2]


def toGrayscale3Channel(frame: np.ndarray) -> np.ndarray:
    """[신규] BGR 프레임을 흑백으로 변환한 뒤, 모델이 기대하는 3채널
    형태에 맞추기 위해 동일한 값으로 다시 3채널 복제한다.
    (TRANSFORM의 Normalize가 채널별 mean/std 3개를 쓰므로 1채널 그대로
     넣으면 shape mismatch가 난다. 3채널로 복제하면 파이프라인을
     건드리지 않고 흑백 효과만 낼 수 있다.)
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


# ============================================================
# 모델 로드
# [수정] ResNet18 -> MobileNet_V3_Small 교체
#   - ResNet18은 model.fc 가 마지막 레이어라 통째로 교체했지만,
#     MobileNet_V3_Small은 model.classifier 가 Sequential(4개 층)이고
#     그중 마지막 index(3)가 최종 분류 레이어이므로 그 부분만 교체한다.
# ============================================================

def loadModel():
    if not os.path.exists(MODELPATH):
        raise FileNotFoundError(f"{MODELPATH}가 없습니다.")

    # [버그 수정] mapLocation -> map_location
    checkpoint = torch.load(MODELPATH, map_location=DEVICE)

    model = models.mobilenet_v3_small(weights=None)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, 2)
    # [버그 수정] loadStateDict -> load_state_dict
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(DEVICE)
    model.eval()

    classes = checkpoint.get("classes", ["normal", "overflow"])
    imageSize = checkpoint.get("image_size", IMAGESIZE)

    return model, classes, imageSize


# ============================================================
# 전역 리소스 로드 (서버 시작 시 1회)
# ============================================================

ROI = loadRoi()
MODEL, CLASSES, RESOLVEDIMAGESIZE = loadModel()

TRANSFORM = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((RESOLVEDIMAGESIZE, RESOLVEDIMAGESIZE)),
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
        self.overflowStartTime = None
        self.normalStartTime = None
        self.finalOverflow = False
        self.overflowDuration = 0.0
        self.lastSeen = time.monotonic()

        # 결과 영상 저장용
        self.videoWriter = None
        self.videoPath = None
        self.frameSize = None


Sessions: dict[str, SessionState] = {}
SessionsLock = threading.Lock()


def getSession(sessionId: str) -> SessionState:
    with SessionsLock:
        # 오래된 세션 정리 (요청 처리 김에 가볍게)
        now = time.monotonic()
        stale = [
            sid for sid, s in Sessions.items()
            if now - s.lastSeen > SESSIONIDLETIMEOUT
        ]
        for sid in stale:
            closeWriter(Sessions[sid])
            del Sessions[sid]

        if sessionId not in Sessions:
            Sessions[sessionId] = SessionState()

        state = Sessions[sessionId]
        state.lastSeen = now
        return state


# ============================================================
# 핵심 판정 로직 (기존 while 루프 내부 로직을 함수로 분리)
# ============================================================

def updateOverflowState(state: SessionState, frameOverflow: bool, clockTime: float):
    """clock_time: 이번 프레임 시각의 기준값.

    - 실시간 스트림이면 time.monotonic() (서버 도착 시각)
    - 배치(빠른 전송)이면 클라이언트가 보낸 영상 재생 시점(초)

    어느 쪽이든 "이 세션 안에서 단조 증가하는 시간축"이기만 하면
    이하 로직은 동일하게 동작합니다.
    """

    if frameOverflow:
        state.normalStartTime = None

        if state.overflowStartTime is None:
            state.overflowStartTime = clockTime

        state.overflowDuration = clockTime - state.overflowStartTime

        if state.overflowDuration >= OVERFLOWSECONDS:
            state.finalOverflow = True

    else:
        if state.overflowStartTime is None:
            state.overflowDuration = 0.0
            state.finalOverflow = False
            state.normalStartTime = None
        else:
            if state.normalStartTime is None:
                state.normalStartTime = clockTime

            normalDuration = clockTime - state.normalStartTime

            if normalDuration >= NORMALRESETSECONDS:
                state.overflowStartTime = None
                state.normalStartTime = None
                state.overflowDuration = 0.0
                state.finalOverflow = False


def drawOverlay(
    frame,
    roi,
    predictedClass,
    confidence,
    finalOverflow,
    overflowDuration,
    normalDuration,
    sessionId,
    useGrayscale=False,
):
    """기존 스크립트의 imshow용 오버레이 그리기 로직을 그대로 이식.
    useGrayscale은 화면에 현재 흑백 전처리가 적용중인지 표시만 하기 위한 용도.
    """

    resultText = "OVERFLOW" if finalOverflow else "NORMAL"
    resultColor = (0, 0, 255) if finalOverflow else (0, 255, 0)

    x1, y1, x2, y2 = int(roi["x1"]), int(roi["y1"]), int(roi["x2"]), int(roi["y2"])

    cv2.rectangle(frame, (x1, y1), (x2, y2), resultColor, 3)

    # [버그 수정] cv2.FONTHERSHEYSIMPLEX -> cv2.FONT_HERSHEY_SIMPLEX (아래 전부 동일)
    cv2.putText(
        frame, resultText, (30, 50),
        cv2.FONT_HERSHEY_SIMPLEX, 1.2, resultColor, 3,
    )

    cv2.putText(
        frame, f"Model: {predictedClass} {confidence:.2f}", (30, 85),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
    )

    durationText = f"Overflow duration: {overflowDuration:.1f}s / {OVERFLOWSECONDS:.1f}s"
    cv2.putText(
        frame, durationText, (30, 120),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
    )

    if normalDuration is not None:
        resetText = f"Normal reset: {normalDuration:.1f}s / {NORMALRESETSECONDS:.1f}s"
        cv2.putText(
            frame, resetText, (30, 155),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
        )

    cv2.putText(
        frame, sessionId, (30, 190),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
    )

    if useGrayscale:
        cv2.putText(
            frame, "GRAYSCALE INPUT", (30, 225),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 0), 2,
        )

    return frame


def getOrCreateWriter(state: "SessionState", sessionId: str, frame: np.ndarray):
    """세션의 첫 프레임이 들어오면 result/{session_id}.mp4 파일을 새로 연다."""

    if state.videoWriter is not None:
        return state.videoWriter

    height, width = frame.shape[:2]
    state.frameSize = (width, height)

    outputPath = os.path.join(RESULTDIR, f"{sessionId}.mp4")
    # [버그 수정] cv2.VideoWriterFourcc -> cv2.VideoWriter_fourcc
    fourcc = cv2.VideoWriter_fourcc(*VIDEOCODEC)

    writer = cv2.VideoWriter(outputPath, fourcc, SAVEFPS, state.frameSize)

    if not writer.isOpened():
        raise RuntimeError(f"영상 저장 파일을 열 수 없습니다: {outputPath}")

    state.videoWriter = writer
    state.videoPath = outputPath

    return writer


def closeWriter(state: "SessionState"):
    if state.videoWriter is not None:
        state.videoWriter.release()
        state.videoWriter = None


def runInference(frame: np.ndarray, useGrayscale: bool):
    """[수정] useGrayscale 인자 추가.
    True면 ROI 크롭 이미지를 흑백으로 변환한 뒤 모델에 넣는다.
    """
    roiImage = cropRoi(frame, ROI)

    if useGrayscale:
        roiImage = toGrayscale3Channel(roiImage)

    image = TRANSFORM(roiImage).unsqueeze(0).to(DEVICE)

    # [버그 수정] torch.noGrad() -> torch.no_grad()
    with torch.no_grad():
        output = MODEL(image)
        probabilities = torch.softmax(output, dim=1)[0]

    predictedIndex = torch.argmax(probabilities).item()
    confidence = probabilities[predictedIndex].item()
    predictedClass = CLASSES[predictedIndex]

    frameOverflow = (
        predictedClass == "overflow"
        and confidence >= CONFIDENCETHRESHOLD
    )

    return predictedClass, confidence, frameOverflow


# ============================================================
# FastAPI 앱
# ============================================================

app = FastAPI(title="Trash Overflow Detection API")


class PredictResponse(BaseModel):
    sessionId: str
    predictedClass: str
    confidence: float
    frameOverflow: bool          # 이번 프레임 단독 판정
    finalOverflow: bool          # 세션 누적 기준 최종 판정
    overflowDuration: float
    overflowThreshold: float = OVERFLOWSECONDS
    clockMode: str                # "client_timestamp" 또는 "server_walltime"
    grayscaleUsed: bool           # [신규] 이번 요청에 흑백 전처리가 적용됐는지
    videoPath: str | None = None  # 이번 프레임이 저장된 결과 영상 경로


# [버그 수정] responseModel= -> response_model=
@app.post("/trashflowmodel/predict", response_model=PredictResponse)
async def predict(
    sessionId: str,
    file: UploadFile = File(...),
    saveVideo: bool = True,
    timestamp: float | None = None,
    grayscale: bool | None = None,
):
    """
    timestamp: 배치(녹화 영상을 빠르게 전송하는 경우) 전용 파라미터.
               영상 재생 기준 이 프레임의 시점(초)을 넘겨주세요.
               (예: frame_index / fps). 실시간 스트림이면 생략하세요.
    grayscale: [신규] 이번 요청만 흑백 전처리 여부를 강제로 지정하고 싶을 때 사용.
               생략하면 전역 설정 USEGRAYSCALEPREPROCESS를 따릅니다.
    """
    contents = await file.read()

    npArr = np.frombuffer(contents, np.uint8)
    # [버그 수정] cv2.IMREADCOLOR -> cv2.IMREAD_COLOR
    frame = cv2.imdecode(npArr, cv2.IMREAD_COLOR)

    if frame is None:
        # [버그 수정] statusCode= -> status_code=
        raise HTTPException(status_code=400, detail="이미지를 디코딩할 수 없습니다.")

    useGrayscale = USEGRAYSCALEPREPROCESS if grayscale is None else grayscale

    predictedClass, confidence, frameOverflow = runInference(frame, useGrayscale)

    state = getSession(sessionId)

    if timestamp is not None:
        clockTime = timestamp
        clockMode = "client_timestamp"
    else:
        clockTime = time.monotonic()
        clockMode = "server_walltime"

    updateOverflowState(state, frameOverflow, clockTime)

    normalDuration = None
    if state.normalStartTime is not None:
        normalDuration = clockTime - state.normalStartTime

    if saveVideo:
        annotated = drawOverlay(
            frame.copy(),
            ROI,
            predictedClass,
            confidence,
            state.finalOverflow,
            state.overflowDuration,
            normalDuration,
            sessionId,
            useGrayscale=useGrayscale,
        )

        writer = getOrCreateWriter(state, sessionId, annotated)

        # 프레임 크기가 세션 시작 때와 다르면 강제로 맞춰서 기록 (크기 불일치 시 VideoWriter 오류 방지)
        if (annotated.shape[1], annotated.shape[0]) != state.frameSize:
            annotated = cv2.resize(annotated, state.frameSize)

        writer.write(annotated)

    if state.finalOverflow:
        # [버그 수정] EventCreate / event_service 는 이 파일 어디에도 정의되지
        # 않은 이름이라 원래 코드대로면 여기서 매번 NameError로 500 에러가 났음.
        # 실제 이벤트 적재/브로드캐스트 서비스가 별도 모듈로 있다면 그 모듈을
        # import해서 아래 TODO 부분을 교체하세요. 지금은 안전하게 로그만 남깁니다.
        logger.info(
            "finalOverflow detected - sessionId=%s confidence=%.4f "
            "(TODO: EventCreate/event_service 연동 필요)",
            sessionId, confidence,
        )
        # 예시:
        # event_data = EventCreate(
        #     cameraId=sessionId,
        #     detectedClass="overflow",
        #     isMisclassified=True,
        #     confidenceScore=confidence,
        # )
        # await event_service.handle_detection(event_data)

    return PredictResponse(
        sessionId=sessionId,
        predictedClass=predictedClass,
        confidence=confidence,
        frameOverflow=frameOverflow,
        finalOverflow=state.finalOverflow,
        overflowDuration=round(state.overflowDuration, 2),
        clockMode=clockMode,
        grayscaleUsed=useGrayscale,
        videoPath=state.videoPath if saveVideo else None,
    )


# [버그 수정] 경로 플레이스홀더를 함수 인자명(sessionId)과 일치시킴
# (기존에는 {session_id} vs sessionId 로 달라서 FastAPI 라우트 검증 단계에서
#  서버 시작 자체가 실패했음)
@app.post("/trashflowmodel/reset/{sessionId}")
def resetSession(sessionId: str):
    with SessionsLock:
        state = Sessions.pop(sessionId, None)
        if state is not None:
            closeWriter(state)
    return {"sessionId": sessionId, "reset": True}


@app.post("/trashflowmodel/finalize/{sessionId}")
def finalizeSession(sessionId: str):
    """세션 상태는 유지한 채, 저장 중인 결과 영상만 닫아서 파일을 완성시킵니다."""
    with SessionsLock:
        if sessionId not in Sessions:
            # [버그 수정] statusCode= -> status_code=
            raise HTTPException(status_code=404, detail="세션이 없습니다.")
        state = Sessions[sessionId]
        videoPath = state.videoPath
        closeWriter(state)
    return {"sessionId": sessionId, "videoPath": videoPath, "finalized": True}


@app.get("/trashflowmodel/session/{sessionId}")
def getSessionStatus(sessionId: str):
    with SessionsLock:
        if sessionId not in Sessions:
            # [버그 수정] statusCode= -> status_code=
            raise HTTPException(status_code=404, detail="세션이 없습니다.")
        state = Sessions[sessionId]
        return {
            "sessionId": sessionId,
            "finalOverflow": state.finalOverflow,
            "overflowDuration": round(state.overflowDuration, 2),
        }


@app.get("/trashflowmodel/health")
def health():
    return {
        "status": "ok",
        "device": DEVICE,
        "classes": CLASSES,
        "grayscalePreprocessDefault": USEGRAYSCALEPREPROCESS,
    }