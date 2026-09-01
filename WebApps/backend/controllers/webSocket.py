from datetime import (
    datetime,
    timezone,
)

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)

from services.modeService import modeService
from services.webSocketManager import (
    webSocketManager,
)


router = APIRouter(
    tags=["webSocket"],
)


@router.websocket("/ws/events")
async def eventWebSocket(
    webSocket: WebSocket,
) -> None:
    await webSocketManager.connect(
        webSocket
    )

    currentMode = modeService.getMode()

    await webSocketManager.sendPersonalMessage(
        {
            "eventType": "MODE_CHANGED",
            "mode": currentMode.mode.value,
            "timestamp": (
                datetime.now(timezone.utc)
                .isoformat()
            ),
        },
        webSocket,
    )

    try:
        while True:
            await webSocket.receive_text()

    except WebSocketDisconnect:
        webSocketManager.disconnect(
            webSocket
        )

    except Exception:
        webSocketManager.disconnect(
            webSocket
        )