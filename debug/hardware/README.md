# Raspberry Pi speaker test

This tool verifies the Raspberry Pi speaker and ALSA output. It generates two
short 880 Hz beeps, so no audio asset is required.

## Run

```bash
sudo apt install alsa-utils
python3 debug/hardware/testSpeaker.py
```

If no sound is played, list the available devices:

```bash
python3 debug/hardware/testSpeaker.py --listDevices
aplay -L
```

Specify a USB speaker by its ALSA card name when necessary:

```bash
python3 debug/hardware/testSpeaker.py --device plughw:CARD=Device,DEV=0
alsamixer
```

The command above verifies speaker output only. Use the listener below to
connect that output to backend events.

## Test a real misclassification event

Create a small virtual environment on the Raspberry Pi and install the
WebSocket client:

```bash
python3 -m venv .venv-alert
source .venv-alert/bin/activate
pip install websocket-client
```

Start the listener with the LAN address of the backend:

```bash
python3 debug/hardware/alertListener.py \
  --webSocketUrl ws://<LOCAL_BACKEND_IP>:8047/ws/events
```

If the USB speaker is not the default ALSA output, also pass `--device`:

```bash
python3 debug/hardware/alertListener.py \
  --webSocketUrl ws://<LOCAL_BACKEND_IP>:8047/ws/events \
  --device plughw:CARD=Device,DEV=0
```

The listener ignores mode, overflow, and other messages. It plays the generated
tone only when it receives `MISCLASSIFICATION_DETECTED` with
`isMisclassified=true`. The backend emits that message only when it is in
`MANAGE` mode and a new misclassification event is stored. Press Ctrl+C to
stop the listener.
