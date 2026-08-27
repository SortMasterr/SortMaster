import logging
from datetime import datetime, timezone

from repositories.eventRepository import (
    EventRepository,
    eventRepository,
)
from schemas.event import Event
from schemas.visitClip import VisitClip
from services.mediaService import MediaService, mediaService


logger = logging.getLogger(__name__)
previewDurationSeconds = 5.0


def _normalizeToUtc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


class EventMediaService:
    def __init__(
        self,
        eventRepositoryInstance: EventRepository,
        mediaServiceInstance: MediaService,
    ):
        self.eventRepository = eventRepositoryInstance
        self.mediaService = mediaServiceInstance

    async def attachPreviewFromVisitClip(
        self,
        event: Event,
        visitClip: VisitClip,
        eventTimestamp: datetime | None = None,
    ) -> Event:
        if event.imageFileId is not None:
            return event

        clipStartedAt = _normalizeToUtc(
            visitClip.startedAt
        )
        clipEndedAt = _normalizeToUtc(
            visitClip.endedAt
        )
        targetTimestamp = _normalizeToUtc(
            eventTimestamp or event.timestamp
        )
        clipDurationSeconds = max(
            0.0,
            (clipEndedAt - clipStartedAt).total_seconds(),
        )
        previewEndSeconds = min(
            clipDurationSeconds,
            max(
                0.2,
                (targetTimestamp - clipStartedAt).total_seconds(),
            ),
        )
        previewStartSeconds = max(
            0.0,
            previewEndSeconds - previewDurationSeconds,
        )

        imageFileId = None

        try:
            imageFileId = (
                await self.mediaService.saveStoredClipSegmentAsGif(
                    visitClip.imageFileId,
                    visitClip.cameraId,
                    event.timestamp,
                    previewStartSeconds,
                    previewEndSeconds,
                )
            )

            if imageFileId is None:
                logger.warning(
                    "[eventMediaService] 방문 클립 원본을 찾지 못함: eventId=%s",
                    event.eventId,
                )
                return event

            updated = await self.eventRepository.updateImageFileIdIfMissing(
                event.eventId,
                imageFileId,
            )

            if not updated:
                await self.mediaService.deleteClip(
                    imageFileId,
                    visitClip.cameraId,
                )
                return event

            return event.model_copy(
                update={"imageFileId": imageFileId}
            )
        except Exception:
            if imageFileId is not None:
                try:
                    await self.mediaService.deleteClip(
                        imageFileId,
                        visitClip.cameraId,
                    )
                except Exception:
                    logger.exception(
                        "[eventMediaService] 파생 GIF 보상 삭제 실패: fileId=%s",
                        imageFileId,
                    )

            logger.exception(
                "[eventMediaService] DB 방문 영상에서 이벤트 GIF 생성 실패: eventId=%s",
                event.eventId,
            )
            return event


eventMediaService = EventMediaService(
    eventRepository,
    mediaService,
)
