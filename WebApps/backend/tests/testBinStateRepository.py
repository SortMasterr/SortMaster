import unittest
from datetime import datetime, timezone

from repositories.binStateRepository import BinStateRepository
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


if __name__ == "__main__":
    unittest.main()
