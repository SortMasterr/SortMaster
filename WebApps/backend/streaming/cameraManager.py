import asyncio
import os

import cv2
from dotenv import load_dotenv

from schemas.event import CameraId

load_dotenv()


class CameraManager:
    def __init__(
        self,
        source,
        label: str,
        maxRetry: int = 5,
        retryDelay: float = 1.0,
    ):
        self.source = source
        self.label = label
        self.maxRetry = maxRetry
        self.retryDelay = retryDelay
        self.capture: cv2.VideoCapture | None = None
        self.lock = asyncio.Lock()

    def _open(self) -> cv2.VideoCapture:
        if isinstance(self.source, str) and self.source.startswith("rtsp://"):
            # RTSP 영상 데이터는 기본적으로 UDP로 전송되는데, 방화벽에 UDP 포트를
            # 별도로 안 열어도 되도록 TCP로 강제(제어 채널과 같은 포트로 처리됨).
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

        capture = cv2.VideoCapture(self.source)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return capture

    async def start(self) -> None:
        if self.source is None:
            raise RuntimeError(
                f"카메라 소스가 설정되지 않음: {self.label} (.env 확인 필요)"
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
                f"[cameraManager] '{self.label}' 카메라 연결 실패: {self.source}"
            )

            raise RuntimeError(
                f"카메라 연결 실패: {self.label}"
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


def _envKeyForCameraId(cameraId: str) -> str:
    # "ELEV-TOP" -> "CAMERA_SOURCE_ELEVTOP", "REST-4F-01" -> "CAMERA_SOURCE_REST4F01"
    return "CAMERA_SOURCE_" + cameraId.replace("-", "").upper()


# 지점(CameraId)당 카메라 1대, 지점마다 독립된 젯슨 나노 1개(architecture.md 참고).
# CAMERA_SOURCE_<ID>가 .env에 없으면 해당 지점은 미설정 상태로 남고,
# 스트림 요청 시 503으로 처리됨(일부 지점만 연결된 개발 환경 대응).
# ELEV-TOP만 기본값 "0"으로 둬서, 로컬 웹캠 1대짜리 개발 환경에서 바로 동작하게 함.
_defaultSources = {CameraId.ELEVTOP.value: "0"}

cameraManagers = {
    cameraId.value: CameraManager(
        _resolveCameraSource(
            _envKeyForCameraId(cameraId.value),
            default=_defaultSources.get(cameraId.value),
        ),
        label=cameraId.value,
    )
    for cameraId in CameraId
}
