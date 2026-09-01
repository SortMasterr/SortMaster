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
from services.eventMediaService import eventMediaService
from services.modeService import modeService
from services.visitClipService import visitClipService


@dataclass(frozen=True)
class EventCreationResult:
    event: Event | None
    created: bool


# models/trashdetect/tracking2.py가 실제로 내보내는 값 — 모델이 plastic/can을 구분 못 해서
# "recyclables" 하나로 합쳐 내며 내부 API 값도 같은 이름을 사용한다.
# detectedClass/binId 둘 다 이 값 체계를 그대로 씀(스크립트 내 TRASH_TYPE_MAP/BIN_TYPE_MAP과 동일).
_aiClassToDetectedClass: dict[str, DetectedClass] = {
    "normal": DetectedClass.NORMAL,
    "paper": DetectedClass.PAPER,
    "recyclables": DetectedClass.RECYCLABLES,
    "coffeecup": DetectedClass.COFFEE_CUP,
}

_aiClassToBinType: dict[str, BinType] = {
    "normal": BinType.NORMAL,
    "paper": BinType.PAPER,
    "recyclables": BinType.RECYCLABLES,
    "coffeecup": BinType.COFFEE_CUP,
}

# 물리 통 ID 문자열 자체는 CTO 승인 불필요(decisionLog.md의 SIDE 통 ID 선례) —
# debug/db/seedTestEvents.py와 동일한 명명 재사용
_binTypeToBinId: dict[BinType, str] = {
    BinType.NORMAL: "BIN-GENERAL",
    BinType.PAPER: "BIN-PAPER",
    BinType.RECYCLABLES: "BIN-PLASTIC-CAN",
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

    async def acknowledgeEvent(
        self,
        eventId: str,
    ) -> Event | None:
        return await self.repository.acknowledgeById(
            eventId,
            datetime.now(timezone.utc),
        )

    async def acknowledgeEvents(
        self,
        eventIds: list[str],
    ) -> list[Event]:
        return await self.repository.acknowledgeMany(
            eventIds,
            datetime.now(timezone.utc),
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
            # GPU가 스스로 판정을 못 내렸다고 알려온 것 — trackEnded(확정 실패)와
            # 성격이 같아서 재학습 후보 분류에도 동일하게 반영한다(architecture.md의
            # "재학습용 미확정 방문 캡처" 참고).
            await visitClipService.registerTrackEnded(aiEvent.trackId)
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

        result = await self.createEventWithStatus(eventCreate)

        # correct 판정은 EVENT를 저장하지 않지만(위 _createEventWithStatus 참고), 그래도
        # 방문 자체는 "정상적으로 해결됨"으로 표시해야 재학습 후보(미확정 방문)로 잘못
        # 잡히지 않는다 — eventId=None으로 호출해도 resolved 표시는 그대로 된다.
        resolvedEventId = result.event.eventId if result.event is not None else None
        eventTimestamp = _parseAiTimestamp(
            aiEvent.timestamp,
            result.event.timestamp if result.event is not None else None,
        )
        visitClip = await visitClipService.registerAiDisposalResolution(
            aiEvent.trackId,
            resolvedEventId,
            cameraId,
            eventTimestamp,
        )

        if visitClip is not None and result.event is not None:
            updatedEvent = await eventMediaService.attachPreviewFromVisitClip(
                result.event,
                visitClip,
                eventTimestamp,
            )
            result = EventCreationResult(
                event=updatedEvent,
                created=result.created,
            )

        return result

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
            acknowledgedAt=None,
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


def _parseAiTimestamp(
    value: str,
    fallback: datetime | None,
) -> datetime:
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
    except ValueError:
        logger.warning(
            "[eventService] AI 이벤트 timestamp 형식 오류, 백엔드 시각 사용: %r",
            value,
        )
        return fallback or datetime.now(timezone.utc)
