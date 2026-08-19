"""엣지 모델과 SortMaster 백엔드 사이의 HTTP 연결 클라이언트.

모델 런타임(PyTorch/TensorRT)과 무관하게 탐지 시작·종료 시점에 이 모듈의 두 함수를
호출하면 된다. 외부 패키지 없이 Python 표준 라이브러리만 사용한다.

예시:
    recordingId = startDetection("http://localhost:8047", "ELEV-SIDE")
    event = stopDetection(
        "http://localhost:8047",
        {
            "recordingId": recordingId,
            "cameraId": "ELEV-SIDE",
            "eventCategory": "overflow",
            "detectionId": "엣지에서 생성한 UUID",
            "binId": "BIN-GENERAL",
            "binType": "general",
            "overflowDuration": 5.2,
            "overflowThreshold": 5.0,
            "modelVersion": "overflow-mvp-1",
        },
    )
"""
import http.client
import json
import time
import urllib.error
import urllib.request


class DetectionApiError(RuntimeError):
    pass


class DetectionApiConnectionError(DetectionApiError):
    pass


def _postJson(
    url: str,
    payload: dict,
    timeoutSeconds: float = 10,
) -> dict | None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeoutSeconds,
        ) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise DetectionApiError(
            f"백엔드 요청 실패({error.code}): {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise DetectionApiConnectionError(
            f"백엔드에 연결할 수 없습니다: {error.reason}"
        ) from error
    except TimeoutError as error:
        raise DetectionApiConnectionError(
            "백엔드 요청 시간이 초과되었습니다."
        ) from error
    except (
        OSError,
        http.client.HTTPException,
    ) as error:
        raise DetectionApiConnectionError(
            f"백엔드 연결이 응답 중 끊어졌습니다: {error}"
        ) from error

    return json.loads(body) if body else None


def startDetection(
    backendUrl: str,
    cameraId: str,
) -> str:
    response = _postJson(
        f"{backendUrl.rstrip('/')}/api/detection/start",
        {"cameraId": cameraId},
    )

    if not response or "recordingId" not in response:
        raise DetectionApiError(
            "백엔드 응답에 recordingId가 없습니다."
        )

    return response["recordingId"]


def stopDetection(
    backendUrl: str,
    detectionResult: dict,
) -> dict | None:
    stopUrl = (
        f"{backendUrl.rstrip('/')}/api/detection/stop"
    )
    lastError = None

    for attempt in range(2):
        try:
            return _postJson(
                stopUrl,
                detectionResult,
                timeoutSeconds=60,
            )
        except DetectionApiConnectionError as error:
            lastError = error

            if attempt == 0:
                time.sleep(0.5)

    if lastError is None:
        raise DetectionApiError(
            "종료 요청 재시도 상태가 올바르지 않습니다."
        )

    raise lastError
