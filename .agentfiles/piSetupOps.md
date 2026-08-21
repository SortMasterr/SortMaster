# piSetupOps.md

라즈베리파이(메인보드) 실기기 셋업 실전 절차/트러블슈팅. `architecture.md`가 "뭘 하기로
했는지"라면 이 문서는 "실제로 어떻게 하는지"(`gpuServerOps.md`와 같은 성격). **자동 로드
안 함** — 라즈베리파이 셋업/재현이 필요할 때만 열어볼 것.

## SD카드 굽기 (Raspberry Pi Imager)

- OS: Raspberry Pi OS 64-bit (Bookworm 이후 cloud-init 기반, NoCloud datasource)
- 사용자 지정(⚙️)에서 호스트이름/계정/SSH/Wi-Fi 미리 설정 → 완전 헤드리스 부팅 가능(모니터/키보드 불필요)
- 지점(`CameraId`)당 보드 1대 원칙 유지 — 호스트이름은 `elev-top`/`elev-side`처럼 카메라
  지점명과 맞춤(계정명은 GPU 서버 팀 계정과 헷갈리지 않게 별도로, 예: `sortmaster`)
- sudo는 기본 `null`(권한 없음)로 구워짐 — 패키지 설치 등 필요하면 Imager 설정 단계에서
  `ALL=(ALL) NOPASSWD:ALL`로 직접 지정해야 함

## cloud-init 설정 파일 위치

SD카드를 PC에 꽂으면 `bootfs`라는 이름의 FAT32 파티션만 드라이브로 보임(리눅스 rootfs
파티션은 Windows에서 안 보이는 게 정상). 이 안에 cloud-init 설정이 평문으로 들어있어서
Windows에서 바로 읽고 쓸 수 있음:

- `user-data` — hostname/user/ssh/write_files/runcmd 등 cloud-config 본문
- `meta-data` — `instance-id: ...` (이 값이 바뀌어야 cloud-init이 "새 인스턴스"로 보고
  `user-data`를 다시 처리함)
- `network-config` — Wi-Fi SSID/비밀번호 등
- `cmdline.txt` — 커널 부팅 파라미터. **여기에도 `ds=nocloud;i=<instance-id>`로 instance-id가
  하드코딩돼 있음**

## 함정: user-data 수정해도 재부팅 시 반영이 안 될 때

`meta-data`의 `instance-id`만 바꿔서 cloud-init이 재처리하게 하려 했는데 안 먹혔던 사례 있음
(write_files로 넣은 파일이 재부팅해도 안 생김). **원인: `cmdline.txt`의
`ds=nocloud;i=<instance-id>`가 `meta-data`보다 우선 적용됨** — 이것도 같이 안 바꾸면
cloud-init이 여전히 "이미 처리한 인스턴스"로 착각하고 `write_files`/`runcmd`를 건너뜀.

→ `user-data`를 고쳐서 재부팅 시 반영하고 싶으면 **`meta-data`와 `cmdline.txt` 두 곳의
instance-id를 동일한 새 값으로 같이 바꿀 것**. 그리고 SD카드만 바꿔 끼우는 걸로는 반영
안 됨 — **전원을 완전히 껐다 켜야** 새 부팅이 시작됨(전원 유지한 채 카드만 교체하는 건
무의미).

## rootfs(ext4) 로그 확인 방법

Windows는 ext4 파일시스템을 못 읽어서 `/var/log/cloud-init*.log`, `/etc/ssh/` 등은 바로
확인 불가. 시도해본 방법들:

- **`wsl --mount`(관리자 권한 필요)**: 카드리더 종류에 따라 Hyper-V가 디스크를 못 넘겨받는
  경우 있음(`0x8007000f` 에러) — 리더 하드웨어 한계로 실패한 사례 있음, 안 되면 아래로
- **DiskInternals Linux Reader(무료, Windows GUI)**: 관리자 권한 불필요, ext4 파티션을
  탐색기처럼 읽기 전용으로 볼 수 있음 — **이 방법으로 성공**. `cloud-init-output.log`,
  `/etc/ssh/sshd_config.d/` 등 확인할 때 사용. 파일 쓰기(수정)는 안 됨 — 설정 변경은
  `bootfs`(FAT32) 쪽 `user-data`를 고쳐서 재부팅으로 반영하는 방식으로 우회

## Wi-Fi 5GHz 대역에서 SSH 접속 불안정

학원 공유 네트워크에서 노트북이 **5GHz 대역**에 붙어있을 때 라즈베리파이 SSH가 배너 교환
직전에 계속 끊기는 증상 발생(`kex_exchange_identification: Connection closed by remote
host`), mDNS(`.local`)도 엉뚱한 IP로 잘못 풀림. **2.4GHz 대역으로 전환하니 즉시 정상화**됨
(SSH 접속 성공, `.local` 정상 해석). 정확한 메커니즘(공유기의 대역별 VLAN 분리 추정)은
확인 안 됐지만, **재현성 있게 확인된 증상**이라 접속 안 될 때 가장 먼저 확인할 것.

