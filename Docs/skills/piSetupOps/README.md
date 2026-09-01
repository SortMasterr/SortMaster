# 라즈베리파이(메인보드) 실기기 셋업 가이드

이 문서는 SortMaster의 카메라 지점(`CameraId`)마다 붙는 라즈베리파이 보드를 처음부터 끝까지
셋업하는 절차입니다. 지점 1개(예 `ELEV-TOP`, `ELEV-SIDE`)마다 이 과정을 그대로 반복하면
됩니다. 배경/설계 이유는 `.agentfiles/architecture.md`의 "메인보드(라즈베리파이) 엣지 코드"
절 참고, 여기서는 "실제로 어떻게 하는지"만 다룹니다.

## 준비물

- 라즈베리파이 본체 (64bit, Raspberry Pi OS 지원 모델)
- microSD 카드 + 카드리더
- USB 웹캠 (또는 카메라 모듈 — 카메라 모듈 연동은 아직 검증 안 됨, USB 웹캠 기준으로 작성)
- 전원 케이블, (USB 랜선 또는 Wi-Fi로 네트워크 연결)
- SD카드를 구울 노트북/PC (Windows 기준, Raspberry Pi Imager 설치)

## 1단계 — SD카드 굽기 (Raspberry Pi Imager)

1. [Raspberry Pi Imager](https://www.raspberrypi.com/software/) 설치 후 실행
2. **CHOOSE DEVICE** → 실제 보드 모델 선택
3. **CHOOSE OS** → `Raspberry Pi OS (64-bit)` (GUI 필요 없으면 Lite 버전 추천 — 이 보드는
   캡처+RTSP송신+GPIO만 하는 헤드리스 장비라 데스크톱 불필요)
4. **CHOOSE STORAGE** → SD카드 선택 (주의: 다른 드라이브 잘못 고르면 그 드라이브가 통째로
   지워짐 — 용량/이름으로 SD카드 맞는지 꼭 확인)
5. 톱니바퀴(사용자 지정) 눌러서 미리 설정:
   - **호스트이름**: 카메라 지점명과 맞춤(예 `elev-top`, `elev-side`) — `CameraId` 값을
     소문자+하이픈으로
   - **사용자**: 계정명은 GPU 서버 팀 계정(`.agentfiles/gpuServerOps.md`의 `soma`)과
     헷갈리지 않게 별도로 지정, sudo는 기본 `null`(권한 없음)이라 필요하면 여기서
     `ALL=(ALL) NOPASSWD:ALL`로 직접 켜야 함
   - **SSH**: 활성화 + 비밀번호(또는 공개키) 등록
   - **Wi-Fi**: 유선만 쓸 계획이어도 채워두면 편함(유선 케이블 문제 생겼을 때 대체 경로)
6. WRITE 실행(SD카드 전체가 지워지고 새로 써짐, 몇 분 소요)

## 2단계 — 첫 부팅 & SSH 접속 확인

1. SD카드를 라즈베리파이에 꽂고 전원 연결(HDMI/키보드 불필요 — 헤드리스)
2. 첫 부팅은 1~3분 정도 걸림(cloud-init이 패키지 설치 등 초기화 작업을 하는 동안)
3. 노트북에서 접속:
   ```bash
   ssh <계정>@<호스트이름>.local
   ```
4. `.local`(mDNS)이 안 통하면 "트러블슈팅 → mDNS/SSH 접속 안 될 때" 참고

## 3단계 — RTSP 송신 셋업 (ffmpeg + MediaMTX)

Windows 로컬 시뮬레이터(`debug/streaming/startRtspSim.py`)와 동일한 패턴 — 캡처 백엔드만
Linux용(v4l2)으로 다릅니다. SSH로 접속한 상태에서 진행합니다.

### 카메라 확인 + 패키지 설치

```bash
ls /dev/video*
sudo apt update && sudo apt install -y ffmpeg v4l-utils
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

마지막 명령어로 카메라가 지원하는 포맷(MJPEG 지원 여부, 최대 해상도/fps)을 확인합니다.
MJPEG를 지원하면 대역폭 절약을 위해 MJPEG로, 없으면(저가형 웹캠은 보통 YUYV 무압축만
지원) 무압축으로 캡처해도 640x480 수준이면 대역폭 문제는 없습니다.

### MediaMTX 설치 (arm64)

```bash
cd ~
curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest \
  | grep browser_download_url | grep linux_arm64 | cut -d '"' -f 4
```

위 결과로 나온 URL(예: `mediamtx_v1.x.x_linux_arm64.tar.gz` — `arm64v8` 아님, 버전마다
파일명이 바뀔 수 있으니 실제 출력을 확인)을 `wget`으로 받아 압축 해제:

```bash
wget <위에서 나온 URL>
tar xzf mediamtx_*_linux_arm64.tar.gz
ls mediamtx mediamtx.yml
```

### 실행

```bash
# MediaMTX (RTSP 서버) 백그라운드 실행
nohup ./mediamtx > mediamtx.log 2>&1 &
sleep 2
cat mediamtx.log        # 8554 포트로 [RTSP] started 로그 확인
ss -tlnp | grep 8554

# 웹캠 → MediaMTX push (해상도/포맷은 위에서 확인한 카메라 스펙에 맞출 것)
nohup ffmpeg -f v4l2 -input_format yuyv422 -video_size 640x480 -framerate 20 -i /dev/video0 \
  -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -g 10 \
  -rtsp_transport tcp -f rtsp rtsp://localhost:8554/<CameraId> \
  > ffmpeg.log 2>&1 &
sleep 3
cat ffmpeg.log
```

`<CameraId>`는 `ELEV-TOP`/`ELEV-SIDE`처럼 대문자 하이픈 값(스트림 경로, `schemas/event.py`의
`CameraId` 값과 동일).

위 `nohup` 방식은 최초 수동 검증용 — 정식 운영은 재부팅 시 자동 기동되도록 systemd
서비스로 등록해서 쓴다(아래 "systemd 서비스화" 참고, 실제 재부팅 테스트로 검증 완료).

### 스트림 확인

노트북에서 VLC(또는 ffplay)로 재생 — **반드시 TCP 강제**(안 하면 Wi-Fi 구간에서 화면
깨짐, 아래 트러블슈팅 참고):

```bash
vlc rtsp://<호스트이름>.local:8554/<CameraId> --rtsp-tcp
```

fps 확인은 VLC 도구 → 미디어 정보 → 통계 탭, 또는 라즈베리파이 쪽 `tail -f ~/ffmpeg.log`의
`speed=` 값(1.0 근처면 정상 실시간 처리).

### systemd 서비스화 (정식 배포)

`nohup`으로 수동 검증이 끝났으면, 재부팅 시 자동 기동되도록 두 프로세스를 systemd
서비스로 등록한다. `/etc/systemd/system/mediamtx.service`(경로는 실제 설치 위치에 맞출 것):

```ini
[Unit]
Description=MediaMTX RTSP server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sortmaster
WorkingDirectory=/home/sortmaster
ExecStart=/home/sortmaster/mediamtx
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/webcam-rtsp-push.service`(서비스 이름은 보드마다 물리적으로 분리돼
있어서 겹칠 일이 없어 공통 이름 사용, `<CameraId>`만 실제 카메라 값으로 교체):

```ini
[Unit]
Description=Webcam RTSP push to local MediaMTX
After=mediamtx.service
Requires=mediamtx.service

[Service]
Type=simple
User=sortmaster
ExecStart=/usr/bin/ffmpeg -f v4l2 -input_format yuyv422 -video_size 640x480 -framerate 20 -i /dev/video0 -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -g 10 -rtsp_transport tcp -f rtsp rtsp://localhost:8554/<CameraId>
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

등록/기동 및 검증:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mediamtx.service
sudo systemctl enable --now webcam-rtsp-push.service
systemctl status mediamtx.service --no-pager
systemctl status webcam-rtsp-push.service --no-pager
```
두 서비스 다 `active (running)`이면 성공. 로그는 `journalctl -u <서비스명> -f`로 확인
(기존 `mediamtx.log`/`ffmpeg.log` 파일 대신 journal로 통합됨). 마지막으로 `sudo reboot` 후
다시 접속해서 수동 기동 없이 두 서비스가 저절로 떠있는지 확인하면 검증 끝 — **TOP/SIDE
둘 다 이 방식으로 재부팅 검증 완료**.

### 고정 IP 설정 (Docker로 배포할 경우 사실상 필수)

**mDNS(`.local`)는 Docker 컨테이너 안에서는 기본적으로 안 통함** — 컨테이너 안에 mDNS
리졸버(`libnss-mdns`)가 없어서, Windows 호스트나 `uvicorn` 로컬 실행에선 잘 되던
`elev-top.local`이 `docker compose`로 띄운 백엔드 컨테이너 안에선 해석이 안 돼 스트림이
안 뜸(실전에서 확인됨 — TOP을 호스트이름으로 바꾸고 Docker에서 빌드했더니 화면이 안
나오고, IP를 그대로 쓴 SIDE는 정상 작동했음). Docker로 배포한다면 호스트이름 대신
**라즈베리파이 자체에 고정 IP**를 설정하는 게 현실적인 해법.

공유기 관리자 권한이 없어도(학원 공유망 등) 라즈베리파이 쪽에서 직접 설정 가능. Bookworm
이후 Raspberry Pi OS는 NetworkManager+netplan 조합을 씀 — 연결 프로필 이름 확인:

```bash
nmcli connection show
```

`netplan-wlan0-<SSID>`처럼 나오는 항목의 UUID로 원본 설정 파일 위치를 찾음(실제 적용되는
파일은 `/run/NetworkManager/system-connections/`에 있지만 **이건 재부팅하면 사라지는
임시 파일** — 반드시 `/etc/netplan/90-NM-<UUID>.yaml`을 고쳐야 영구 반영됨):

```bash
sudo cat /etc/netplan/90-NM-<UUID>.yaml   # 기존 내용(Wi-Fi 비밀번호 등) 확인 후 그대로 유지
```

기존 내용에서 `dhcp4: true`를 `false`로 바꾸고 `addresses`/`routes`/`nameservers`를
추가(다른 필드는 그대로 유지 — 특히 `access-points`의 `password`는 그대로 복사):

```bash
sudo tee /etc/netplan/90-NM-<UUID>.yaml > /dev/null <<'EOF'
network:
  version: 2
  wifis:
    wlan0:
      renderer: NetworkManager
      match: {}
      dhcp4: false
      addresses:
        - 192.168.0.201/24
      routes:
        - to: default
          via: 192.168.0.1
      nameservers:
        addresses: [192.168.0.1, 8.8.8.8]
      access-points:
        "<SSID>":
          auth:
            key-management: "psk"
            password: "<기존 파일에서 그대로 복사한 값>"
          networkmanager:
            uuid: "<UUID>"
            name: "netplan-wlan0-<SSID>"
            passthrough:
              proxy._: ""
      networkmanager:
        uuid: "<UUID>"
        name: "netplan-wlan0-<SSID>"
EOF
sudo netplan apply
```

적용 중 SSH 세션이 잠깐 끊기는 게 정상(IP가 바뀌는 순간이라) — 새 IP로 재접속해서
`ip addr show wlan0`로 확인. 고정 IP로 고를 값은 사전에 `ping -c 2 <후보IP>`로
"Destination Host Unreachable"이 나오는지(=비어있는지) 확인하고 쓸 것. TOP/SIDE 각각
다른 고정 IP를 부여(예: TOP `.201`, SIDE `.202`) — 재부팅 후에도 유지되는지 반드시
검증할 것(`sudo reboot` → 재접속 → `ip addr show`).

**주의: SD카드를 전원 켜진 채로 뽑지 말 것**: 이 작업 중 SD카드를 라즈베리파이 전원이 켜진
상태로 그냥 뽑았다가 `/etc/netplan/*.yaml` 파일 2개가 통째로 빈 파일이 돼버린 사례가
있음(방금 `tee`로 쓴 내용이 디스크에 완전히 반영되기 전에 저장장치가 사라지면서 발생한
것으로 추정). 그 결과 wlan0/eth0 프로필이 NetworkManager 목록에서 아예 사라지고 SSH도
완전히 불통이 됐음 — 복구는 (1) 안 건드린 인터페이스(이 경우 eth0)로 랜선 연결 후 재부팅해서
해당 인터페이스로 재접속, (2) 깨진 netplan 파일들을 SSH로 다시 써넣기, 순으로 진행. **SD카드를
분리해야 하면 반드시 전원(케이블)부터 끈 다음에 뽑을 것** — 전원 케이블만 뽑는 건(SD카드는
꽂아둔 채) `fsck.repair=yes` 덕에 훨씬 안전하니 일상적으로는 문제없음.

## 4단계 — 백엔드 연동

`WebApps/backend`의 `.env`에 아래처럼 추가. 키는 `CameraId`에서 하이픈을 빼고 대문자로
바꾼 형태(`streaming/cameraManager.py`의 `_envKeyForCameraId` 규칙), 예를 들어
`ELEV-TOP`이면:

```
CAMERA_SOURCE_ELEVTOP=rtsp://elev-top.local:8554/ELEV-TOP   # 로컬 uvicorn 직접 실행 시
CAMERA_SOURCE_ELEVTOP=rtsp://192.168.0.201:8554/ELEV-TOP    # Docker로 배포 시(위 "고정 IP 설정" 참고)
```

백엔드 재시작 후 `GET /api/stream/<CameraId>`로 확인. RTSP를 TCP로 강제하는 옵션은
`streaming/cameraManager.py`에 이미 구현돼 있어 별도 설정 불필요.

---

## 트러블슈팅

### mDNS(`.local`)/SSH 접속이 안 될 때

1. **전원/링크 LED부터 확인**: 전원 LED 꺼져있으면 전원 문제, 이더넷 포트 링크 LED
   꺼져있으면 케이블/포트 문제
2. **Wi-Fi 5GHz 대역 이슈**: 노트북이 5GHz 대역에 붙어있으면 SSH가 배너 교환 직전에
   계속 끊기고(`kex_exchange_identification: Connection closed by remote host`), `.local`도
   엉뚱한 IP로 잘못 풀리는 증상을 실전에서 확인함. **노트북을 2.4GHz 대역으로 전환하면
   즉시 해소**됨 — 재현성 있게 확인된 증상이라 접속 안 될 때 가장 먼저 확인할 것
   (정확한 메커니즘은 미확인, 공유기의 대역별 네트워크 분리로 추정)
3. **SSH 22번이 막힌 네트워크일 경우**: `sshd_config.d/`에 드롭인 설정으로 2222번도 같이
   열어두면 대안이 됨(GPU 서버도 같은 이유로 2222 사용, `.agentfiles/gpuServerOps.md` 참고).
   단, 위 5GHz 이슈였을 가능성이 더 높으니 대역 전환을 먼저 시도할 것
4. **IP를 직접 찾아야 할 때**: 노트북에서 서브넷 전체를 스캔하고 라즈베리파이 제조사
   MAC 대역(OUI)으로 필터링:
   ```powershell
   $tasks = 1..254 | ForEach-Object {
       $ip = "192.168.0.$_"   # 본인 서브넷에 맞게 수정
       $p = New-Object System.Net.NetworkInformation.Ping
       [PSCustomObject]@{ IP = $ip; Task = $p.SendPingAsync($ip, 400) }
   }
   [System.Threading.Tasks.Task]::WaitAll($tasks.Task)
   $alive = $tasks | Where-Object { $_.Task.Result.Status -eq 'Success' } | Select-Object -ExpandProperty IP
   $piPrefixes = 'b8-27-eb','dc-a6-32','e4-5f-01','28-cd-c1','d8-3a-dd','2c-cf-67','3a-35-41'
   arp -a | Select-String -Pattern ($alive -join '|') | Select-String -Pattern ($piPrefixes -join '|')
   ```
   여러 대가 동시에 잡히면 라즈베리파이에서 `ip addr`로 실제 MAC 확인 후 대조
5. **`ping <호스트이름>.local`은 되는데 `ssh`만 타임아웃날 때**: 방화벽/AP 격리 문제가
   아니라, mDNS가 IPv6 링크-로컬 주소(`fe80::...`)를 먼저 돌려주는데 그 주소는 zone
   ID(`%5`처럼 인터페이스 번호)가 있어야 라우팅되고 ssh는 호스트이름만으로 이걸 자동으로
   못 붙여서 생기는 문제일 수 있음(`ping <호스트이름>.local`로 나온 주소가 `fe80::`로
   시작하면 이 케이스) — ssh에 IPv4를 강제하면 해결:
   ```powershell
   ssh -4 sortmaster@<호스트이름>.local
   ```

### IP가 자꾸 바뀔 때 (공유기 재시작, 다른 네트워크로 이동 등)

DHCP로 받는 이상 네트워크가 바뀌면 IP도 바뀌는 게 정상. 대응 방법은 백엔드를 어떻게
돌리느냐에 따라 다름:

- **로컬 `uvicorn`으로 직접 실행**: `.env`에 IP 대신 호스트이름(`<호스트이름>.local`)을
  넣어두면 이 문제 자체가 사라짐 — mDNS가 그 순간의 실제 IP로 자동으로 다시 풀어줌.
  공유기 관리자 권한 불필요. 실전에서 공유기 재시작으로 전체 IP가 초기화된 뒤에도
  호스트이름 접속은 그대로 동작 확인함
- **Docker로 배포**: 컨테이너 안에서는 mDNS가 안 통해서 호스트이름 방식이 안 먹힘(위
  "고정 IP 설정" 참고) — 라즈베리파이 자체에 고정 IP를 설정해서 아예 IP가 안 바뀌게 하는
  방식으로 대응. 공유기 관리자 권한 없어도 가능

단, mDNS는 **같은 네트워크 세그먼트 안에서만** 동작(멀티캐스트가 라우팅 경계를 못 넘음).
로컬 백엔드와 라즈베리파이가 서로 다른 네트워크 세그먼트에 있으면 호스트이름 접속 자체가
안 되고(고정 IP를 쓰더라도 마찬가지 — IP 자체가 다른 네트워크에서는 안 보임), 그때는
라우팅(양쪽 네트워크 관리자 권한 필요) 또는 터널(SSH 터널 등, GPU 서버 연동과 같은 방식)
중 하나를 선택해야 함 — 실제 설치 위치와 로컬 백엔드가 같은 네트워크인지 사전에 확인할 것.

### SD카드 설정을 고쳤는데 재부팅해도 반영이 안 될 때

Raspberry Pi OS(Bookworm 이후)는 cloud-init(NoCloud datasource)으로 최초 설정을 적용함.
SD카드를 PC에 꽂으면 `bootfs`라는 FAT32 파티션만 보이고(리눅스 rootfs는 Windows에서 안 보임,
정상), 그 안의 `user-data`/`meta-data`/`network-config`/`cmdline.txt`가 설정 원본입니다.

**함정**: `user-data`를 고치고 `meta-data`의 `instance-id`만 새 값으로 바꿔서 cloud-init이
재처리하게 하려 했는데 반영이 안 됐던 사례가 있음. **원인은 `cmdline.txt`에도
`ds=nocloud;i=<instance-id>`로 instance-id가 하드코딩돼 있고, 이게 `meta-data`보다 우선
적용된다는 것** — `meta-data`만 바꾸면 cloud-init이 여전히 "이미 처리한 인스턴스"로
착각하고 `write_files`/`runcmd`를 건너뜁니다.

→ **`meta-data`와 `cmdline.txt` 두 곳의 instance-id를 동일한 새 값으로 같이 바꿀 것.** 그리고
SD카드만 바꿔 끼우는 걸로는 반영 안 됨 — 전원을 완전히 껐다 켜야 새 부팅이 시작됩니다.

### rootfs(ext4) 안의 로그를 Windows에서 확인하고 싶을 때

Windows는 ext4 파일시스템을 못 읽어서 `/var/log/cloud-init*.log`, `/etc/ssh/` 등은 SD카드를
그냥 꽂아서는 못 봄. 시도해본 방법:

- **`wsl --mount \\.\PHYSICALDRIVEn --partition 2 --type ext4`(관리자 권한 필요)**: 카드리더
  종류에 따라 Hyper-V가 디스크를 못 넘겨받아 실패하는 경우 있음(`0x8007000f` 에러) — 리더
  하드웨어 한계로 추정, 안 되면 아래로
- **DiskInternals Linux Reader(무료, Windows GUI, 읽기 전용)**: 관리자 권한 불필요, ext4
  파티션을 탐색기처럼 읽을 수 있음 — 실전에서 이 방법으로 성공. 단 쓰기(수정)는 안 되므로
  설정 변경은 `bootfs`(FAT32) 쪽 `user-data`를 고쳐서 재부팅으로 반영하는 방식으로 우회

### RTSP 재생 시 화면이 블록 단위로 깨질 때

Wi-Fi 구간에서 RTSP를 UDP로 받으면(VLC 기본값) 패킷 유실로 화면이 깨짐 — GOP를 짧게
잡아뒀다면(위 예시는 10, 0.5초) 다음 키프레임에서 곧 회복되지만 눈에 띄는 깨짐 자체는
발생. **TCP로 강제하면 해소**(VLC: `--rtsp-tcp` 옵션, 또는 환경설정 → 모든 설정 보기 →
입력/코덱 → 디먹서 → RTP/RTSP 스트림 → "TCP를 통한 RTP 사용" 체크). 백엔드
(`WebApps/backend/streaming/cameraManager.py`)는 이미 `OPENCV_FFMPEG_CAPTURE_OPTIONS`로
`rtsp_transport;tcp`를 강제하고 있어 코드 수정은 불필요 — 이 이슈는 VLC 등으로 수동
테스트할 때만 해당.

### systemd 서비스 등록 시 `ExecStart=` 오타

`ExecStart=` 뒤 `=`을 빠뜨리면(`ExecStart/경로...`) `systemctl daemon-reload`는 그냥
통과하지만, 시작 시 "Unit has a bad unit file setting"으로 실패함. `journalctl -xeu
<서비스명>`에 "Missing '=', ignoring line" 문구가 보이면 이 오타부터 의심.

## 남은 작업 (TBD)

- 로컬 백엔드와 라즈베리파이가 다른 네트워크 세그먼트에 있는 경우의 연결 방식(라우팅/터널)
  확정
- Wi-Fi 5GHz 불안정 현상의 정확한 원인 규명(현재는 2.4GHz 우회로만 대응)
- 카메라 모듈(CSI) 연동 — 지금까지는 USB 웹캠으로만 검증
- GPIO(전구)/스피커 연동 — 아직 미착수
