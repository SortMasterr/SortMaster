from datetime import datetime, timezone

from schemas.event import (
    ActionTaken,
    CameraId,
    DetectedClass,
    Event,
)


class EventRepository:
    def __init__(self):
        self.events = [
            Event(
                eventId="event-001",
                timestamp=datetime.now(timezone.utc),
                cameraId=CameraId.ELEV01,
                detectedClass=DetectedClass.PLASTIC,
                isMisclassified=True,
                confidenceScore=0.91,
                actionTaken=(
                    ActionTaken.LIGHT_AND_SOUND
                ),
                imageFileId=None,
                notes="플라스틱 오분류 Mock 이벤트",
            ),
            Event(
                eventId="event-002",
                timestamp=datetime.now(timezone.utc),
                cameraId=CameraId.ELEV02,
                detectedClass=DetectedClass.PAPER,
                isMisclassified=True,
                confidenceScore=0.87,
                actionTaken=(
                    ActionTaken.LIGHT_AND_SOUND
                ),
                imageFileId=None,
                notes="종이 오분류 Mock 이벤트",
            ),
        ]

    def save(
        self,
        event: Event,
    ) -> Event:
        self.events.append(event)

        return event

    def findById(
        self,
        eventId: str,
    ) -> Event | None:
        for event in self.events:
            if event.eventId == eventId:
                return event

        return None

    def findAll(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> list[Event]:
        normalizedFromDate = (
            self.normalizeDateTime(fromDate)
        )

        normalizedToDate = (
            self.normalizeDateTime(toDate)
        )

        filteredEvents = self.events

        if normalizedFromDate is not None:
            filteredEvents = [
                event
                for event in filteredEvents
                if (
                    event.timestamp
                    >= normalizedFromDate
                )
            ]

        if normalizedToDate is not None:
            filteredEvents = [
                event
                for event in filteredEvents
                if (
                    event.timestamp
                    <= normalizedToDate
                )
            ]

        return sorted(
            filteredEvents,
            key=lambda event: event.timestamp,
            reverse=True,
        )

    def countByDetectedClass(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> dict[DetectedClass, int]:
        events = self.findAll(
            fromDate=fromDate,
            toDate=toDate,
        )

        counts = {
            detectedClass: 0
            for detectedClass in DetectedClass
        }

        for event in events:
            counts[event.detectedClass] += 1

        return counts

    def normalizeDateTime(
        self,
        dateTime: datetime | None,
    ) -> datetime | None:
        if (
            dateTime is not None
            and dateTime.tzinfo is None
        ):
            return dateTime.replace(
                tzinfo=timezone.utc
            )

        return dateTime


eventRepository = EventRepository()