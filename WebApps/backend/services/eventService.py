from datetime import (
    datetime,
    timedelta,
    timezone,
)
from uuid import uuid4

from repositories.eventRepository import (
    EventRepository,
    eventRepository,
)
from schemas.event import (
    ActionTaken,
    DetectedClass,
    Event,
    EventCategory,
    EventCreate,
)
from schemas.mode import Mode
from schemas.statistics import Statistics
from services.modeService import modeService


class EventService:
    def __init__(
        self,
        repository: EventRepository,
    ):
        self.repository = repository
        self.cooldownSeconds = 5
        self.lastEventTimes = {}

    async def getEvents(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> list[Event]:
        return await self.repository.findAll(
            fromDate=fromDate,
            toDate=toDate,
        )

    async def getEventById(
        self,
        eventId: str,
    ) -> Event | None:
        return await self.repository.findById(
            eventId
        )

    async def getStatistics(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> Statistics:
        countsByClass = (
            await self.repository.countByDetectedClass(
                fromDate=fromDate,
                toDate=toDate,
            )
        )

        detectedClasses = list(
            DetectedClass
        )

        return Statistics(
            labels=detectedClasses,
            counts=[
                countsByClass[
                    detectedClass
                ]
                for detectedClass
                in detectedClasses
            ],
        )

    async def createEvent(
        self,
        eventCreate: EventCreate,
    ) -> Event | None:
        if (
            eventCreate.eventCategory
            == EventCategory.MISCLASSIFICATION
            and not eventCreate.isMisclassified
        ):
            return None

        currentTime = datetime.now(
            timezone.utc
        )

        cooldownKey = self._buildCooldownKey(
            eventCreate
        )

        lastEventTime = (
            self.lastEventTimes.get(
                cooldownKey
            )
        )

        if (
            lastEventTime is not None
            and (
                currentTime - lastEventTime
                < timedelta(
                    seconds=(
                        self.cooldownSeconds
                    )
                )
            )
        ):
            return None

        currentMode = (
            modeService.getMode().mode
        )

        if currentMode == Mode.manage:
            actionTaken = (
                ActionTaken.LIGHT_AND_SOUND
            )
        else:
            actionTaken = ActionTaken.NONE

        event = Event(
            eventId=str(uuid4()),
            timestamp=currentTime,
            cameraId=eventCreate.cameraId,
            eventCategory=(
                eventCreate.eventCategory
            ),
            detectedClass=(
                eventCreate.detectedClass
            ),
            isMisclassified=(
                eventCreate.isMisclassified
            ),
            confidenceScore=(
                eventCreate.confidenceScore
            ),
            actionTaken=actionTaken,
            imageFileId=(
                eventCreate.imageFileId
            ),
            notes=None,
        )

        savedEvent = (
            await self.repository.save(
                event
            )
        )

        self.lastEventTimes[
            cooldownKey
        ] = currentTime

        return savedEvent

    def _buildCooldownKey(
        self,
        eventCreate: EventCreate,
    ):
        if (
            eventCreate.eventCategory
            == EventCategory.MISCLASSIFICATION
        ):
            return (
                eventCreate.cameraId.value,
                eventCreate.detectedClass.value,
            )

        return (
            eventCreate.cameraId.value,
            "overflow",
        )


eventService = EventService(
    eventRepository
)
