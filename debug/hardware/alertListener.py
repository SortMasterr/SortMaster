"""Play a Raspberry Pi speaker alert for backend misclassification events."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from testSpeaker import playTone, validateArgs, writeTone


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Listen for SortMaster misclassification events and play a tone."
    )
    parser.add_argument(
        "--webSocketUrl",
        required=True,
        help="Backend WebSocket URL, e.g. ws://192.168.0.10:8047/ws/events",
    )
    parser.add_argument("--device", help="Optional ALSA output device.")
    parser.add_argument("--frequency", type=float, default=880.0)
    parser.add_argument("--duration", type=float, default=0.5)
    parser.add_argument("--volume", type=float, default=0.35)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--reconnectDelay", type=float, default=3.0)
    return parser.parse_args()


def playAlert(wavPath: Path, device: str | None, repeat: int, interval: float) -> None:
    for repeatIndex in range(repeat):
        playTone(wavPath, device)
        if repeatIndex + 1 < repeat:
            time.sleep(interval)


def handleMessage(
    rawMessage: str,
    wavPath: Path,
    device: str | None,
    repeat: int,
    interval: float,
) -> bool:
    try:
        message = json.loads(rawMessage)
    except json.JSONDecodeError:
        print(f"[ALERT] Ignored invalid JSON: {rawMessage!r}", flush=True)
        return False

    eventType = message.get("eventType")
    print(f"[WEBSOCKET] eventType={eventType}", flush=True)

    if (
        eventType != "MISCLASSIFICATION_DETECTED"
        or message.get("isMisclassified") is not True
    ):
        return False

    print(
        f"[ALERT] Misclassification detected: cameraId={message.get('cameraId')}, "
        f"timestamp={message.get('timestamp')}",
        flush=True,
    )
    playAlert(wavPath, device, repeat, interval)
    print("[ALERT] Speaker playback completed.", flush=True)
    return True


def listen(args: argparse.Namespace, wavPath: Path) -> int:
    try:
        import websocket
    except ImportError:
        print("websocket-client is required. Install it with: pip install websocket-client")
        return 1

    while True:
        connection = None
        try:
            print(f"[WEBSOCKET] Connecting to {args.webSocketUrl}", flush=True)
            connection = websocket.create_connection(args.webSocketUrl, timeout=10)
            connection.settimeout(None)
            print("[WEBSOCKET] Connected.", flush=True)

            while True:
                rawMessage = connection.recv()
                if not rawMessage:
                    raise ConnectionError("WebSocket connection closed")
                handleMessage(
                    rawMessage,
                    wavPath,
                    args.device,
                    args.repeat,
                    args.interval,
                )
        except KeyboardInterrupt:
            print("\n[WEBSOCKET] Listener stopped.", flush=True)
            return 0
        except Exception as error:
            print(
                f"[WEBSOCKET] Connection error: {error}. "
                f"Retrying in {args.reconnectDelay:.1f}s.",
                flush=True,
            )
            time.sleep(args.reconnectDelay)
        finally:
            if connection is not None:
                connection.close()


def main() -> int:
    args = parseArgs()
    if shutil.which("aplay") is None:
        print("aplay was not found. Install it with: sudo apt install alsa-utils")
        return 1
    try:
        validateArgs(args)
    except ValueError as error:
        print(f"Invalid option: {error}")
        return 2
    if args.reconnectDelay < 0:
        print("reconnectDelay must not be negative.")
        return 2

    wavPath: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="sortMasterAlert-", suffix=".wav", delete=False
        ) as wavFile:
            wavPath = Path(wavFile.name)
        writeTone(wavPath, args.frequency, args.duration, args.volume)
        return listen(args, wavPath)
    finally:
        if wavPath is not None:
            wavPath.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
