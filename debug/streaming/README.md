# 젯슨 나노 RTSP 시뮬레이션 (로컬 테스트용)

젯슨 나노 입고 전, 이 PC의 웹캠 2대(위+옆)로 젯슨 나노가 나중에 할 역할(캡처+RTSP 송신)을
흉내내서 백엔드가 RTSP를 정상적으로 받아오는지 미리 테스트하기 위한 도구.

**주의**: 여기서 쓰는 FFmpeg/MediaMTX는 "카메라를 든 쪽"(현재는 이 PC, 나중엔 젯슨 나노) 역할이라
`WebApps/backend`나 `docker-compose.yml`에는 포함되지 않음. 백엔드는 원래 설계대로 RTSP URL만
받아서 열면 됨(`cv2.VideoCapture`가 RTSP 문자열도 그대로 처리 — 백엔드 코드 수정 불필요).

## 사용법

```bash
python startRtspSim.py
```

`infra/checkEnv.py`처럼 필요한 것들을 자동으로 확인·설치한다:

1. **FFmpeg** — 없으면 `winget install --id Gyan.FFmpeg -e`로 자동 설치
2. **MediaMTX** — 없으면 GitHub 최신 릴리스를 자동 다운로드(`%LOCALAPPDATA%\mediamtx\`)
3. **카메라 장치** — `ffmpeg -f dshow -list_devices`로 자동 감지해서 목록 출력,
   위(top)/옆(side) 카메라 번호만 입력하면 됨
4. MediaMTX + FFmpeg 송신(위/옆) 자동 실행

완료되면 `.env`에 추가할 두 줄을 화면에 출력해준다:

```
CAMERA_SOURCE=rtsp://localhost:8554/top
CAMERA_SOURCE_SIDE=rtsp://localhost:8554/side
```

종료는 스크립트를 실행한 창에서 `Ctrl+C`(MediaMTX/FFmpeg 프로세스까지 같이 종료됨).

## 주의사항

- **FFmpeg를 방금 처음 설치했다면 터미널을 재시작하고 다시 실행**해야 함(winget이 PATH를
  갱신해도 이미 열려있는 터미널엔 반영 안 됨)
- 카메라가 1개뿐이면(예: 노트북 내장캠만 있는 경우) 2개 미만 감지로 실패함 — 정상 동작.
  실제 2대 연결된 PC에서 실행할 것
- Windows 전용(DirectShow 기반)

## 확인 후 백엔드 실행

```bash
cd WebApps/backend
uvicorn main:app --reload --port 8047
```

`http://localhost:8047/`에서 위/옆 2분할 화면이 RTSP 경유로 정상 표시되면 성공.

## 참고

- MediaMTX 기본 RTSP 포트는 8554(변경 가능하나 바꿀 이유 없음)
- 실제 배포 시엔 젯슨 나노가 자체 RTSP 서버(GStreamer, JetPack 기본 포함)를 띄우므로 이 절차
  전체가 불필요해짐 — `.env`의 `CAMERA_SOURCE`/`CAMERA_SOURCE_SIDE`만 젯슨 나노 IP로 교체
- FFmpeg 인코딩 옵션(`ultrafast`/`zerolatency`/GOP 40 등)은 팀원이 실측으로 찾은 안정화 설정
  (H264 corrupted macroblock, frame duplication 문제 해결 이력 있음)
