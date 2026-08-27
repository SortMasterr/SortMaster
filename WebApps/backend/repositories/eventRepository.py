import logging
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from repositories.mongoClient import getMongoDb
from schemas.event import (
    ActionTaken,
    BinType,
    CameraId,
    DetectedClass,
    Event,
    EventCategory,
)


logger = logging.getLogger(__name__)

_legacyDetectedClassValues = {
    "general": DetectedClass.NORMAL,
    "plasticCan": DetectedClass.RECYCLABLES,
}
_legacyBinTypeValues = {
    "general": BinType.NORMAL,
    "plasticCan": BinType.RECYCLABLES,
}


class EventRepository:
    def __init__(self):
        self.indexesReady = False

    @property
    def collection(self):
        return getMongoDb()["events"]

    def _toDocument(self, event: Event) -> dict:
        document = event.model_dump()
        document["cameraId"] = event.cameraId.value
        document["eventCategory"] = event.eventCategory.value
        document["detectedClass"] = (
            event.detectedClass.value
            if event.detectedClass is not None
            else None
        )
        document["actionTaken"] = event.actionTaken.value
        document["binType"] = event.binType.value

        return document

    def _fromDocument(self, document: dict) -> Event:
        return Event(
            eventId=document["eventId"],
            timestamp=self.normalizeDateTime(
                document["timestamp"]
            ),
            cameraId=CameraId(document["cameraId"]),
            eventCategory=EventCategory(document["eventCategory"]),
            detectionId=document["detectionId"],
            trackingId=document.get("trackingId"),
            detectedClass=(
                _parseDetectedClass(document["detectedClass"])
                if document.get("detectedClass") is not None
                else None
            ),
            binId=document["binId"],
            binType=_parseBinType(document["binType"]),
            isMisclassified=document.get("isMisclassified"),
            confidenceScore=document.get("confidenceScore"),
            actionTaken=ActionTaken(document["actionTaken"]),
            imageFileId=document.get("imageFileId"),
            overflowDuration=document.get("overflowDuration"),
            overflowThreshold=document.get("overflowThreshold"),
            modelVersion=document["modelVersion"],
            notes=document.get("notes"),
        )

    def _tryFromDocument(
        self,
        document: dict,
    ) -> Event | None:
        try:
            return self._fromDocument(document)
        except (KeyError, TypeError, ValueError) as error:
            logger.warning(
                'Skipping incompatible event document %r: %s',
                document.get('_id'),
                error,
            )
            return None

    async def ensureIndexes(self) -> None:
        if self.indexesReady:
            return

        await self.collection.create_index(
            "eventId",
            unique=True,
        )
        await self.collection.create_index(
            "detectionId",
            unique=True,
            sparse=True,
        )
        await self.collection.create_index(
            [("timestamp", -1)],
        )
        self.indexesReady = True

    async def save(
        self,
        event: Event,
    ) -> Event:
        await self.ensureIndexes()

        try:
            await self.collection.insert_one(
                self._toDocument(event)
            )
        except DuplicateKeyError:
            existingEvent = await self.findByDetectionId(
                event.detectionId
            )

            if existingEvent is None:
                raise

            return existingEvent

        return event

    async def findByDetectionId(
        self,
        detectionId: str,
    ) -> Event | None:
        document = await self.collection.find_one(
            {"detectionId": detectionId}
        )

        return (
            self._tryFromDocument(document)
            if document is not None
            else None
        )

    async def findById(
        self,
        eventId: str,
    ) -> Event | None:
        document = await self.collection.find_one(
            {"eventId": eventId}
        )

        return (
            self._tryFromDocument(document)
            if document is not None
            else None
        )

    async def findAll(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> list[Event]:
        query = self._buildDateQuery(
            fromDate=fromDate,
            toDate=toDate,
        )

        cursor = self.collection.find(query).sort(
            "timestamp", -1
        )

        events = []

        async for document in cursor:
            event = self._tryFromDocument(document)

            if event is not None:
                events.append(event)

        return events

    async def countByDetectedClass(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> dict[DetectedClass, int]:
        query = self._buildDateQuery(
            fromDate=fromDate,
            toDate=toDate,
        )

        pipeline = []

        if query:
            pipeline.append({"$match": query})

        pipeline.append(
            {
                "$group": {
                    "_id": "$detectedClass",
                    "count": {"$sum": 1},
                }
            }
        )

        counts = {
            detectedClass: 0
            for detectedClass in DetectedClass
        }

        async for result in self.collection.aggregate(
            pipeline
        ):
            groupId = result["_id"]

            if groupId is not None:
                try:
                    detectedClass = _parseDetectedClass(groupId)
                except ValueError:
                    logger.warning(
                        "Skipping unknown detectedClass %r",
                        groupId,
                    )
                    continue

                counts[detectedClass] += result["count"]

        return counts

    async def countByEventCategory(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> dict[EventCategory, int]:
        query = self._buildDateQuery(
            fromDate=fromDate,
            toDate=toDate,
        )

        pipeline = []

        if query:
            pipeline.append({"$match": query})

        pipeline.append(
            {
                "$group": {
                    "_id": "$eventCategory",
                    "count": {"$sum": 1},
                }
            }
        )

        counts = {
            eventCategory: 0
            for eventCategory in EventCategory
        }

        async for result in self.collection.aggregate(pipeline):
            groupId = result["_id"]

            if groupId is not None:
                try:
                    eventCategory = EventCategory(groupId)
                except ValueError:
                    logger.warning(
                        "Skipping unknown eventCategory %r",
                        groupId,
                    )
                    continue

                counts[eventCategory] = result["count"]

        return counts

    async def getStatisticsCounts(
        self,
        fromDate: datetime | None = None,
        toDate: datetime | None = None,
    ) -> tuple[
        dict[DetectedClass, int],
        dict[EventCategory, int],
    ]:
        query = self._buildDateQuery(
            fromDate=fromDate,
            toDate=toDate,
        )
        pipeline = [
            {"$match": query},
            {
                "$facet": {
                    "detectedClasses": [
                        {
                            "$group": {
                                "_id": "$detectedClass",
                                "count": {"$sum": 1},
                            }
                        }
                    ],
                    "eventCategories": [
                        {
                            "$group": {
                                "_id": "$eventCategory",
                                "count": {"$sum": 1},
                            }
                        }
                    ],
                }
            },
        ]
        facetResult = {}

        async for result in self.collection.aggregate(pipeline):
            facetResult = result
            break

        countsByClass = {
            detectedClass: 0
            for detectedClass in DetectedClass
        }

        for result in facetResult.get("detectedClasses", []):
            groupId = result["_id"]

            if groupId is None:
                continue

            try:
                detectedClass = _parseDetectedClass(groupId)
            except ValueError:
                logger.warning(
                    "Skipping unknown detectedClass %r",
                    groupId,
                )
                continue

            countsByClass[detectedClass] += result["count"]

        countsByCategory = {
            eventCategory: 0
            for eventCategory in EventCategory
        }

        for result in facetResult.get("eventCategories", []):
            groupId = result["_id"]

            try:
                eventCategory = EventCategory(groupId)
            except ValueError:
                logger.warning(
                    "Skipping unknown eventCategory %r",
                    groupId,
                )
                continue

            countsByCategory[eventCategory] = result["count"]

        return countsByClass, countsByCategory

    async def updateImageFileId(
        self,
        eventId: str,
        imageFileId: str,
    ) -> None:
        await self.collection.update_one(
            {"eventId": eventId},
            {"$set": {"imageFileId": imageFileId}},
        )

    async def updateImageFileIdIfMissing(
        self,
        eventId: str,
        imageFileId: str,
    ) -> bool:
        result = await self.collection.update_one(
            {
                "eventId": eventId,
                "$or": [
                    {"imageFileId": None},
                    {"imageFileId": {"$exists": False}},
                ],
            },
            {"$set": {"imageFileId": imageFileId}},
        )
        return result.modified_count > 0

    def _buildCurrentDocumentQuery(self) -> dict:
        return {
            "eventId": {"$type": "string", "$ne": ""},
            "timestamp": {"$type": "date"},
            "cameraId": {
                "$in": [item.value for item in CameraId]
            },
            "eventCategory": {
                "$in": [item.value for item in EventCategory]
            },
            "detectionId": {"$type": "string", "$ne": ""},
            "detectedClass": {
                "$in": [
                    None,
                    *[item.value for item in DetectedClass],
                    *_legacyDetectedClassValues,
                ]
            },
            "binId": {"$type": "string", "$ne": ""},
            "binType": {
                "$in": [
                    *[item.value for item in BinType],
                    *_legacyBinTypeValues,
                ]
            },
            "actionTaken": {
                "$in": [item.value for item in ActionTaken]
            },
            "modelVersion": {"$type": "string", "$ne": ""},
            "$and": [
                {
                    "$or": [
                        {"trackingId": None},
                        {
                            "trackingId": {
                                "$type": ["int", "long"],
                                "$gte": 0,
                            }
                        },
                    ]
                },
                {
                    "$or": [
                        {"imageFileId": None},
                        {"imageFileId": {"$type": "string"}},
                    ]
                },
                {
                    "$or": [
                        {"overflowDuration": None},
                        {
                            "overflowDuration": {
                                "$type": "number",
                                "$gte": 0.0,
                            }
                        },
                    ]
                },
                {
                    "$or": [
                        {"overflowThreshold": None},
                        {
                            "overflowThreshold": {
                                "$type": "number",
                                "$gte": 0.0,
                            }
                        },
                    ]
                },
                {
                    "$or": [
                        {"notes": None},
                        {"notes": {"$type": "string"}},
                    ]
                },
            ],
            "$or": [
                {
                    "eventCategory": "misclassification",
                    "cameraId": CameraId.ELEVTOP.value,
                    "detectedClass": {
                        "$in": [
                            item.value
                            for item in DetectedClass
                        ]
                    },
                    "isMisclassified": {"$type": "bool"},
                    "confidenceScore": {
                        "$type": "number",
                        "$gte": 0.0,
                        "$lte": 1.0,
                    },
                },
                {
                    "eventCategory": "overflow",
                    "cameraId": CameraId.ELEVSIDE.value,
                    "detectedClass": None,
                    "isMisclassified": None,
                    "confidenceScore": None,
                },
            ],
        }

    def _buildDateQuery(
        self,
        fromDate: datetime | None,
        toDate: datetime | None,
    ) -> dict:
        normalizedFromDate = self.normalizeDateTime(
            fromDate
        )
        normalizedToDate = self.normalizeDateTime(toDate)

        timestampQuery = {}

        if normalizedFromDate is not None:
            timestampQuery["$gte"] = normalizedFromDate

        if normalizedToDate is not None:
            timestampQuery["$lte"] = normalizedToDate

        query = self._buildCurrentDocumentQuery()

        if timestampQuery:
            query["timestamp"] = {
                "$type": "date",
                **timestampQuery,
            }

        return query

    def normalizeDateTime(
        self,
        dateTime: datetime | None,
    ) -> datetime | None:
        if dateTime is None:
            return None

        if not isinstance(dateTime, datetime):
            raise TypeError(
                "timestamp must be a BSON datetime"
            )

        if dateTime.tzinfo is None:
            return dateTime.replace(
                tzinfo=timezone.utc
            )

        return dateTime


eventRepository = EventRepository()


def _parseDetectedClass(value: str) -> DetectedClass:
    if value in _legacyDetectedClassValues:
        return _legacyDetectedClassValues[value]
    return DetectedClass(value)


def _parseBinType(value: str) -> BinType:
    if value in _legacyBinTypeValues:
        return _legacyBinTypeValues[value]
    return BinType(value)
