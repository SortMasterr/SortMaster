import asyncio
import os

import cv2
from dotenv import load_dotenv

from schemas.event import CameraId

load_dotenv()

_ffmpegPath = os.getenv("FFMPEG_PATH", "ffmpeg")
_readChunkSize = 65536
_jpegQuality = "3"  # ffmpeg -q:v 스케일: 2(최고 화질)~31(최저)
_readTimeoutSeconds = 5.0
_outputFps = "12"  # 소스(약 20fps)보다 낮춰서 CPU 경합 시 여유를 둠(라이브뷰엔 충분)


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
        self.isRtsp = (
            isinstance(source, str) and source.startswith("rtsp://")
        )

        # RTSP 전용 상태 — OpenCV에 내장된 소형 ffmpeg는 손상된 H264 프레임을 만나면
        # 파이썬이 못 잡는 네이티브 크래시(Assertion fctx->async_lock failed,
        # malloc 힙 손상 등 실제로 관측됨)를 내서 백엔드 전체가 죽는 문제가 있었음.
        # 그래서 진짜 ffmpeg 바이너리를 별도 OS 프로세스로 띄우고 MJPEG로 재인코딩한
        # stdout을 읽는 방식으로 바꿈 — 크래시가 나도 이 프로세스 하나만 죽고,
        # 아래 _runRtspLoop가 자동으로 재시작한다.
        self.latestFrame: bytes | None = None
        self.process: asyncio.subprocess.Process | None = None
        self._readerTask: asyncio.Task | None = None
        self._openedEvent = asyncio.Event()

        # 로컬 웹캠(정수 인덱스) 전용 — 지금까지 크래시가 관측된 적 없는 경로라
        # 기존 cv2.VideoCapture 방식 그대로 유지.
        self.capture: cv2.VideoCapture | None = None
        self.lock = asyncio.Lock()

    async def start(self) -> None:
        if self.source is None:
            raise RuntimeError(
                f"카메라 소스가 설정되지 않음: {self.label} (.env 확인 필요)"
            )

        if self.isRtsp:
            await self._startRtsp()
        else:
            await self._startLocal()

    async def readFrame(self) -> bytes | None:
        if self.isRtsp:
            return self.latestFrame

        return await self._readLocalFrame()

    async def stop(self) -> None:
        if self.isRtsp:
            await self._stopRtsp()
        else:
            await self._stopLocal()

    # ---- RTSP (ffmpeg 서브프로세스) ----

    async def _startRtsp(self) -> None:
        if self._readerTask is None or self._readerTask.done():
            self._openedEvent = asyncio.Event()
            self._readerTask = asyncio.create_task(
                self._runRtspLoop()
            )
        elif self._openedEvent.is_set():
            return

        budget = self.maxRetry * self.retryDelay + self.retryDelay

        try:
            await asyncio.wait_for(
                self._openedEvent.wait(), timeout=budget
            )
        except asyncio.TimeoutError as error:
            print(
                f"[cameraManager] '{self.label}' 카메라 연결 실패: {self.source}"
            )
            raise RuntimeError(
                f"카메라 연결 실패: {self.label}"
            ) from error

    async def _runRtspLoop(self) -> None:
        # 소스가 죽었다 살아나거나, ffmpeg가 크래시로 죽어도 여기서 계속
        # 재시도한다 — 지금 아무도 이 스트림을 안 보고 있어도 백그라운드에서
        # 계속 재연결을 시도하는 게 의도된 동작(자가치유).
        try:
            while True:
                try:
                    await self._runFfmpegOnce()
                except Exception as error:
                    print(
                        f"[cameraManager] '{self.label}' 워커 오류: {error}"
                    )

                await asyncio.sleep(self.retryDelay)
        finally:
            self.latestFrame = None
            await self._terminateProcess()

    async def _runFfmpegOnce(self) -> bool:
        # ffmpeg 자체의 타임아웃 CLI 옵션(-timeout/-stimeout 등)은 버전마다 이름/지원
        # 여부가 달라서(도커 이미지의 apt-get ffmpeg와 개발 PC의 winget ffmpeg 버전이
        # 다를 수 있음 — 실제로 이번에 -stimeout이 로컬 버전에서 무효 옵션이었음) 믿지
        # 않고, 아래 read() 쪽에서 파이썬 코드로 직접 타임아웃을 건다.
        command = [
            _ffmpegPath,
            "-hide_banner",
            "-loglevel", "warning",
            "-rtsp_transport", "tcp",
            "-i", self.source,
            "-f", "mjpeg",
            "-q:v", _jpegQuality,
            # ffmpeg는 들어오는 프레임을 하나도 안 버리고 전부 순서대로
            # 디코딩+JPEG 재인코딩함 — 우리 파이썬 쪽 "최신 프레임만 유지" 로직은
            # ffmpeg가 이미 내보낸 것에만 적용되지, ffmpeg 내부 처리 자체가 실시간을
            # 못 따라가면(다른 프로세스와 CPU 경합 등) 그 지연은 우리가 손 못 댐 —
            # 실사용 중 실제로 이렇게 지연이 누적되는 게 확인됨. 그래서 출력
            # 프레임레이트를 소스(약 20fps)보다 낮게 제한해서 ffmpeg가 못 따라잡을
            # 상황이 되면 인코딩 자체를 덜 하도록(=오래된 프레임을 드롭하도록) 강제.
            "-r", _outputFps,
            "pipe:1",
        ]

        # 소스 문자열(RTSP URL에 인증정보가 포함될 수 있음)은 서버 로그에만 남기고
        # API 응답에는 절대 포함하지 않음(기존 원칙과 동일) — 지금 이 카메라 슬롯이
        # 실제로 어느 RTSP 경로를 구독 중인지 로그로 바로 확인할 수 있게 함
        # (.env 값이 컨테이너에 실제로 반영됐는지 등을 docker logs로 바로 검증 가능).
        print(
            f"[cameraManager] '{self.label}' 연결 시도: {self.source}"
        )

        try:
            self.process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            print(
                f"[cameraManager] ffmpeg 실행 파일을 찾을 수 없음: {_ffmpegPath}"
            )
            return False

        # ffmpeg는 진행 상황을 stderr에 계속 찍는데, 아무도 안 읽으면 OS 파이프
        # 버퍼(보통 64KB)가 꽉 차서 ffmpeg 자신이 stderr 쓰기에서 멈춰버림
        # (=스트리밍이 조용히 멈추는 원인이었음, 실제로 관측됨). 그래서 항상
        # 백그라운드에서 계속 비워준다 — 위의 -loglevel warning은 애초에 양을
        # 줄이는 보조 수단이고, 이 드레인이 실제 방지책.
        stderrBuffer = bytearray()
        stderrTask = asyncio.create_task(
            self._drainStderr(self.process, stderrBuffer)
        )

        buffer = bytearray()
        openedThisRun = False

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.process.stdout.read(
                            _readChunkSize
                        ),
                        timeout=_readTimeoutSeconds,
                    )
                except asyncio.TimeoutError:
                    print(
                        f"[cameraManager] '{self.label}' "
                        f"{_readTimeoutSeconds}초간 응답 없음, 재연결"
                    )
                    break

                if not chunk:
                    break

                buffer.extend(chunk)

                # 한 번에 여러 프레임이 들어올 수 있어 계속 스캔하면서
                # 오래된 프레임은 버리고 항상 최신 것만 유지한다.
                while True:
                    start = buffer.find(b"\xff\xd8")

                    if start == -1:
                        break

                    end = buffer.find(b"\xff\xd9", start)

                    if end == -1:
                        break

                    self.latestFrame = bytes(
                        buffer[start:end + 2]
                    )
                    del buffer[:end + 2]

                    if not openedThisRun:
                        openedThisRun = True
                        self._openedEvent.set()
        finally:
            self.latestFrame = None

            stderrTask.cancel()

            try:
                await stderrTask
            except asyncio.CancelledError:
                pass

            # 연결이 한 번도 안 열렸으면(=진짜 실패) ffmpeg가 왜 실패했는지
            # 드레인해둔 stderr 마지막 부분을 로그로 남김 — 소스 URL엔 인증정보가
            # 있을 수 있어서 명령어 자체는 안 찍고 ffmpeg 출력만 남긴다.
            if not openedThisRun and stderrBuffer:
                print(
                    f"[cameraManager] '{self.label}' ffmpeg 실패 로그: "
                    + stderrBuffer.decode(errors="replace")
                )

            await self._terminateProcess()

        return openedThisRun

    async def _drainStderr(
        self,
        process: asyncio.subprocess.Process,
        tailBuffer: bytearray,
    ) -> None:
        if process.stderr is None:
            return

        try:
            while True:
                chunk = await process.stderr.read(
                    _readChunkSize
                )

                if not chunk:
                    break

                # -loglevel warning이라 정상 상태에선 거의 안 찍히는데, 그럼에도
                # 뭔가 나온다는 건 실제 경고(RTP 패킷 유실, 타임스탬프 불연속 등) —
                # 연결이 안 끊긴 "성공 중" 상태에서도 실시간으로 바로 보이게 함
                # (기존엔 완전 실패했을 때만 로그에 남아서 "연결은 됐는데 밀리는"
                # 상황이 안 보였음).
                print(
                    f"[cameraManager] '{self.label}' ffmpeg: "
                    + chunk.decode(errors="replace").rstrip()
                )

                tailBuffer.extend(chunk)

                if len(tailBuffer) > 2000:
                    del tailBuffer[:len(tailBuffer) - 2000]
        except asyncio.CancelledError:
            pass

    async def _terminateProcess(self) -> None:
        if self.process is None:
            return

        if self.process.returncode is None:
            self.process.terminate()

            try:
                await asyncio.wait_for(
                    self.process.wait(), timeout=2.0
                )
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

        self.process = None

    async def _stopRtsp(self) -> None:
        if self._readerTask is not None:
            self._readerTask.cancel()

            try:
                await self._readerTask
            except asyncio.CancelledError:
                pass

            self._readerTask = None

        self.latestFrame = None

    # ---- 로컬 웹캠(cv2) ----

    def _openLocal(self) -> cv2.VideoCapture:
        capture = cv2.VideoCapture(self.source)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return capture

    async def _startLocal(self) -> None:
        async with self.lock:
            if self.capture is not None and self.capture.isOpened():
                return

            for attempt in range(1, self.maxRetry + 1):
                self.capture = await asyncio.to_thread(
                    self._openLocal
                )

                if self.capture.isOpened():
                    return

                await asyncio.to_thread(self.capture.release)
                self.capture = None

                if attempt < self.maxRetry:
                    await asyncio.sleep(self.retryDelay)

            print(
                f"[cameraManager] '{self.label}' 카메라 연결 실패: {self.source}"
            )
            raise RuntimeError(
                f"카메라 연결 실패: {self.label}"
            )

    async def _readLocalFrame(self) -> bytes | None:
        if self.capture is None or not self.capture.isOpened():
            return None

        async with self.lock:
            ok, frame = await asyncio.to_thread(
                self.capture.read
            )

        if not ok:
            return None

        encoded, jpegBuffer = await asyncio.to_thread(
            cv2.imencode, ".jpg", frame
        )

        return jpegBuffer.tobytes() if encoded else None

    async def _stopLocal(self) -> None:
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
