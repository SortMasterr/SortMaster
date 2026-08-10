from datetime import datetime, timedelta, timezone
from uuid import uuid4

from repositories.event_repository import (
    EventRepository,
    eventRepository,
)
from schemas.event import (
    ActionTaken,
    Event,
    EventCreate,
)


class EventService:
    def __init__(
        self,
        repository: EventRepository,
    ):
        self.repository = repository
        self.cooldownSeconds = 5
        self.lastEventTimes = {}

    def getEvents(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> list[Event]:
        return self.repository.findAll(
            fromDate=fromDate,
            toDate=toDate,
        )
        
    def getEventById(
        self,
        eventId: str,
    ) -> Event | None:
        return self.repository.findById(eventId)
        

    def createEvent(
        self,
        eventCreate: EventCreate,
    ) -> Event | None:
        if not eventCreate.isMisclassified:
            return None

        currentTime = datetime.now(timezone.utc)

        cooldownKey = (
            eventCreate.cameraId.value,
            eventCreate.detectedClass.value,
        )

        lastEventTime = self.lastEventTimes.get(
            cooldownKey
        )

        if (
            lastEventTime is not None
            and currentTime - lastEventTime
            < timedelta(seconds=self.cooldownSeconds)
        ):
            return None

        event = Event(
            eventId=str(uuid4()),
            timestamp=currentTime,
            cameraId=eventCreate.cameraId,
            detectedClass=eventCreate.detectedClass,
            isMisclassified=(
                eventCreate.isMisclassified
            ),
            confidenceScore=(
                eventCreate.confidenceScore
            ),
            actionTaken=(
                ActionTaken.LIGHT_AND_SOUND
            ),
            imageFileId=None,
            notes=None,
        )

        savedEvent = self.repository.save(event)

        self.lastEventTimes[cooldownKey] = (
            currentTime
        )

        return savedEvent


eventService = EventService(eventRepository)