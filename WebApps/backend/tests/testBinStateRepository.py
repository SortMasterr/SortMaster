import unittest
from datetime import datetime, timezone

from repositories.binStateRepository import BinStateRepository
from schemas.binState import BinStateUpdate
from schemas.event import BinType


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


if __name__ == "__main__":
    unittest.main()
