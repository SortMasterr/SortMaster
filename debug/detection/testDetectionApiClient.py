import http.client
import json
import unittest
from unittest.mock import patch

from debug.detection import detectionApiClient


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


class DetectionApiClientTest(unittest.TestCase):
    def testStartReturnsRecordingId(self):
        with patch.object(
            detectionApiClient.urllib.request,
            "urlopen",
            return_value=FakeResponse({"recordingId": "recording-1"}),
        ) as urlopen:
            recordingId = detectionApiClient.startDetection(
                "http://backend:8047/",
                "ELEV-SIDE",
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(
            urlopen.call_args.kwargs["timeout"],
            10,
        )
        self.assertEqual(recordingId, "recording-1")
        self.assertEqual(
            request.full_url,
            "http://backend:8047/api/detection/start",
        )
        self.assertEqual(
            json.loads(request.data),
            {"cameraId": "ELEV-SIDE"},
        )

    def testStopForwardsModelResultWithoutRuntimeDependency(self):
        detectionResult = {
            "recordingId": "recording-1",
            "cameraId": "ELEV-SIDE",
            "eventCategory": "overflow",
            "detectionId": "overflow-1",
            "binId": "BIN-GENERAL",
            "binType": "normal",
            "overflowDuration": 5.2,
            "overflowThreshold": 5.0,
            "modelVersion": "overflow-mvp-1",
        }

        with patch.object(
            detectionApiClient.urllib.request,
            "urlopen",
            return_value=FakeResponse({"eventId": "event-1"}),
        ) as urlopen:
            result = detectionApiClient.stopDetection(
                "http://backend:8047",
                detectionResult,
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(
            urlopen.call_args.kwargs["timeout"],
            60,
        )
        self.assertEqual(result["eventId"], "event-1")
        self.assertEqual(
            request.full_url,
            "http://backend:8047/api/detection/stop",
        )
        self.assertEqual(json.loads(request.data), detectionResult)

    def testStopRetriesOneConnectionFailureWithSamePayload(self):
        detectionResult = {
            "recordingId": "recording-retry",
            "cameraId": "ELEV-TOP",
            "detectionId": "detection-retry",
        }

        with (
            patch.object(
                detectionApiClient,
                "_postJson",
                side_effect=[
                    detectionApiClient.DetectionApiConnectionError(
                        "response lost"
                    ),
                    {"eventId": "event-retry"},
                ],
            ) as postJson,
            patch.object(
                detectionApiClient.time,
                "sleep",
            ) as sleep,
        ):
            result = detectionApiClient.stopDetection(
                "http://backend:8047",
                detectionResult,
            )

        self.assertEqual("event-retry", result["eventId"])
        self.assertEqual(2, postJson.call_count)
        self.assertEqual(
            postJson.call_args_list[0],
            postJson.call_args_list[1],
        )
        sleep.assert_called_once_with(0.5)

    def testStopRetriesRemoteDisconnectAfterServerProcessedRequest(self):
        detectionResult = {
            "recordingId": "recording-disconnected",
            "cameraId": "ELEV-TOP",
            "detectionId": "detection-disconnected",
        }

        with (
            patch.object(
                detectionApiClient.urllib.request,
                "urlopen",
                side_effect=[
                    http.client.RemoteDisconnected(
                        "response lost"
                    ),
                    FakeResponse({"eventId": "event-after-retry"}),
                ],
            ) as urlopen,
            patch.object(
                detectionApiClient.time,
                "sleep",
            ) as sleep,
        ):
            result = detectionApiClient.stopDetection(
                "http://backend:8047",
                detectionResult,
            )

        self.assertEqual(
            "event-after-retry",
            result["eventId"],
        )
        self.assertEqual(2, urlopen.call_count)
        self.assertEqual(
            urlopen.call_args_list[0].args[0].data,
            urlopen.call_args_list[1].args[0].data,
        )
        sleep.assert_called_once_with(0.5)


if __name__ == "__main__":
    unittest.main()
