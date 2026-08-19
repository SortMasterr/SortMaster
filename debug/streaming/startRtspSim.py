"""
라즈베리파이 도착 전, 이 PC의 웹캠들로 RTSP 송신을 흉내내는 로컬 테스트 도구.
지점(CameraId)당 독립 라즈베리파이 1대+카메라 1대 구성(architecture.md 참고) —
카메라 여러 대를 각각 다른 지점(ELEV-TOP, ELEV-SIDE 등)에 할당해서 동시에 RTSP로 송신.
infra/checkEnv.py처럼 필요한 것(FFmpeg/MediaMTX)을 자동으로 확인+설치하고,
카메라 장치도 자동으로 찾아서 MediaMTX + FFmpeg 송신을 바로 띄운다.

실제 배포 시엔 각 지점의 라즈베리파이가 이 역할(GStreamer RTSP 서버)을 대신하므로,
이 스크립트는 WebApps/backend·docker-compose.yml과 무관한 로컬 테스트 전용 —
카메라를 든 쪽(현재는 이 PC, 나중엔 라즈베리파이)의 역할만 흉내낸다.
백엔드(streaming/cameraManager.py)는 RTSP URL을 받기만 하면 되므로 수정 불필요.

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


def listDshowCameras(ffmpegPath: str) -> list[tuple[str, str]]:
    # ffmpeg는 장치명을 UTF-8로 출력하므로(한글 장치명 포함),
    # Windows 기본 로케일 인코딩(cp949)이 아니라 명시적으로 utf-8로 읽어야 함.
    result = subprocess.run(
        [ffmpegPath, "-f", "dshow", "-list_devices", "true", "-i", "dummy"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    lines = result.stderr.splitlines()
    cameras = []

    for i, line in enumerate(lines):
        nameMatch = re.search(r'"([^"]+)"\s*\(video\)', line)

        if not nameMatch:
            continue

        friendlyName = nameMatch.group(1)
        # 카메라 모델이 같으면 friendlyName이 똑같아서(예: "ABKO APC480 SD WEBCAM"
        # 이 2개), 이름만으로 열면 둘 다 같은 물리 장치로 열려서 충돌남 — 장치별로
        # 고유한 "Alternative name"(다음 줄)을 실제 -i 값으로 써서 구분해야 함.
        altName = friendlyName

        if i + 1 < len(lines):
            altMatch = re.search(r'Alternative name "([^"]+)"', lines[i + 1])

            if altMatch:
                altName = altMatch.group(1)

        cameras.append((friendlyName, altName))

    return cameras


# schemas/event.py의 CameraId 값과 동일하게 유지 — 지점당 독립 라즈베리파이+카메라 1대.
cameraIdChoices = ["ELEV-TOP", "ELEV-SIDE", "REST-4F-01"]


def chooseCameraAssignments(
    cameras: list[tuple[str, str]],
) -> dict[str, str]:
    print("\n감지된 카메라:")

    for i, (friendlyName, _) in enumerate(cameras):
        print(f"  [{i}] {friendlyName}")

    print(
        "(이름이 똑같이 나오면 실제로는 다른 물리 장치일 수 있음 — "
        "화면 가리기 등으로 직접 구분 필요)"
    )

    print("\n지점(cameraId) 후보:")

    for i, cameraId in enumerate(cameraIdChoices):
        print(f"  [{i}] {cameraId}")

    assignments: dict[str, str] = {}

    while True:
        raw = input(
            "\n카메라 번호 입력(할당 다 끝났으면 Enter만): "
        ).strip()

        if raw == "":
            break

        cameraIndex = int(raw)
        idRaw = input("  → 어느 지점인가요(위 목록 번호): ").strip()
        cameraId = cameraIdChoices[int(idRaw)]

        assignments[cameraId] = cameras[cameraIndex][1]
        print(f"  [OK] {cameraId} = {cameras[cameraIndex][0]}")

    return assignments


logDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


def startFfmpegPush(
    ffmpegPath: str,
    cameraName: str,
    rtspPath: str,
) -> tuple[subprocess.Popen, str]:
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

    os.makedirs(logDir, exist_ok=True)
    logPath = os.path.join(logDir, f"ffmpeg_{rtspPath}.log")
    logFile = open(logPath, "w", encoding="utf-8", errors="replace")

    process = subprocess.Popen(
        command,
        stdout=logFile,
        stderr=subprocess.STDOUT,
    )

    return process, logPath


def checkAlive(
    process: subprocess.Popen,
    label: str,
    logPath: str,
) -> None:
    # FFmpeg가 창 없이 백그라운드로 뜨기 때문에, 바로 죽었는지 확인해서
    # 로그를 즉시 보여줌(창이 순식간에 닫혀서 에러를 못 보는 문제 방지).
    time.sleep(2)

    if process.poll() is not None:
        print(f"[FAIL] {label} 프로세스가 바로 종료됨(exit {process.returncode})")
        print(f"       로그: {logPath}")

        with open(logPath, encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-15:]

        print("".join(tail))
    else:
        print(f"[OK ] {label} 정상 실행 중 (로그: {logPath})")


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

    if len(cameras) < 1:
        print("[FAIL] 카메라가 감지되지 않음")
        sys.exit(1)

    assignments = chooseCameraAssignments(cameras)

    if not assignments:
        print("[FAIL] 지점에 할당된 카메라가 없음")
        sys.exit(1)

    print("\n=== 4. MediaMTX 실행 ===")
    os.makedirs(logDir, exist_ok=True)
    mediaMtxLog = os.path.join(logDir, "mediamtx.log")
    mediaMtxLogFile = open(mediaMtxLog, "w", encoding="utf-8", errors="replace")

    mediaMtxProcess = subprocess.Popen(
        [mediaMtxExe],
        cwd=mediaMtxDir,  # mediamtx.yml을 설치 폴더 기준으로 찾게 함
        stdout=mediaMtxLogFile,
        stderr=subprocess.STDOUT,
    )
    print(f"      로그: {mediaMtxLog}")
    time.sleep(2)

    if mediaMtxProcess.poll() is not None:
        print(
            f"[FAIL] MediaMTX가 바로 종료됨(exit {mediaMtxProcess.returncode}) "
            "— 이미 다른 MediaMTX가 8554 포트를 쓰고 있을 수 있음(작업관리자에서 "
            "mediamtx.exe 중복 실행 확인)"
        )

        with open(mediaMtxLog, encoding="utf-8", errors="replace") as f:
            print("".join(f.readlines()[-15:]))

        sys.exit(1)

    print("=== 5. FFmpeg 송신 시작 ===")
    ffmpegProcesses = []

    for cameraId, altName in assignments.items():
        process, logPath = startFfmpegPush(ffmpegPath, altName, cameraId)
        checkAlive(process, cameraId, logPath)
        ffmpegProcesses.append(process)

    envLines = "\n".join(
        # streaming/cameraManager.py의 _envKeyForCameraId와 동일한 규칙
        f"  CAMERA_SOURCE_{cameraId.replace('-', '').upper()}="
        f"rtsp://localhost:{rtspPort}/{cameraId}"
        for cameraId in assignments
    )

    print(f"""
완료. .env에 아래 줄을 추가하세요:
{envLines}

종료하려면 이 창에서 Ctrl+C
""")

    try:
        mediaMtxProcess.wait()
    except KeyboardInterrupt:
        print("\n종료 중...")

        for process in (mediaMtxProcess, *ffmpegProcesses):
            process.terminate()


if __name__ == "__main__":
    main()
