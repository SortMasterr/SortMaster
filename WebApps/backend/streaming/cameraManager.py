import asyncio
import os

import cv2
from dotenv import load_dotenv

load_dotenv()


class CameraManager:
    def __init__(
        self,
        source,
        role: str,
        maxRetry: int = 5,
        retryDelay: float = 1.0,
    ):
        self.source = source
        self.role = role
        self.maxRetry = maxRetry
        self.retryDelay = retryDelay
        self.capture: cv2.VideoCapture | None = None
        self.lock = asyncio.Lock()

    def _open(self) -> cv2.VideoCapture:
        capture = cv2.VideoCapture(self.source)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return capture

    async def start(self) -> None:
        if self.source is None:
            raise RuntimeError(
                f"카메라 소스가 설정되지 않음: {self.role} (.env 확인 필요)"
            )

        async with self.lock:
            if self.capture is not None and self.capture.isOpened():
                return

            for attempt in range(1, self.maxRetry + 1):
                self.capture = await asyncio.to_thread(self._open)

                if self.capture.isOpened():
                    return

                await asyncio.to_thread(self.capture.release)
                self.capture = None

                if attempt < self.maxRetry:
                    await asyncio.sleep(self.retryDelay)

            # 소스 문자열(RTSP URL에 인증정보가 포함될 수 있음)은 서버 로그에만 남기고,
            # API 응답(HTTPException detail)에는 절대 포함하지 않음 — 이 API는 인증이 없어서
            # 누구나 에러 메시지를 볼 수 있음
            print(
                f"[cameraManager] '{self.role}' 카메라 연결 실패: {self.source}"
            )

            raise RuntimeError(
                f"카메라 연결 실패: {self.role}"
            )

    async def readFrame(self):
        if self.capture is None or not self.capture.isOpened():
            return None

        async with self.lock:
            ok, frame = await asyncio.to_thread(
                self.capture.read
            )

        return frame if ok else None

    async def stop(self) -> None:
        async with self.lock:
            if self.capture is not None:
                await asyncio.to_thread(self.capture.release)
                self.capture = None


def _resolveCameraSource(envKey: str, default: str | None = None):
    rawSource = os.getenv(envKey, default)

    if rawSource is None:
        return None

    if rawSource.isdigit():
        return int(rawSource)

    return rawSource


# 지점당 위(Top)+옆(Side) 카메라 2대 구성 (architecture.md 참고).
# CAMERA_SOURCE_SIDE가 .env에 없으면 side 카메라는 미설정 상태로 남고,
# 스트림 요청 시 503으로 처리됨(카메라 1대만 연결된 개발 환경 대응).
cameraManagers = {
    "top": CameraManager(
        _resolveCameraSource("CAMERA_SOURCE", default="0"),
        role="top",
    ),
    "side": CameraManager(
        _resolveCameraSource("CAMERA_SOURCE_SIDE"),
        role="side",
    ),
}
