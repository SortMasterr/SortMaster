import json
import unittest
from unittest.mock import patch

from debug.detection import binStateApiClient


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class BinStateApiClientTest(unittest.TestCase):
    def testGetBinStatesReturnsList(self):
        payload = [
            {
                "binId": "BIN-GENERAL",
                "currentState": "FULL",
            }
        ]

        with patch.object(
            binStateApiClient.urllib.request,
            "urlopen",
            return_value=FakeResponse(payload),
        ) as urlopen:
            binStates = binStateApiClient.getBinStates(
                "http://backend:8047/"
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(payload, binStates)
        self.assertEqual(
            request.full_url,
            "http://backend:8047/api/binStates",
        )
        self.assertEqual(request.get_method(), "GET")

    def testGetBinStatesReturnsEmptyListWhenBodyEmpty(self):
        with patch.object(
            binStateApiClient,
            "_request",
            return_value=None,
        ):
            binStates = binStateApiClient.getBinStates(
                "http://backend:8047"
            )

        self.assertEqual([], binStates)

    def testUpdateBinStateForwardsPayload(self):
        update = {
            "binId": "BIN-GENERAL",
            "binType": "general",
            "sessionId": "session-1",
            "currentState": "FULL",
            "confidenceScore": 0.97,
            "overflowDuration": 12.4,
            "overflowThreshold": 5.0,
            "detectionId": "detection-1",
            "modelVersion": "overflow-mvp-1",
        }

        with patch.object(
            binStateApiClient.urllib.request,
            "urlopen",
            return_value=FakeResponse(
                {**update, "activeOverflowEventId": "event-1"}
            ),
        ) as urlopen:
            result = binStateApiClient.updateBinState(
                "http://backend:8047",
                update,
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(result["activeOverflowEventId"], "event-1")
        self.assertEqual(
            request.full_url,
            "http://backend:8047/api/binStates",
        )
        self.assertEqual(json.loads(request.data), update)

    def testUpdateBinStateRetriesOneConnectionFailure(self):
        update = {"binId": "BIN-GENERAL"}

        with (
            patch.object(
                binStateApiClient,
                "_request",
                side_effect=[
                    binStateApiClient.BinStateApiConnectionError(
                        "response lost"
                    ),
                    {"binId": "BIN-GENERAL"},
                ],
            ) as request,
            patch.object(
                binStateApiClient.time,
                "sleep",
            ) as sleep,
        ):
            result = binStateApiClient.updateBinState(
                "http://backend:8047",
                update,
            )

        self.assertEqual({"binId": "BIN-GENERAL"}, result)
        self.assertEqual(2, request.call_count)
        sleep.assert_called_once_with(0.5)


if __name__ == "__main__":
    unittest.main()
