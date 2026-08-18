import asyncio
import os
import time

import cv2
from dotenv import load_dotenv

from schemas.event import CameraId

load_dotenv()

# RTSP 소스는 CAP_PROP_BUFFERSIZE=1을 무시하고 ffmpeg 내부 큐에 프레임을 계속 쌓아두는
# 경우가 있어(디버그: debug/streaming/testRtspDelay.py로 확인 — 1초만 안 읽어도
# 40개 이상 쌓임), readFrame()에서 grab()으로 오래된 프레임을 건너뛰고 라이브 edge의
# 최신 프레임만 꺼낸다. grab()이 이 시간(초)보다 빨리 끝나면 "이미 쌓여있던 프레임"으로
# 보고 계속 건너뛰고, 이 시간을 넘기면(=실시간으로 다음 프레임을 기다림) 최신 프레임에
# 도달한 것으로 보고 멈춘다.
_bufferDrainThresholdSeconds = 0.05
_maxBufferDrain = 200


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
            # threads;1: ffmpeg 멀티스레드 프레임 디코딩에서 나는
            # "Assertion fctx->async_lock failed" 크래시 회피용.
            # stimeout/rw_timeout: ffmpeg RTSP 백엔드는 기본적으로 읽기 타임아웃이 없어서,
            # 네트워크가 응답을 안 주면 grab()이 에러 없이 무한 대기함 — 연결 자체는 열렸는데
            # 프레임이 하나도 안 오는 상황(디버깅 시 원인 파악용)을 5초 후 명시적 에러로
            # 바꾸기 위함(단순 hang과 진짜 실패를 로그로 구분 가능해짐).
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;tcp|threads;1|stimeout;5000000|rw_timeout;5000000"
            )

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
            for _ in range(_maxBufferDrain):
                start = time.monotonic()
                grabbed = await asyncio.to_thread(
                    self.capture.grab
                )
                elapsed = time.monotonic() - start

                if not grabbed:
                    return None

                if elapsed > _bufferDrainThresholdSeconds:
                    break

            ok, frame = await asyncio.to_thread(
                self.capture.retrieve
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
