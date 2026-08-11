"""
젯슨 나노 도착 전, 이 PC의 웹캠 2대(위+옆)로 RTSP 송신을 흉내내는 로컬 테스트 도구.
infra/checkEnv.py처럼 필요한 것(FFmpeg/MediaMTX)을 자동으로 확인+설치하고,
카메라 장치도 자동으로 찾아서 MediaMTX + FFmpeg 송신을 바로 띄운다.

실제 배포 시엔 젯슨 나노가 이 역할(GStreamer RTSP 서버)을 대신하므로, 이 스크립트는
WebApps/backend·docker-compose.yml과 무관한 로컬 테스트 전용 — 카메라를 든 쪽(현재는
이 PC, 나중엔 젯슨 나노)의 역할만 흉내낸다. 백엔드(streaming/cameraManager.py)는
RTSP URL을 받기만 하면 되므로 수정 불필요.

실행:
    python startRtspSim.py

Windows 전용(DirectShow 기반).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

mediaMtxDir = os.path.join(os.environ["LOCALAPPDATA"], "mediamtx")
mediaMtxExe = os.path.join(mediaMtxDir, "mediamtx.exe")
rtspPort = 8554


def _refreshPathFromRegistry() -> None:
    # winget이 PATH를 갱신해도 이미 떠 있는 프로세스(이 스크립트)의 환경변수엔
    # 반영이 안 되므로, 레지스트리에서 최신 PATH를 읽어와 현재 프로세스에 덧붙임.
    for scope in ("Machine", "User"):
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f"[System.Environment]::GetEnvironmentVariable('Path','{scope}')",
            ],
            capture_output=True,
            text=True,
        )

        pathValue = result.stdout.strip()

        if pathValue:
            os.environ["PATH"] = (
                os.environ.get("PATH", "") + os.pathsep + pathValue
            )


def checkFfmpeg() -> str | None:
    ffmpegPath = shutil.which("ffmpeg")

    if ffmpegPath:
        print(f"[OK ] ffmpeg 확인됨: {ffmpegPath}")
        return ffmpegPath

    print("[--- ] ffmpeg 미설치 → winget으로 설치 시도")

    subprocess.run(
        [
            "winget", "install", "--id", "Gyan.FFmpeg", "-e",
            "--accept-source-agreements", "--accept-package-agreements",
        ],
    )

    _refreshPathFromRegistry()
    ffmpegPath = shutil.which("ffmpeg")

    if ffmpegPath:
        print(f"[OK ] ffmpeg 설치 확인됨: {ffmpegPath}")
        return ffmpegPath

    print(
        "[FAIL] ffmpeg를 찾지 못함 - 터미널을 완전히 재시작한 뒤 다시 실행하세요"
    )
    return None


def ensureMediaMtx() -> bool:
    if os.path.exists(mediaMtxExe):
        print(f"[OK ] MediaMTX 확인됨: {mediaMtxExe}")
        return True

    print("[--- ] MediaMTX 미설치 → GitHub 최신 릴리스 자동 설치")
    os.makedirs(mediaMtxDir, exist_ok=True)

    with urllib.request.urlopen(
        "https://api.github.com/repos/bluenviron/mediamtx/releases/latest"
    ) as response:
        release = json.load(response)

    asset = next(
        (
            a for a in release["assets"]
            if a["name"].endswith("windows_amd64.zip")
        ),
        None,
    )

    if asset is None:
        print("[FAIL] Windows용 MediaMTX 릴리스를 찾지 못함")
        return False

    zipPath = os.path.join(mediaMtxDir, "mediamtx.zip")
    print(f"      다운로드 중: {asset['browser_download_url']}")
    urllib.request.urlretrieve(asset["browser_download_url"], zipPath)

    with zipfile.ZipFile(zipPath) as zf:
        zf.extractall(mediaMtxDir)

    os.remove(zipPath)
    print(f"[OK ] 설치 완료: {mediaMtxExe}")
    return True


def listDshowCameras(ffmpegPath: str) -> list[str]:
    # ffmpeg는 장치명을 UTF-8로 출력하므로(한글 장치명 포함),
    # Windows 기본 로케일 인코딩(cp949)이 아니라 명시적으로 utf-8로 읽어야 함.
    result = subprocess.run(
        [ffmpegPath, "-f", "dshow", "-list_devices", "true", "-i", "dummy"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    return re.findall(r'"([^"]+)"\s*\(video\)', result.stderr)


def chooseCameras(cameras: list[str]) -> tuple[str, str]:
    print("\n감지된 카메라:")

    for i, name in enumerate(cameras):
        print(f"  [{i}] {name}")

    topIndex = int(input("\n위(top) 카메라 번호 입력: "))
    sideIndex = int(input("옆(side) 카메라 번호 입력: "))

    return cameras[topIndex], cameras[sideIndex]


def startFfmpegPush(
    ffmpegPath: str,
    cameraName: str,
    rtspPath: str,
) -> subprocess.Popen:
    command = [
        ffmpegPath,
        "-f", "dshow",
        "-rtbufsize", "200M",
        "-framerate", "20",
        "-i", f"video={cameraName}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-g", "40",
        "-rtsp_transport", "tcp",
        "-f", "rtsp",
        f"rtsp://localhost:{rtspPort}/{rtspPath}",
    ]

    return subprocess.Popen(
        command,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def main():
    print("=== 1. FFmpeg 확인 ===")
    ffmpegPath = checkFfmpeg()

    if ffmpegPath is None:
        sys.exit(1)

    print("\n=== 2. MediaMTX 확인/설치 ===")

    if not ensureMediaMtx():
        sys.exit(1)

    print("\n=== 3. 카메라 장치 감지 ===")
    cameras = listDshowCameras(ffmpegPath)

    if len(cameras) < 2:
        print(
            f"[FAIL] 카메라가 {len(cameras)}개만 감지됨(2개 필요): {cameras}"
        )
        sys.exit(1)

    topCamera, sideCamera = chooseCameras(cameras)

    print("\n=== 4. MediaMTX 실행 ===")
    mediaMtxProcess = subprocess.Popen(
        [mediaMtxExe],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    time.sleep(2)

    print("=== 5. FFmpeg 송신 시작 ===")
    topProcess = startFfmpegPush(ffmpegPath, topCamera, "top")
    sideProcess = startFfmpegPush(ffmpegPath, sideCamera, "side")

    print(f"""
완료. .env에 아래 두 줄을 추가하세요:
  CAMERA_SOURCE=rtsp://localhost:{rtspPort}/top
  CAMERA_SOURCE_SIDE=rtsp://localhost:{rtspPort}/side

종료하려면 이 창에서 Ctrl+C
""")

    try:
        mediaMtxProcess.wait()
    except KeyboardInterrupt:
        print("\n종료 중...")

        for process in (mediaMtxProcess, topProcess, sideProcess):
            process.terminate()


if __name__ == "__main__":
    main()
