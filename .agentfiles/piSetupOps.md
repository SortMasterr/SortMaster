# piSetupOps.md

전체 가이드(준비물/단계별 절차 포함): `Docs/skills/piSetupOps/README.md` (원본). 이 문서는
그 요약본 — AI가 참고할 핵심 트러블슈팅/명령어 위주로만 추림, 팀원이 처음부터 따라할
땐 원본을 볼 것.

라즈베리파이(메인보드) 실기기 셋업 실전 절차/트러블슈팅. `architecture.md`가 "뭘 하기로
했는지"라면 이 문서는 "실제로 어떻게 하는지"(`gpuServerOps.md`와 같은 성격). **자동 로드
안 함** — 라즈베리파이 셋업/재현이 필요할 때만 열어볼 것.

## SD카드 굽기 (Raspberry Pi Imager)

- OS: Raspberry Pi OS 64-bit (Bookworm 이후 cloud-init 기반, NoCloud datasource)
- 사용자 지정(Imager 톱니바퀴 메뉴)에서 호스트이름/계정/SSH/Wi-Fi 미리 설정 → 완전 헤드리스
  부팅 가능(모니터/키보드 불필요)
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

## RTSP 송신 구조 (MediaMTX + ffmpeg push) — systemd 서비스화 완료

Windows 시뮬레이터(`debug/streaming/startRtspSim.py`)와 동일한 패턴을 라즈베리파이에서도
그대로 사용 — 캡처 백엔드만 dshow(Windows) 대신 v4l2(Linux)로 다름. 최초 설치(바이너리
다운로드)는 수동, 실행은 재부팅 시 자동 기동되도록 **systemd 서비스로 등록 완료**(재부팅
테스트로 검증됨):

```bash
# MediaMTX 설치 (arm64) — 최초 1회, 최신 릴리스 자산명은 그때그때 확인
curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest \
  | grep browser_download_url | grep linux_arm64 | cut -d '"' -f 4
# 위에서 나온 linux_arm64.tar.gz(그냥 arm64, "arm64v8" 아님) 다운로드+압축 해제
# ~/mediamtx(바이너리)가 나오는 위치 기준으로 아래 서비스 파일 작성
```

`/etc/systemd/system/mediamtx.service`:
```ini
[Unit]
Description=MediaMTX RTSP server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sortmaster
WorkingDirectory=/home/sortmaster
ExecStart=/home/sortmaster/mediamtx /home/sortmaster/mediamtx.yml
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/webcam-rtsp-push.service`(서비스 이름은 보드마다 물리적으로 분리돼
있어 공통 이름 사용, 해상도/포맷/CameraId는 카메라·보드마다 다르니 맞출 것):
```ini
[Unit]
Description=Webcam RTSP push to local MediaMTX
After=mediamtx.service
Requires=mediamtx.service

[Service]
Type=simple
User=sortmaster
ExecStart=/usr/bin/ffmpeg -f v4l2 -input_format yuyv422 -video_size 640x480 -framerate 20 -i /dev/video0 -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -g 10 -rtsp_transport tcp -f rtsp rtsp://localhost:8554/ELEV-TOP
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

등록/기동:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mediamtx.service
sudo systemctl enable --now webcam-rtsp-push.service
systemctl status mediamtx.service --no-pager
systemctl status webcam-rtsp-push.service --no-pager
```
TOP/SIDE 둘 다 재부팅 검증 완료.

로그 확인은 `journalctl -u webcam-rtsp-push.service -f`(기존 `ffmpeg.log`/`mediamtx.log`
파일 대신 journal로 통합됨). **자주 하는 실수**: unit 파일에 `ExecStart=` 쓸 때 `=`을
빠뜨리면(`ExecStart/경로...`) `systemctl daemon-reload`는 통과하지만 시작 시
"Unit has a bad unit file setting"으로 실패함 — `journalctl -xeu <서비스명>`으로
"Missing '=', ignoring line" 같은 문구가 보이면 이 오타부터 의심.

## RTSP 재생 시 화면 깨짐 (UDP 패킷 유실)

