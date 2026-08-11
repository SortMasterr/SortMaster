from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.activeConnections: list[
            WebSocket
        ] = []

    async def connect(
        self,
        webSocket: WebSocket,
    ) -> None:
        await webSocket.accept()

        self.activeConnections.append(
            webSocket
        )

    def disconnect(
        self,
        webSocket: WebSocket,
    ) -> None:
        if (
            webSocket
            in self.activeConnections
        ):
            self.activeConnections.remove(
                webSocket
            )

    async def sendPersonalMessage(
        self,
        message: dict,
        webSocket: WebSocket,
    ) -> None:
        await webSocket.send_json(
            message
        )

    async def broadcast(
        self,
        message: dict,
    ) -> None:
        disconnectedConnections = []

        for webSocket in self.activeConnections:
            try:
                await webSocket.send_json(
                    message
                )
            except Exception:
                disconnectedConnections.append(
                    webSocket
                )

        for webSocket in disconnectedConnections:
            self.disconnect(webSocket)


webSocketManager = WebSocketManager()