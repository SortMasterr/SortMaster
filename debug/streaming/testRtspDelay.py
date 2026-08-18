"""
RTSP 스트리밍 지연이 "병목(버퍼링 누적)" 때문인지 확인하는 디버그 스크립트.
streaming/cameraManager.py를 수정하지 않고, 같은 옵션(rtsp_transport;tcp, threads;1)으로
직접 cv2.VideoCapture를 열어서 두 가지를 측정한다:

  1. 방치 구간 측정: 일부러 N초간 안 읽고 두면, 그새 파이프(ffmpeg 내부 큐/OS 소켓 버퍼 등,
     CAP_PROP_BUFFERSIZE로 온전히 제어 안 되는 영역)에 프레임이 쌓이는지 → 쌓이면 "병목형
     지연"(오래된 프레임이 FIFO로 계속 밀려서 나옴)이 맞다는 뜻
  2. 현재 방식(capture.read() 단순 호출) vs 수정안(오래된 프레임을 grab()으로 버리고
     최신 프레임만 retrieve()하는 flush 방식)을 다운스트림 처리 지연(JPEG 인코딩+탐지 등
     흉내)이 있는 상황에서 같은 시간 동안 돌려서 비교

주의: flush 방식은 "오래된 프레임을 버리고 최신 것만 보여주는" 트레이드오프라
실시간 미리보기(GET /api/stream/{cameraId})에만 적합함. 모든 프레임이 필요한
recordingService(이벤트 녹화)에는 적용하면 안 됨 — 거기는 지금처럼 프레임 유실 없이
전부 받아야 하는 경로라 이 스크립트의 결론을 그대로 옮기지 말 것.

실행(반드시 프로젝트 루트에서, backend venv 활성화 후):
    python debug/streaming/testRtspDelay.py --camera-id ELEV-TOP

.env의 CAMERA_SOURCE_<cameraId>가 설정돼 있어야 함(RTSP 시뮬레이션은
debug/streaming/startRtspSim.py 참고). 웹캠(정수 인덱스) 소스로도 동작은 하지만,
로컬 웹캠은 애초에 버퍼링이 거의 없어서 RTSP 소스로 테스트해야 의미가 있음.
"""
import argparse
import asyncio
import os
import sys
import time

from dotenv import load_dotenv

# Windows 콘솔 기본 코드페이지(cp949)는 "—" 같은 유니코드 문자를 못 담아
# UnicodeEncodeError로 죽으므로, stdout을 UTF-8로 강제.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_scriptDir = os.path.dirname(os.path.abspath(__file__))
_backendDir = os.path.join(
    _scriptDir, "..", "..", "WebApps", "backend"
)
_projectRootEnv = os.path.join(
    _scriptDir, "..", "..", ".env"
)

sys.path.insert(0, _backendDir)
load_dotenv(_projectRootEnv)

from schemas.event import CameraId  # noqa: E402
from streaming.cameraManager import (  # noqa: E402
    CameraManager,
    _envKeyForCameraId,
    _resolveCameraSource,
)


async def drainAndCount(
    capture,
    frameInterval: float,
    maxFlush: int = 200,
) -> int:
    """이미 쌓여서 곧바로(실시간 대기 없이) 꺼내지는 프레임 수를 센다."""
    count = 0

    while count < maxFlush:
        start = time.monotonic()
        grabbed = await asyncio.to_thread(capture.grab)
        elapsed = time.monotonic() - start

        if not grabbed:
            break

        count += 1

        if elapsed > frameInterval * 0.5:
            # 대기 없이 즉시 안 잡히고 다음 실시간 프레임을 기다렸다는 뜻
            # → 쌓여있던 프레임을 다 소진하고 라이브 edge에 도달
            break

    return count


async def readLatestFrame(capture, frameInterval: float):
    flushed = await drainAndCount(capture, frameInterval)
    ok, frame = await asyncio.to_thread(capture.retrieve)
    return (frame if ok else None), flushed


