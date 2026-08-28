"""Generate and play a short speaker test tone on Raspberry Pi OS."""

from __future__ import annotations

import argparse
import math
import shutil
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play an ALSA speaker test tone.")
    parser.add_argument("--device", help="ALSA device, e.g. plughw:CARD=Device,DEV=0")
    parser.add_argument("--frequency", type=float, default=880.0)
    parser.add_argument("--duration", type=float, default=0.5)
    parser.add_argument("--volume", type=float, default=0.35)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--listDevices", action="store_true")
    return parser.parse_args()


def validateArgs(args: argparse.Namespace) -> None:
    if not 20.0 <= args.frequency <= 20_000.0:
        raise ValueError("frequency must be between 20 and 20000 Hz")
    if not 0.05 <= args.duration <= 10.0:
        raise ValueError("duration must be between 0.05 and 10 seconds")
    if not 0.0 <= args.volume <= 1.0:
        raise ValueError("volume must be between 0.0 and 1.0")
    if not 1 <= args.repeat <= 20:
        raise ValueError("repeat must be between 1 and 20")
    if not 0.0 <= args.interval <= 10.0:
        raise ValueError("interval must be between 0 and 10 seconds")


def writeTone(wavPath: Path, frequency: float, duration: float, volume: float) -> None:
    sampleRate = 44_100
    sampleCount = int(sampleRate * duration)
    fadeSampleCount = min(int(sampleRate * 0.01), sampleCount // 2)

    with wave.open(str(wavPath), "wb") as wavFile:
        wavFile.setnchannels(1)
        wavFile.setsampwidth(2)
        wavFile.setframerate(sampleRate)
        for sampleIndex in range(sampleCount):
            fade = min(
                1.0,
                sampleIndex / fadeSampleCount,
                (sampleCount - sampleIndex - 1) / fadeSampleCount,
            )
            sample = math.sin(2.0 * math.pi * frequency * sampleIndex / sampleRate)
            wavFile.writeframesraw(struct.pack("<h", int(32_767 * volume * fade * sample)))


def playTone(wavPath: Path, device: str | None) -> None:
    command = ["aplay", "-q"]
    if device:
        command.extend(["-D", device])
    subprocess.run([*command, str(wavPath)], check=True)


def main() -> int:
    args = parseArgs()
    if shutil.which("aplay") is None:
        print("aplay was not found. Install it with: sudo apt install alsa-utils")
        return 1
    if args.listDevices:
        return subprocess.run(["aplay", "-l"], check=False).returncode

    try:
        validateArgs(args)
    except ValueError as error:
        print(f"Invalid option: {error}")
        return 2

    wavPath: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="sortMasterSpeakerTest-", suffix=".wav", delete=False
        ) as wavFile:
            wavPath = Path(wavFile.name)
        writeTone(wavPath, args.frequency, args.duration, args.volume)
        for repeatIndex in range(args.repeat):
            playTone(wavPath, args.device)
            if repeatIndex + 1 < args.repeat:
                time.sleep(args.interval)
    except subprocess.CalledProcessError as error:
        print(f"Playback failed ({error.returncode}). Check --listDevices.")
        return error.returncode or 1
    finally:
        if wavPath is not None:
            wavPath.unlink(missing_ok=True)

    print("Speaker test tone playback completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
