import asyncio
from dataclasses import dataclass
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


@dataclass(frozen=True)
class EventCreationResult:
    event: Event | None
    created: bool


class EventService:
    def __init__(
        self,
        repository: EventRepository,
    ):
        self.repository = repository
        self.cooldownSeconds = 5
        self.lastEventTimes = {}
        self.creationLock = asyncio.Lock()

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
        (
            countsByClass,
            countsByCategory,
        ) = await self.repository.getStatisticsCounts(
                fromDate=fromDate,
                toDate=toDate,
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
            totalEventCount=sum(countsByCategory.values()),
            misclassificationCount=countsByCategory[
                EventCategory.MISCLASSIFICATION
            ],
            overflowCount=countsByCategory[
                EventCategory.OVERFLOW
            ],
        )

    async def createEvent(
        self,
        eventCreate: EventCreate,
    ) -> Event | None:
        result = await self.createEventWithStatus(eventCreate)
        return result.event

    async def createEventWithStatus(
        self,
        eventCreate: EventCreate,
    ) -> EventCreationResult:
        async with self.creationLock:
            return await self._createEventWithStatus(eventCreate)

    async def _createEventWithStatus(
        self,
        eventCreate: EventCreate,
    ) -> EventCreationResult:
        existingEvent = await self.repository.findByDetectionId(
            eventCreate.detectionId
        )

        if existingEvent is not None:
            return EventCreationResult(
                event=existingEvent,
                created=False,
            )

        if (
            eventCreate.eventCategory
            == EventCategory.MISCLASSIFICATION
            and not eventCreate.isMisclassified
        ):
            return EventCreationResult(
                event=None,
                created=False,
            )

        currentTime = datetime.now(
            timezone.utc
        )

        cooldownKey = None

        if eventCreate.eventCategory == EventCategory.MISCLASSIFICATION:
            cooldownKey = self._buildCooldownKey(eventCreate)
            lastEventTime = self.lastEventTimes.get(cooldownKey)

            if (
                lastEventTime is not None
                and currentTime - lastEventTime
                < timedelta(seconds=self.cooldownSeconds)
            ):
                return EventCreationResult(
                    event=None,
                    created=False,
                )

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
            detectionId=eventCreate.detectionId,
            trackingId=eventCreate.trackingId,
            detectedClass=(
                eventCreate.detectedClass
            ),
            binId=eventCreate.binId,
            binType=eventCreate.binType,
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
            overflowDuration=eventCreate.overflowDuration,
            overflowThreshold=eventCreate.overflowThreshold,
            modelVersion=eventCreate.modelVersion,
            notes=None,
        )

        savedEvent = (
            await self.repository.save(
                event
            )
        )

        created = savedEvent.eventId == event.eventId

        if cooldownKey is not None and created:
            self.lastEventTimes[cooldownKey] = currentTime

        return EventCreationResult(
            event=savedEvent,
            created=created,
        )

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
