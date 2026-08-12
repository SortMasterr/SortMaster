# 젯슨 나노 RTSP 시뮬레이션 (로컬 테스트용)

젯슨 나노 입고 전, 이 PC의 웹캠 여러 대를 각각 다른 지점(`CameraId`)에 할당해서, 지점마다
독립된 젯슨 나노가 나중에 할 역할(캡처+RTSP 송신)을 흉내내는 도구. 카메라 1대 = 지점 1개 =
`CameraId` 1개 구성(architecture.md 참고).

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
3. **카메라 장치** — `ffmpeg -f dshow -list_devices`로 자동 감지해서 목록 출력. 감지된
   카메라마다 어느 지점(`ELEV-01`/`ELEV-02`/`REST-4F-01`)인지 번호로 선택(카메라가 1대뿐이면
   1개만 할당해도 됨, Enter만 누르면 할당 종료)
4. MediaMTX + 할당한 카메라 수만큼 FFmpeg 송신 자동 실행

완료되면 `.env`에 추가할 줄을 화면에 출력해준다(할당한 지점 수만큼):

```
CAMERA_SOURCE_ELEV01=rtsp://localhost:8554/ELEV-01
CAMERA_SOURCE_ELEV02=rtsp://localhost:8554/ELEV-02
```

종료는 스크립트를 실행한 창에서 `Ctrl+C`(MediaMTX/FFmpeg 프로세스까지 같이 종료됨).

## 주의사항

- **FFmpeg를 방금 처음 설치했다면 터미널을 재시작하고 다시 실행**해야 함(winget이 PATH를
  갱신해도 이미 열려있는 터미널엔 반영 안 됨)
- 카메라 모델이 같으면 장치 이름이 똑같이 나올 수 있음(예: 같은 제품 2대) — 내부적으로는
  장치 고유 경로로 구분해서 열기 때문에 문제없지만, 어느 번호가 어느 물리 카메라인지는
  화면 가리기 등으로 직접 구분해야 함
- 카메라가 1개뿐이면(예: 노트북 내장캠만 있는 경우) 지점 1개만 할당하고 테스트 가능
- Windows 전용(DirectShow 기반)
- 문제 생기면 `logs/` 폴더의 `mediamtx.log`, `ffmpeg_<cameraId>.log` 확인(자동 생성, git에는 안 올라감)

## 확인 후 백엔드 실행

```bash
cd WebApps/backend
uvicorn main:app --reload --port 8047
```

`http://localhost:8047/`에서 할당한 지점들의 화면이 RTSP 경유로 정상 표시되면 성공.

## 참고

- MediaMTX 기본 RTSP 포트는 8554(변경 가능하나 바꿀 이유 없음)
- 실제 배포 시엔 젯슨 나노가 자체 RTSP 서버(GStreamer, JetPack 기본 포함)를 띄우므로 이 절차
  전체가 불필요해짐 — `.env`의 `CAMERA_SOURCE_<CameraId>`만 해당 젯슨 나노 IP로 교체
- FFmpeg 인코딩 옵션(`ultrafast`/`zerolatency`/GOP 40 등)은 팀원이 실측으로 찾은 안정화 설정
  (H264 corrupted macroblock, frame duplication 문제 해결 이력 있음)