Wi-Fi 구간에서 RTSP를 UDP로 받으면(VLC 기본값) 패킷 유실로 화면이 블록 단위로 깨짐 — GOP를
10(0.5초)으로 짧게 잡아둬서 다음 키프레임에서 곧 회복되긴 하지만, 눈에 띄는 깨짐 자체는
발생. **TCP로 강제하면 해소됨**(VLC: `--rtsp-tcp` 옵션 또는 환경설정에서 "TCP를 통한 RTP
사용" 체크). 백엔드(`WebApps/backend/streaming/cameraManager.py`)는 이미
`OPENCV_FFMPEG_CAPTURE_OPTIONS`로 `rtsp_transport;tcp`를 강제하고 있어서 **코드 수정
불필요** — 이 문제는 VLC 등으로 수동 테스트할 때만 해당.

## 스트림 상태(fps) 확인

- **수신 쪽(VLC)**: 재생 중 도구(T) → 미디어 정보(I) → 통계 탭 → 실시간 수신 fps 표시
- **송신 쪽(라즈베리파이 ffmpeg 로그)**: `tail -f ~/ffmpeg.log` — `frame=... fps=XX ...
  speed=1.03x` 형태로 갱신됨. `speed`가 1.0 근처면 설정한 fps를 실시간으로 잘 따라가는
  중, 많이 낮으면(예 0.7x) 인코딩이 밀려서 실제 전송 fps가 떨어지고 있다는 신호

## Docker 컨테이너 안에서는 mDNS(`.local`)가 안 통함

`.env`에 호스트이름(`elev-top.local`)을 넣으면 **로컬 `uvicorn` 직접 실행**이나 SSH 같은
Windows 호스트 명령에선 잘 되지만, **`docker compose`로 띄운 백엔드 컨테이너 안에서는
해석이 안 됨**(컨테이너에 mDNS 리졸버가 기본적으로 없음) — 실전에서 TOP을 호스트이름으로
바꾸고 Docker에서 빌드했더니 화면이 안 나왔고, IP를 그대로 쓴 SIDE는 정상 작동했음으로
확인됨. **Docker로 배포한다면 호스트이름 대신 라즈베리파이 자체에 고정 IP를 설정**할 것
(아래 "고정 IP 설정" 참고) — 공유기 관리자 권한 없어도 가능.

## 고정 IP 설정 (netplan, 공유기 관리자 권한 불필요)

Bookworm 이후 Raspberry Pi OS는 NetworkManager+netplan 조합. 연결 프로필 확인:
```bash
nmcli connection show
```
`netplan-wlan0-<SSID>` 항목의 UUID로 원본 파일 위치 특정. **주의: 실제 적용 파일은
`/run/NetworkManager/system-connections/`(재부팅하면 사라지는 임시 파일)에 있음 — 반드시
`/etc/netplan/90-NM-<UUID>.yaml`을 고쳐야 영구 반영됨.**

```bash
sudo cat /etc/netplan/90-NM-<UUID>.yaml   # 기존 내용(Wi-Fi 비밀번호 등) 먼저 확인
```

`dhcp4: true`를 `false`로, `addresses`/`routes`/`nameservers` 추가(다른 필드, 특히
`access-points`의 `password`는 그대로 유지):
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
            password: "<기존 파일에서 그대로 복사>"
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
적용 중 SSH 잠깐 끊기는 게 정상 — 새 IP로 재접속. 후보 IP는 `ping -c 2 <IP>`로
"Destination Host Unreachable" 나오는지(=비어있는지) 미리 확인. TOP/SIDE 각각 다른
고정 IP 부여(`.201`/`.202` 사용), `sudo reboot` 후에도 유지되는지 재검증 완료.

**주의: 이 작업 중 SD카드를 전원 켜진 채로 뽑으면 안 됨** — `tee`로 쓴 내용이 디스크에
완전히 반영되기 전에 저장장치가 사라지면서 `/etc/netplan/*.yaml` 파일이 통째로 빈 파일이
돼버린 사례 있음(wlan0/eth0 프로필이 NetworkManager에서 아예 사라지고 SSH 완전 불통).
복구는 안 건드린 인터페이스(예: eth0)로 랜선 연결 후 재부팅해서 재접속 → 깨진 netplan
파일들 다시 써넣기. **SD카드 분리 전엔 반드시 전원부터 끌 것** — 전원 케이블만 뽑는 건
(SD카드는 꽂아둔 채) `fsck.repair=yes` 덕에 훨씬 안전해서 일상적으로 문제없음.

## IP 재확인 (공유기 재시작 등으로 바뀌었을 때, 호스트이름/mDNS 방식 쓸 때만 필요)

`.env`에 IP를 직접 박아두지 않고 `elev-top.local`(호스트이름)으로 넣어뒀으면 이 작업 자체가
불필요함(mDNS가 새 IP로 자동으로 다시 풀어줌, 단 로컬 uvicorn 실행 한정 — 위 Docker 관련
항목 참고) — 아래는 호스트이름 접속이 안 통할 때나 직접 확인이 필요할 때만.

노트북 PowerShell에서 본인 서브넷(`ipconfig`로 확인) 기준으로 전체 스캔 후 라즈베리파이
제조사 MAC 대역(OUI)으로 필터링:

```powershell
$tasks = 1..254 | ForEach-Object {
    $ip = "192.168.0.$_"   # 본인 서브넷에 맞게 앞 3자리 수정
    $p = New-Object System.Net.NetworkInformation.Ping
    [PSCustomObject]@{ IP = $ip; Task = $p.SendPingAsync($ip, 400) }
}
[System.Threading.Tasks.Task]::WaitAll($tasks.Task)
$alive = $tasks | Where-Object { $_.Task.Result.Status -eq 'Success' } | Select-Object -ExpandProperty IP
$piPrefixes = 'b8-27-eb','dc-a6-32','e4-5f-01','28-cd-c1','d8-3a-dd','2c-cf-67','3a-35-41'
arp -a | Select-String -Pattern ($alive -join '|') | Select-String -Pattern ($piPrefixes -join '|')
```

여러 대(TOP/SIDE 등)가 동시에 잡히면 MAC 뒷자리로 구분 — 라즈베리파이에서 `ip addr`로
실제 MAC 확인 후 대조.

## `ssh elev-top.local`이 타임아웃(`ping`은 되는데)

`ping elev-top.local`(IPv4 강제 없이)은 성공했는데 바로 이어서 `ssh sortmaster@elev-top.local`은
`Connection timed out`(포트 22/2222 둘 다)나는 사례 있음 — 방화벽/AP 격리 문제가 아니라
**mDNS가 IPv6 링크-로컬 주소(`fe80::...`)를 먼저 돌려주는데, 그 주소는 zone ID(`%5`처럼
인터페이스 번호)가 있어야 라우팅되고 ssh가 호스트이름만으로는 이걸 자동으로 못 붙여서
생기는 문제**였음(직접 그 IPv6 주소를 리터럴로 넣으면 zone ID 없이도 실패). 확인: `ping
elev-top.local`(IPv4 강제 없이)로 나온 주소가 `fe80::`로 시작하면 이 케이스.

→ ssh에 IPv4를 강제하면 해결:
```powershell
ssh -4 sortmaster@elev-top.local
```

## TBD / 남은 작업

- **로컬 백엔드와 라즈베리파이가 다른 네트워크 세그먼트에 있을 경우** — mDNS(`.local`)는
  같은 세그먼트에서만 동작. 다른 세그먼트면 라우팅(양쪽 다 관리자 권한 있어야) 또는
  터널(GPU 서버처럼 SSH 터널 등) 필요, 아직 미정. 실제 배포 시 라즈베리파이 설치 위치의
  네트워크와 로컬 백엔드 네트워크가 같은지 먼저 확인할 것(`architecture.md`의 "TBD" 참고)
- Wi-Fi 5GHz 불안정 현상의 정확한 원인(공유기 설정 추정) 미확인 — 재발하면 2.4GHz로 우회
- GPIO(전구)/스피커 연동 — 아직 미착수(`architecture.md` 참고)
