import unittest
from datetime import datetime, timezone

from repositories.binStateRepository import BinStateRepository
from schemas.binState import BinStateUpdate
from schemas.event import BinType


class AsyncCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, *_args):
        return self

    def __aiter__(self):
        self.iterator = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration as error:
            raise StopAsyncIteration from error


class FakeCollection:
    def __init__(self, documents):
        self.documents = documents

    def find(self, _query):
        return AsyncCursor(self.documents)


class TestBinStateRepository(BinStateRepository):
    def __init__(self, documents):
        super().__init__()
        self.testCollection = FakeCollection(documents)

    @property
    def collection(self):
        return self.testCollection


class BinStateRepositoryCompatibilityTest(unittest.TestCase):
    def testPreviousBinTypeIsReadAsCurrentApiValue(self):
        document = {
            "binId": "BIN-GENERAL",
            "cameraId": "ELEV-SIDE",
            "binType": "general",
            "sessionId": "session-1",
            "currentState": "NORMAL",
            "confidenceScore": 0.9,
            "overflowDuration": 0.0,
            "lastChangedAt": datetime.now(timezone.utc),
            "activeOverflowEventId": None,
        }

        binState = BinStateRepository()._fromDocument(document)

        self.assertEqual(BinType.NORMAL, binState.binType)

    def testLegacySideBinIdIsReadAsGeneralBin(self):
        document = {
            "binId": "bin-side-01",
            "cameraId": "ELEV-SIDE",
            "binType": "normal",
            "sessionId": "session-1",
            "currentState": "FULL",
            "confidenceScore": 0.9,
            "overflowDuration": 30.0,
            "lastChangedAt": datetime.now(timezone.utc),
            "activeOverflowEventId": "event-1",
        }

        binState = BinStateRepository()._fromDocument(document)

        self.assertEqual("BIN-GENERAL", binState.binId)

    def testLegacySideBinIdInputIsNormalized(self):
        update = BinStateUpdate(
            binId="bin-side-01",
            cameraId="ELEV-SIDE",
            binType="normal",
            sessionId="session-1",
            currentState="FULL",
            confidenceScore=0.9,
            overflowDuration=30.0,
            overflowThreshold=30.0,
            detectionId="detection-1",
            modelVersion="test-v1",
        )

        self.assertEqual("BIN-GENERAL", update.binId)


class BinStateRepositoryListTest(unittest.IsolatedAsyncioTestCase):
    async def testFindAllKeepsLatestStateAfterLegacyIdNormalization(self):
        baseDocument = {
            "cameraId": "ELEV-SIDE",
            "binType": "normal",
            "confidenceScore": 0.9,
            "overflowDuration": 0.0,
            "activeOverflowEventId": None,
        }
        repository = TestBinStateRepository([
            {
                **baseDocument,
                "binId": "BIN-GENERAL",
                "sessionId": "old-session",
                "currentState": "FULL",
                "lastChangedAt": datetime(
                    2026, 8, 26, tzinfo=timezone.utc
                ),
            },
            {
                **baseDocument,
                "binId": "bin-side-01",
                "sessionId": "new-session",
                "currentState": "NORMAL",
                "lastChangedAt": datetime(
                    2026, 8, 27, tzinfo=timezone.utc
                ),
            },
        ])

        states = await repository.findAll()

        self.assertEqual(1, len(states))
        self.assertEqual("BIN-GENERAL", states[0].binId)
        self.assertEqual("NORMAL", states[0].currentState.value)
        self.assertEqual("new-session", states[0].sessionId)


if __name__ == "__main__":
    unittest.main()
