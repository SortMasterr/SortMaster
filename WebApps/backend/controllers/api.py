import asyncio
from datetime import datetime
from typing import Literal

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
    ModeResponse,
    ModeUpdate,
)
from schemas.statistics import Statistics
from services.eventService import eventService
from services.modeService import modeService
from streaming.cameraManager import cameraManagers


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
    return eventService.createEvent(
        eventCreate
    )


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
    return modeService.updateMode(
        modeUpdate
    )


async def generateMjpegFrames(cameraManager):
    while True:
        frame = await cameraManager.readFrame()

        if frame is None:
            await asyncio.sleep(0.05)
            continue

        encoded, buffer = await asyncio.to_thread(
            cv2.imencode,
            ".jpg",
            frame,
        )

        if not encoded:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + buffer.tobytes()
            + b"\r\n"
        )


@router.get("/stream/{cameraId}")
async def streamCamera(
    cameraId: CameraId,
    role: Literal["top", "side"] = "top",
) -> StreamingResponse:
    cameraManager = cameraManagers[role]

    try:
        await cameraManager.start()
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        )

    return StreamingResponse(
        generateMjpegFrames(cameraManager),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )