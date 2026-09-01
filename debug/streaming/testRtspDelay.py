"""
RTSP 카메라(streaming/cameraManager.py, ffmpeg 서브프로세스 방식)의 프레임 전달
상태를 확인하는 디버그 스크립트.

이전 버전은 cv2.VideoCapture를 직접 잡고 grab()/retrieve() 타이밍으로 "방치 시
버퍼가 쌓이는지"를 측정했지만, 지금은 ffmpeg 서브프로세스가 백그라운드에서 항상
최신 프레임만 덮어써서 유지하므로(아무도 안 읽어도 버퍼가 안 쌓임) 그 측정 자체가
더 이상 의미가 없다. 대신 readFrame()을 반복 호출해서 실제로 프레임 내용이 얼마나
자주 바뀌는지(체감 전달 fps)와 연결이 얼마나 빨리 열리는지를 확인한다.

실행(반드시 프로젝트 루트에서, backend venv 활성화 후):
    python debug/streaming/testRtspDelay.py --camera-id ELEV-TOP

.env의 CAMERA_SOURCE_<cameraId>가 설정돼 있어야 함(RTSP 시뮬레이션은
debug/streaming/startRtspSim.py 참고).
"""
import argparse
import asyncio
import os
import sys
import time

from dotenv import load_dotenv

# Windows 콘솔 기본 코드페이지(cp949)는 유니코드 특수문자를 못 담아
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


async def measureDeliveryRate(
    manager: CameraManager,
    durationSeconds: float,
) -> None:
    lastFrame = None
    frameChanges = 0
    changeTimestamps = []
    start = time.monotonic()

    while time.monotonic() - start < durationSeconds:
        frame = await manager.readFrame()

        if frame is not None and frame != lastFrame:
            frameChanges += 1
            changeTimestamps.append(time.monotonic())
            lastFrame = frame

        await asyncio.sleep(0.01)

    elapsed = time.monotonic() - start

    print(
        f"[{manager.label}] {elapsed:.1f}초 동안 서로 다른 프레임 "
        f"{frameChanges}개 수신 (체감 전달 fps ≈ {frameChanges / elapsed:.1f})"
    )

    if len(changeTimestamps) < 2:
        print(
            f"[{manager.label}] → 프레임이 거의/전혀 안 바뀜 — 연결 상태를 "
            "확인해보세요"
        )
        return

    gaps = [
        b - a
        for a, b in zip(changeTimestamps, changeTimestamps[1:])
    ]
    avgGap = sum(gaps) / len(gaps)
    maxGap = max(gaps)

    print(
        f"[{manager.label}] 프레임 간 간격 — 평균 {avgGap * 1000:.0f}ms, "
        f"최대 {maxGap * 1000:.0f}ms"
    )

    if maxGap > 1.0:
        print(
            f"[{manager.label}] → 최대 간격이 1초 이상 — 그 구간에 재연결"
            "(크래시/네트워크 유실)이 있었을 가능성. 백엔드 콘솔 로그도 "
            "같이 확인해보세요"
        )


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
    parser.add_argument(
        "--duration-seconds", type=float, default=10.0
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

    manager = CameraManager(source, label=args.camera_id)

    openStart = time.monotonic()

    try:
        await manager.start()
    except RuntimeError as error:
        print(f"[FAIL] 연결 실패: {error}")
        sys.exit(1)

    print(
        f"[{args.camera_id}] 연결 성공까지 "
        f"{time.monotonic() - openStart:.2f}초"
    )

    await measureDeliveryRate(manager, args.duration_seconds)

    await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