## SSH 포트 2222 fallback

22번이 막힌 걸로 오인했던 시행착오 중에 `sshd_config.d/port.conf`로 2222도 같이 열어두는
작업을 해둠(`Port 22` / `Port 2222` 둘 다 리스닝). 실제 원인은 위 Wi-Fi 대역 문제였을
가능성이 높지만(2.4G에선 22도 정상 동작 확인됨), 2222도 열려있어서 나쁠 건 없어 유지 —
GPU 서버(`gpuServerOps.md`)와 마찬가지로 22 안 되면 2222로도 시도해볼 것.

## USB 웹캠 (테스트용, ABKO APC480)

- `/dev/video0`, 지원 포맷은 **YUYV(무압축) 640x480뿐, MJPEG 없음**(저가형 웹캠이라
  하드웨어 압축 자체가 없음 — 카메라 스펙에 따라 다름, 다른 모델이면 재확인 필요)
- 확인: `v4l2-ctl -d /dev/video0 --list-formats-ext`
- 640x480 무압축이면 대역폭은 문제없는 수준(초당 ~12MB), CPU(libx264 소프트웨어 인코딩)도
  40%대로 여유 있었음

## RTSP 송신 구조 (MediaMTX + ffmpeg push)

Windows 시뮬레이터(`debug/streaming/startRtspSim.py`)와 동일한 패턴을 라즈베리파이에서도
그대로 사용 — 캡처 백엔드만 dshow(Windows) 대신 v4l2(Linux)로 다름:

```bash
# MediaMTX 설치 (arm64) — 최신 릴리스 자산명은 그때그때 확인
curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest \
  | grep browser_download_url | grep linux_arm64 | cut -d '"' -f 4
# 위에서 나온 linux_arm64.tar.gz(암복호X, "arm64v8" 아님) 다운로드+압축 해제

# 실행
nohup ./mediamtx > mediamtx.log 2>&1 &

# 웹캠 push (해상도/포맷은 카메라마다 다르니 --list-formats-ext로 확인 후 맞출 것)
nohup ffmpeg -f v4l2 -input_format yuyv422 -video_size 640x480 -framerate 20 -i /dev/video0 \
  -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -g 10 \
  -rtsp_transport tcp -f rtsp rtsp://localhost:8554/ELEV-TOP \
  > ffmpeg.log 2>&1 &
```

**미완: 아직 `nohup`으로 수동 실행 중** — 재부팅하면 자동으로 안 뜸. 정식 배포 전 systemd
서비스화 필요(TODO, 아래 TBD 참고).

## RTSP 재생 시 화면 깨짐 (UDP 패킷 유실)

Wi-Fi 구간에서 RTSP를 UDP로 받으면(VLC 기본값) 패킷 유실로 화면이 블록 단위로 깨짐 — GOP를
10(0.5초)으로 짧게 잡아둬서 다음 키프레임에서 곧 회복되긴 하지만, 눈에 띄는 깨짐 자체는
발생. **TCP로 강제하면 해소됨**(VLC: `--rtsp-tcp` 옵션 또는 환경설정에서 "TCP를 통한 RTP
사용" 체크). 백엔드(`WebApps/backend/streaming/cameraManager.py`)는 이미
`OPENCV_FFMPEG_CAPTURE_OPTIONS`로 `rtsp_transport;tcp`를 강제하고 있어서 **코드 수정
불필요** — 이 문제는 VLC 등으로 수동 테스트할 때만 해당.

## TBD / 남은 작업

- **MediaMTX/ffmpeg push를 systemd 서비스화** — 지금은 `nohup`으로 수동 실행, 재부팅 시
  자동 시작 안 됨
- **로컬 백엔드와 라즈베리파이가 다른 네트워크 세그먼트에 있을 경우** — mDNS(`.local`)는
  같은 세그먼트에서만 동작. 다른 세그먼트면 라우팅(양쪽 다 관리자 권한 있어야) 또는
  터널(GPU 서버처럼 SSH 터널 등) 필요, 아직 미정. 실제 배포 시 라즈베리파이 설치 위치의
  네트워크와 로컬 백엔드 네트워크가 같은지 먼저 확인할 것(`architecture.md`의 "TBD" 참고)
- Wi-Fi 5GHz 불안정 현상의 정확한 원인(공유기 설정 추정) 미확인 — 재발하면 2.4GHz로 우회
- GPIO(전구)/스피커 연동 — 아직 미착수(`architecture.md` 참고)
