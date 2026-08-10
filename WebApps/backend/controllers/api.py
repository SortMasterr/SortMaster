from datetime import datetime

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from schemas.event import Event, EventCreate
from services.event_service import eventService


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
    event = eventService.getEventById(id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="이벤트를 찾을 수 없습니다.",
        )

    return event


@router.post(
    "/events",
    response_model=Event | None,
)
async def createEvent(
    eventCreate: EventCreate,
) -> Event | None:
    return eventService.createEvent(eventCreate)