async def measureRawBacklog(
    source,
    label: str,
    fps: float,
    stallSeconds: float,
) -> None:
    manager = CameraManager(source, label=f"{label}-backlog")
    await manager.start()
    frameInterval = 1 / fps

    print(
        f"\n[{label}] {stallSeconds:.1f}초간 프레임을 안 읽고 방치..."
    )
    await asyncio.sleep(stallSeconds)

    flushed = await drainAndCount(manager.capture, frameInterval)
    estimatedMs = flushed / fps * 1000

    print(
        f"[{label}] 방치 직후 곧바로 꺼낼 수 있었던(이미 쌓여있던) "
        f"프레임 수: {flushed}  (약 {estimatedMs:.0f}ms 분량 지연 추정)"
    )

    if flushed >= 2:
        print(
            f"[{label}] → 2프레임 이상 쌓임 = CAP_PROP_BUFFERSIZE가 "
            "먹히지 않고 파이프 어딘가(ffmpeg 내부 큐/OS 소켓)에 "
            "버퍼링되고 있다는 뜻(병목형 지연 가능성 높음)"
        )
    else:
        print(
            f"[{label}] → 거의 안 쌓임 = 순수 버퍼링 문제보다는 "
            "인코딩/디코딩/CPU 처리 시간 자체가 느릴 가능성"
        )

    await manager.stop()


async def runConsumerLoop(
    source,
    label: str,
    mode: str,
    fps: float,
    runSeconds: float,
    processDelaySec: float,
) -> None:
    manager = CameraManager(source, label=f"{label}-{mode}")
    await manager.start()
    frameInterval = 1 / fps

    framesConsumed = 0
    totalFlushed = 0
    maxFlushed = 0
    start = time.monotonic()

    while time.monotonic() - start < runSeconds:
        if mode == "flush":
            frame, flushed = await readLatestFrame(
                manager.capture, frameInterval
            )
            totalFlushed += flushed
            maxFlushed = max(maxFlushed, flushed)
        else:
            ok, frame = await asyncio.to_thread(manager.capture.read)

        if frame is not None:
            framesConsumed += 1

        # 다운스트림 처리(JPEG 인코딩 + 탐지 등) 흉내
        await asyncio.sleep(processDelaySec)

    elapsed = time.monotonic() - start
    expectedFrames = elapsed * fps

    print(f"\n[{label}/{mode}] {elapsed:.1f}초 동안:")
    print(
        f"  처리한 프레임 수: {framesConsumed} "
        f"(소스 기준 예상 발생량: {expectedFrames:.0f})"
    )

    if mode == "flush":
        print(
            f"  매 처리마다 버려진(오래된) 프레임 — 평균 "
            f"{totalFlushed / max(framesConsumed, 1):.1f}개, "
            f"최대 {maxFlushed}개"
        )
        print(
            "  → 버려진 프레임 수만큼 '최신성'을 확보한 것. "
            "0에 가까우면 애초에 병목이 없었다는 뜻"
        )
    elif framesConsumed < expectedFrames * 0.9:
        print(
            "  → 처리 속도가 소스 발생 속도를 못 따라감. "
            "current 방식이면 이 차이가 그대로 화면 지연으로 누적됨"
        )

    await manager.stop()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--camera-id",
        default=CameraId.ELEVTOP.value,
        choices=[c.value for c in CameraId],
    )
    parser.add_argument("--fps", type=float, default=20.0)
    parser.add_argument("--stall-seconds", type=float, default=2.0)
    parser.add_argument("--run-seconds", type=float, default=10.0)
    parser.add_argument(
        "--process-delay-ms",
        type=float,
        default=100.0,
        help="다운스트림 처리(JPEG 인코딩+탐지 등)를 흉내내는 프레임당 인위적 지연",
    )
    args = parser.parse_args()

    source = _resolveCameraSource(
        _envKeyForCameraId(args.camera_id)
    )

    if source is None:
        print(
            f"[FAIL] {_envKeyForCameraId(args.camera_id)}가 .env에 없음 — "
            "debug/streaming/startRtspSim.py로 먼저 RTSP 송신을 띄우거나 "
            ".env에 값을 추가하세요"
        )
        sys.exit(1)

    print(f"=== 소스: {source} (cameraId={args.camera_id}) ===")

    print("\n--- 1단계: 방치 시 버퍼링 여부 측정 ---")
    await measureRawBacklog(
        source, args.camera_id, args.fps, args.stall_seconds
    )

    print(
        "\n--- 2단계: 느린 소비자 상황에서 current(현재) vs "
        "flush(수정안) 비교 ---"
    )
    processDelaySec = args.process_delay_ms / 1000

    await runConsumerLoop(
        source,
        args.camera_id,
        "current",
        args.fps,
        args.run_seconds,
        processDelaySec,
    )
    await runConsumerLoop(
        source,
        args.camera_id,
        "flush",
        args.fps,
        args.run_seconds,
        processDelaySec,
    )


if __name__ == "__main__":
    asyncio.run(main())
