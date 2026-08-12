import asyncio
from datetime import datetime, timezone

import cv2
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)
from fastapi.responses import StreamingResponse

from schemas.event import (
    CameraId,
    Event,
    EventCreate,
)
from schemas.mode import (
    Mode,
    ModeResponse,
    ModeUpdate,
)
from schemas.statistics import Statistics
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
    return eventService.getEvents(
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
    event = eventService.getEventById(
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
    createdEvent = (
        eventService.createEvent(
            eventCreate
        )
    )

    currentMode = (
        modeService.getMode().mode
    )

    if (
        createdEvent is not None
        and currentMode == Mode.manage
    ):
        await webSocketManager.broadcast(
            {
                "eventType": (
                    "MISCLASSIFICATION_DETECTED"
                ),
                "cameraId": (
                    createdEvent.cameraId.value
                ),
                "timestamp": (
                    createdEvent.timestamp
                    .isoformat()
                ),
                "isMisclassified": (
                    createdEvent
                    .isMisclassified
                ),
            }
        )

    return createdEvent


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
    return eventService.getStatistics(
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