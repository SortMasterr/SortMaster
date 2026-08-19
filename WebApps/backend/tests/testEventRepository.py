import unittest
from datetime import datetime, timezone

from repositories.eventRepository import EventRepository
from schemas.event import DetectedClass, EventCategory


class AsyncCursor:
    def __init__(self, documents):
        self.documents = list(documents)
        self.index = 0

    def sort(self, *_args):
        return self

    def __aiter__(self):
        self.index = 0
        return self

    async def __anext__(self):
        if self.index >= len(self.documents):
            raise StopAsyncIteration

        document = self.documents[self.index]
        self.index += 1
        return document


class FakeCollection:
    def __init__(self, documents=None, aggregateResults=None):
        self.documents = documents or []
        self.aggregateResults = aggregateResults or []
        self.lastQuery = None
        self.lastPipeline = None

    def find(self, query):
        self.lastQuery = query
        return AsyncCursor(self.documents)

    def aggregate(self, pipeline):
        self.lastPipeline = pipeline
        return AsyncCursor(self.aggregateResults)


class TestEventRepository(EventRepository):
    def __init__(self, collection):
        super().__init__()
        self.testCollection = collection

    @property
    def collection(self):
        return self.testCollection


def currentDocument():
    return {
        "eventId": "event-current",
        "timestamp": datetime.now(timezone.utc),
        "cameraId": "ELEV-TOP",
        "eventCategory": "misclassification",
        "detectionId": "detection-current",
        "trackingId": 1,
        "detectedClass": "plastic",
        "binId": "BIN-PAPER",
        "binType": "paper",
        "isMisclassified": True,
        "confidenceScore": 0.9,
        "actionTaken": "lightAndSound",
        "imageFileId": None,
        "overflowDuration": None,
        "overflowThreshold": None,
        "modelVersion": "test-v1",
        "notes": None,
    }


class EventRepositoryCompatibilityTest(
    unittest.IsolatedAsyncioTestCase
):
    def testNaiveMongoTimestampIsNormalizedToUtc(self):
        document = currentDocument()
        document["timestamp"] = datetime(2026, 8, 19, 12, 0)
        repository = EventRepository()

        event = repository._fromDocument(document)

        self.assertEqual(timezone.utc, event.timestamp.tzinfo)

    def testStringTimestampIsQuarantined(self):
        document = currentDocument()
        document["timestamp"] = "2026-08-19T12:00:00Z"
        repository = EventRepository()

        self.assertIsNone(
            repository._tryFromDocument(document)
        )

    def testCurrentQueryValidatesOptionalFieldTypes(self):
        query = EventRepository()._buildCurrentDocumentQuery()
        optionalFields = {
            next(iter(condition["$or"][1]))
            for condition in query["$and"]
        }

        self.assertEqual(
            {
                "trackingId",
                "imageFileId",
                "overflowDuration",
                "overflowThreshold",
                "notes",
            },
            optionalFields,
        )
        trackingCondition = query["$and"][0]["$or"][1][
            "trackingId"
        ]
        self.assertEqual(0, trackingCondition["$gte"])

    async def testFindAllSkipsLegacyDocumentWithoutBreakingList(self):
        legacyDocument = {
            "eventId": "legacy-event",
            "timestamp": datetime.now(timezone.utc),
            "cameraId": "ELEV-TOP",
        }
        collection = FakeCollection(
            [legacyDocument, currentDocument()]
        )
        repository = TestEventRepository(collection)

        events = await repository.findAll()

        self.assertEqual(
            ["event-current"],
            [event.eventId for event in events],
        )
        self.assertIn("detectionId", collection.lastQuery)

    async def testStatisticsIgnoreUnknownLegacyEnumValues(self):
        collection = FakeCollection(
            aggregateResults=[
                {"_id": "legacy-value", "count": 4},
                {"_id": "plastic", "count": 2},
            ]
        )
        repository = TestEventRepository(collection)

        classCounts = await repository.countByDetectedClass()

        self.assertEqual(2, classCounts[DetectedClass.PLASTIC])
        self.assertEqual(
            set(DetectedClass),
            set(classCounts),
        )

        collection.aggregateResults = [
            {"_id": "legacy-value", "count": 4},
            {"_id": "overflow", "count": 1},
        ]

        categoryCounts = await repository.countByEventCategory()

        self.assertEqual(
            1,
            categoryCounts[EventCategory.OVERFLOW],
        )
        self.assertEqual(
            set(EventCategory),
            set(categoryCounts),
        )

    async def testStatisticsCountsUseOneFacetSnapshot(self):
        collection = FakeCollection(
            aggregateResults=[
                {
                    "detectedClasses": [
                        {"_id": "paper", "count": 3},
                    ],
                    "eventCategories": [
                        {
                            "_id": "misclassification",
                            "count": 3,
                        },
                        {"_id": "overflow", "count": 2},
                    ],
                }
            ]
        )
        repository = TestEventRepository(collection)

        (
            classCounts,
            categoryCounts,
        ) = await repository.getStatisticsCounts()

        self.assertEqual(3, classCounts[DetectedClass.PAPER])
        self.assertEqual(
            3,
            categoryCounts[EventCategory.MISCLASSIFICATION],
        )
        self.assertEqual(
            2,
            categoryCounts[EventCategory.OVERFLOW],
        )
        self.assertIn("$facet", collection.lastPipeline[-1])


if __name__ == "__main__":
    unittest.main()
