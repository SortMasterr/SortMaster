import asyncio
import logging
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
from schemas.aiDisposalEvent import AiDisposalEvent
from schemas.event import (
    ActionTaken,
    BinType,
    CameraId,
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


# models/trashdetect/tracking2.py가 실제로 내보내는 값 — 모델이 plastic/can을 구분 못 해서
# "recyclables" 하나로 합쳐 나옴(DetectedClass.PLASTIC_CAN과 1:1 대응, decisionLog.md 참고).
# detectedClass/binId 둘 다 이 값 체계를 그대로 씀(스크립트 내 TRASH_TYPE_MAP/BIN_TYPE_MAP과 동일).
_aiClassToDetectedClass: dict[str, DetectedClass] = {
    "normal": DetectedClass.GENERAL,
    "paper": DetectedClass.PAPER,
    "recyclables": DetectedClass.PLASTIC_CAN,
    "coffeecup": DetectedClass.COFFEE_CUP,
}

_aiClassToBinType: dict[str, BinType] = {
    "normal": BinType.GENERAL,
    "paper": BinType.PAPER,
    "recyclables": BinType.PLASTIC_CAN,
    "coffeecup": BinType.COFFEE_CUP,
}

# 물리 통 ID 문자열 자체는 CTO 승인 불필요(decisionLog.md의 SIDE bin-side-01 선례) —
# debug/db/seedTestEvents.py와 동일한 명명 재사용
_binTypeToBinId: dict[BinType, str] = {
    BinType.GENERAL: "BIN-GENERAL",
    BinType.PAPER: "BIN-PAPER",
    BinType.PLASTIC_CAN: "BIN-PLASTIC-CAN",
    BinType.COFFEE_CUP: "BIN-COFFEE-CUP",
}

# tracking2.py는 CAMERA_ID를 "CAM-01"로 하드코딩해서 보냄 — 투기(misclassification)는
# TOP 카메라 단독 확정(architecture.md)이라 지금은 이거 하나만 받으면 됨
_aiCameraIdToCameraId: dict[str, CameraId] = {
    "CAM-01": CameraId.ELEVTOP,
}

logger = logging.getLogger(__name__)


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

    async def createEventFromAiDisposal(
        self,
        aiEvent: AiDisposalEvent,
    ) -> EventCreationResult:
        """tracking2.py가 투척 완료 시 보내는 결과를 EventCreate로 변환해 저장한다.

        cameraId/detectedClass가 우리 값 체계에 없으면(스크립트 쪽 변경/오류로 예상 못 한
        값이 온 경우) 500을 내는 대신 이벤트 미생성으로 처리하고 로그만 남긴다 — 우리가
        제어하지 않는 외부 스크립트가 보내는 데이터라 방어적으로 처리.
        """
        cameraId = _aiCameraIdToCameraId.get(aiEvent.cameraId)
        detectedClass = _aiClassToDetectedClass.get(aiEvent.detectedClass)
        binType = _aiClassToBinType.get(aiEvent.binId)

        if cameraId is None or detectedClass is None or binType is None:
            logger.warning(
                "[eventService] AI 투기 이벤트 무시(값 매핑 실패): "
                f"cameraId={aiEvent.cameraId!r}, "
                f"detectedClass={aiEvent.detectedClass!r}, "
                f"binId={aiEvent.binId!r}"
            )
            return EventCreationResult(event=None, created=False)

        if aiEvent.result == "correct":
            isMisclassified = False
        elif aiEvent.result == "incorrect":
            isMisclassified = True
        else:
            logger.warning(
                "[eventService] AI 투기 이벤트 무시(판정 결과 unknown): "
                f"eventId={aiEvent.eventId}"
            )
            return EventCreationResult(event=None, created=False)

        eventCreate = EventCreate(
            cameraId=cameraId,
            eventCategory=EventCategory.MISCLASSIFICATION,
            detectionId=aiEvent.eventId,
            trackingId=aiEvent.trackId,
            detectedClass=detectedClass,
            binId=_binTypeToBinId[binType],
            binType=binType,
            isMisclassified=isMisclassified,
            # tracking2.py는 최종 판정에 쓴 confidence를 응답에 노출하지 않아서(내부
            # class_scores만 누적) 고정값 사용 — 값 자체가 스코어링에 쓰이진 않고 스키마
            # 필수값이라 채워두는 것뿐(아래 TBD).
            confidenceScore=1.0,
            modelVersion="yolo26-tracking2",
        )

        return await self.createEventWithStatus(eventCreate)

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
