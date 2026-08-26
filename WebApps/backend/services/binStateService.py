"""BIN_STATES 비즈니스 로직 — `NORMAL`→`FULL` 전환 순간에만 overflow EVENT를 생성한다.

`Docs/ERD.md`의 BIN_STATES 설계를 그대로 구현: 상태 자체는 `binId`당 최신 1행만
upsert로 유지하고(binStateRepository), 전환 이력은 EVENT(eventService)가 담당한다.
`FULL`→`NORMAL` 복귀는 EVENT를 만들지 않고 `activeOverflowEventId`만 초기화한다.
"""
import asyncio
from datetime import datetime, timezone

from repositories.binStateRepository import (
    BinStateRepository,
    binStateRepository,
)
from schemas.binState import BinCurrentState, BinState, BinStateUpdate
from schemas.event import CameraId, EventCategory, EventCreate
from services.eventService import (
    EventCreationResult,
    EventService,
    eventService,
)
from services.collectionTaskService import (
    CollectionTaskService,
    collectionTaskService,
)


class BinStateService:
    def __init__(
        self,
        repository: BinStateRepository,
        eventServiceInstance: EventService,
        collectionTaskServiceInstance: CollectionTaskService | None = None,
    ):
        self.repository = repository
        self.eventService = eventServiceInstance
        self.collectionTaskService = collectionTaskServiceInstance
        self.transitionLock = asyncio.Lock()

    async def getBinStates(self) -> list[BinState]:
        return await self.repository.findAll()

    async def getBinState(self, binId: str) -> BinState | None:
        return await self.repository.findById(binId)

    async def applyUpdate(
        self,
        update: BinStateUpdate,
    ) -> tuple[BinState, EventCreationResult | None]:
        async with self.transitionLock:
            return await self._applyUpdate(update)

    async def _applyUpdate(
        self,
        update: BinStateUpdate,
    ) -> tuple[BinState, EventCreationResult | None]:
        previous = await self.repository.findById(update.binId)
        currentTime = datetime.now(timezone.utc)

        previousState = (
            previous.currentState if previous is not None else None
        )
        stateChanged = previousState != update.currentState

        transitionedToFull = (
            update.currentState == BinCurrentState.FULL
            and previousState != BinCurrentState.FULL
        )
        transitionedToNormal = (
            update.currentState == BinCurrentState.NORMAL
            and previousState == BinCurrentState.FULL
        )

        activeOverflowEventId = (
            previous.activeOverflowEventId
            if previous is not None
            else None
        )
        eventResult: EventCreationResult | None = None

        if transitionedToFull:
            eventCreate = EventCreate(
                cameraId=CameraId.ELEVSIDE,
                eventCategory=EventCategory.OVERFLOW,
                detectionId=update.detectionId,
                binId=update.binId,
                binType=update.binType,
                overflowDuration=update.overflowDuration,
                overflowThreshold=update.overflowThreshold,
                modelVersion=update.modelVersion,
            )

            eventResult = await self.eventService.createEventWithStatus(
                eventCreate
            )

            if eventResult.event is not None:
                activeOverflowEventId = eventResult.event.eventId
                if self.collectionTaskService is not None:
                    await self.collectionTaskService.createForOverflow(
                        eventResult.event
                    )
        elif transitionedToNormal:
            activeOverflowEventId = None

        lastChangedAt = (
            currentTime
            if stateChanged or previous is None
            else previous.lastChangedAt
        )

        binState = BinState(
            binId=update.binId,
            cameraId=update.cameraId,
            binType=update.binType,
            sessionId=update.sessionId,
            currentState=update.currentState,
            confidenceScore=update.confidenceScore,
            overflowDuration=update.overflowDuration,
            lastChangedAt=lastChangedAt,
            activeOverflowEventId=activeOverflowEventId,
        )

        savedBinState = await self.repository.upsert(binState)

        return savedBinState, eventResult


binStateService = BinStateService(
    binStateRepository,
    eventService,
    collectionTaskService,
)
