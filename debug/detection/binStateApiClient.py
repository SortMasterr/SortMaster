"""넘침 감지 모델(계획상 GPU 서버 `inference`)과 SortMaster 백엔드 사이의 BIN_STATES HTTP
연결 클라이언트. `detectionApiClient.py`와 동일한 패턴(표준 라이브러리만 사용, 재시도 로직
포함)이며, 통 상태(NORMAL/FULL) 갱신 신호를 보내는 용도로 별도 분리했다 — misclassification
쪽 시작/종료 신호와 성격이 달라서(1회성 시작~종료가 아니라 주기적 상태 보고) 같은 클라이언트에
억지로 합치지 않았다.

예시:
    binState = updateBinState(
        "http://localhost:8047",
        {
            "binId": "BIN-GENERAL",
            "binType": "general",
            "sessionId": "감지 모델 프로세스 시작 시 생성한 UUID",
            "currentState": "FULL",
            "confidenceScore": 0.97,
            "overflowDuration": 12.4,
            "overflowThreshold": 5.0,
            "detectionId": "전환 시점마다 새로 생성하는 UUID",
            "modelVersion": "overflow-mvp-1",
        },
    )
    binStates = getBinStates("http://localhost:8047")
"""
import http.client
import json
import time
import urllib.error
import urllib.request


class BinStateApiError(RuntimeError):
    pass


class BinStateApiConnectionError(BinStateApiError):
    pass


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    timeoutSeconds: float = 10,
) -> dict | list | None:
    request = urllib.request.Request(
        url,
        data=(
            json.dumps(payload).encode("utf-8")
            if payload is not None
            else None
        ),
        headers=(
            {"Content-Type": "application/json"}
            if payload is not None
            else {}
        ),
        method=method,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeoutSeconds,
        ) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise BinStateApiError(
            f"백엔드 요청 실패({error.code}): {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise BinStateApiConnectionError(
            f"백엔드에 연결할 수 없습니다: {error.reason}"
        ) from error
    except TimeoutError as error:
        raise BinStateApiConnectionError(
            "백엔드 요청 시간이 초과되었습니다."
        ) from error
    except (
        OSError,
        http.client.HTTPException,
    ) as error:
        raise BinStateApiConnectionError(
            f"백엔드 연결이 응답 중 끊어졌습니다: {error}"
        ) from error

    return json.loads(body) if body else None


def getBinStates(
    backendUrl: str,
) -> list[dict]:
    response = _request(
        "GET",
        f"{backendUrl.rstrip('/')}/api/binStates",
    )

    return response if response is not None else []


def updateBinState(
    backendUrl: str,
    binStateUpdate: dict,
) -> dict | None:
    updateUrl = (
        f"{backendUrl.rstrip('/')}/api/binStates"
    )
    lastError = None

    for attempt in range(2):
        try:
            return _request(
                "POST",
                updateUrl,
                binStateUpdate,
                timeoutSeconds=10,
            )
        except BinStateApiConnectionError as error:
            lastError = error

            if attempt == 0:
                time.sleep(0.5)

    if lastError is None:
        raise BinStateApiError(
            "갱신 요청 재시도 상태가 올바르지 않습니다."
        )

    raise lastError
