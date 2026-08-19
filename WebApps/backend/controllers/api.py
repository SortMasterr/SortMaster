import asyncio
from datetime import datetime, timezone

import cv2
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)
from fastapi.responses import StreamingResponse

from schemas.detection import (
    DetectionStart,
    DetectionStartResponse,
    DetectionStop,
)
from schemas.event import (
    CameraId,
    Event,
    EventCategory,
    EventCreate,
)
from schemas.mode import (
    Mode,
    ModeResponse,
    ModeUpdate,
)
from schemas.statistics import Statistics
from services.detectionService import detectionService
from services.errors import (
    CameraUnavailableError,
    EmptyRecordingError,
    RecordingCameraMismatchError,
    RecordingConflictError,
    RecordingNotFoundError,
)
from services.eventService import eventService
from services.modeService import modeService
from services.webSocketManager import (
    webSocketManager,
)
from streaming.cameraManager import (
    cameraManagers,
)


router = APIRouter(
    prefix="/api",
    tags=["events"],
)


@router.get(
    "/events",
    response_model=list[Event],
)
async def getEvents(
    fromDate: datetime | None = Query(
        default=None,
        alias="from",
    ),
    toDate: datetime | None = Query(
        default=None,
        alias="to",
    ),
) -> list[Event]:
    return await eventService.getEvents(
        fromDate=fromDate,
        toDate=toDate,
    )


@router.get(
    "/events/{id}",
    response_model=Event,
)
async def getEventById(
    id: str,
) -> Event:
    event = await eventService.getEventById(
        id
    )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "이벤트를 찾을 수 없습니다."
            ),
        )

    return event


@router.post(
    "/events",
    response_model=Event | None,
)
async def createEvent(
    eventCreate: EventCreate,
) -> Event | None:
    creationResult = (
        await eventService.createEventWithStatus(
            eventCreate
        )
    )

    if creationResult.created:
        await _broadcastIfManageMode(
            creationResult.event
        )

    return creationResult.event


async def _broadcastIfManageMode(
    event: Event | None,
) -> None:
    currentMode = modeService.getMode().mode

    if event is None or currentMode != Mode.manage:
        return

    if (
        event.eventCategory
        == EventCategory.MISCLASSIFICATION
    ):
        payload = {
            "eventType": (
                "MISCLASSIFICATION_DETECTED"
            ),
            "cameraId": event.cameraId.value,
            "timestamp": (
                event.timestamp.isoformat()
            ),
            "isMisclassified": (
                event.isMisclassified
            ),
        }
    else:
        payload = {
            "eventType": (
                "BIN_OVERFLOW_DETECTED"
            ),
            "cameraId": event.cameraId.value,
            "timestamp": (
                event.timestamp.isoformat()
            ),
        }

    await webSocketManager.broadcast(payload)


@router.post(
    "/detection/start",
    response_model=DetectionStartResponse,
)
async def startDetection(
    detectionStart: DetectionStart,
) -> DetectionStartResponse:
    try:
        recordingId = (
            await detectionService.startDetection(
                detectionStart.cameraId
            )
        )
    except CameraUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    return DetectionStartResponse(
        recordingId=recordingId
    )


@router.post(
    "/detection/stop",
    response_model=Event | None,
)
async def stopDetection(
    detectionStop: DetectionStop,
) -> Event | None:
    try:
        creationResult = (
            await detectionService.stopDetectionWithStatus(
                recordingId=detectionStop.recordingId,
                cameraId=detectionStop.cameraId,
                eventCategory=detectionStop.eventCategory,
                detectionId=detectionStop.detectionId,
                trackingId=detectionStop.trackingId,
                detectedClass=detectionStop.detectedClass,
                binId=detectionStop.binId,
                binType=detectionStop.binType,
                isMisclassified=detectionStop.isMisclassified,
                confidenceScore=detectionStop.confidenceScore,
                overflowDuration=detectionStop.overflowDuration,
                overflowThreshold=detectionStop.overflowThreshold,
                modelVersion=detectionStop.modelVersion,
            )
        )
    except RecordingNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
    except (
        EmptyRecordingError,
        RecordingCameraMismatchError,
        RecordingConflictError,
    ) as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    if creationResult.created:
        await _broadcastIfManageMode(
            creationResult.event
        )

    return creationResult.event


@router.get(
    "/statistics",
    response_model=Statistics,
)
async def getStatistics(
    fromDate: datetime | None = Query(
        default=None,
        alias="from",
    ),
    toDate: datetime | None = Query(
        default=None,
        alias="to",
    ),
) -> Statistics:
    return await eventService.getStatistics(
        fromDate=fromDate,
        toDate=toDate,
    )


@router.post(
    "/mode",
    response_model=ModeResponse,
)
async def updateMode(
    modeUpdate: ModeUpdate,
) -> ModeResponse:
    modeResponse = (
        modeService.updateMode(
            modeUpdate
        )
    )

    await webSocketManager.broadcast(
        {
            "eventType": "MODE_CHANGED",
            "mode": (
                modeResponse.mode.value
            ),
            "timestamp": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }
    )

    return modeResponse


async def generateMjpegFrames(
    cameraManager,
):
    while True:
        frame = (
            await cameraManager.readFrame()
        )

        if frame is None:
            await asyncio.sleep(0.05)
            continue

        encoded, buffer = (
            await asyncio.to_thread(
                cv2.imencode,
                ".jpg",
                frame,
            )
        )

        if not encoded:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: "
            b"image/jpeg\r\n\r\n"
            + buffer.tobytes()
            + b"\r\n"
        )


@router.get(
    "/stream/{cameraId}",
)
async def streamCamera(
    cameraId: CameraId,
) -> StreamingResponse:
    cameraManager = cameraManagers[
        cameraId.value
    ]

    try:
        await cameraManager.start()
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    return StreamingResponse(
        generateMjpegFrames(
            cameraManager
        ),
        media_type=(
            "multipart/x-mixed-replace; "
            "boundary=frame"
        ),
    )
