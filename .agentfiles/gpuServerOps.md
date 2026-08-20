# gpuServerOps.md

전체 가이드(트러블슈팅 포함): `Docs/skills/gpuServerOps/README.md` (원본, 아직 저장소에 없음 — 작성 전까지 이 문서가 유일한 기준)

GPU 서버(`e8000`, 학교 공용, 다른 팀·수강생과 공유) 운영 실전 절차. `architecture.md`가 "뭘
하기로 했는지"라면 이 문서는 "실제로 어떻게 하는지".

## 서버 특성

- `ssh -p 2222 <계정>@<GPU_SERVER_IP>`(실제 IP는 Notion 참고) — 포트포워딩은 2222만 열려있음(관리자 권한 없어 추가 불가).
  다른 서비스는 SSH 터널로 우회
- Docker는 기본 **rootful 데몬을 전원이 공유**(`docker ps -a`에 남 컨테이너까지 보임) — 이름/포트
  충돌 방지 위해 계정별로 **rootless Docker** 사용
- GPU는 L40S 4장, 팀당 1장(`nvidia-smi` 인덱스 확인)

## 팀 공용 계정(`soma`)

개인 계정 대신 팀 전용 Linux 계정 하나를 만들어 팀원 전원이 SSH 키로 공유.

```bash
sudo adduser soma                        # sudo/docker 그룹엔 넣지 않음(권한 최소화)
cat /etc/subuid | grep soma              # rootless Docker 전제조건, adduser가 보통 자동 할당
cat /etc/subgid | grep soma
sudo mkdir -p /home/soma/.ssh
sudo nano /home/soma/.ssh/authorized_keys   # 팀원 공개키 한 줄씩 추가
sudo chown -R soma:soma /home/soma/.ssh && sudo chmod 700 /home/soma/.ssh
sudo chmod 600 /home/soma/.ssh/authorized_keys
```
등록 안 된 팀원은 비밀번호 없이 접속 불가 — 각자 본인 공개키를 추가해야 함. **주의**: root(`sudo -i`)
상태로 `/home/soma`에서 `git clone` 등을 하면 소유자가 root로 생겨 나중에 `soma` 세션에서 권한
문제가 남 — 반드시 `soma`로 직접 로그인해서 작업할 것.

## rootless Docker 설치 (계정마다 개별 필요)

```bash
sudo apt-get install -y uidmap dbus-user-session   # 시스템 패키지, 한 번만
dockerd-rootless-setuptool.sh install --force      # 기존 rootful과 공존, --force로 경고 무시
export PATH=/usr/bin:$PATH
export DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock
echo 'export PATH=/usr/bin:$PATH' >> ~/.bashrc
echo 'export DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock' >> ~/.bashrc
sudo loginctl enable-linger soma    # 로그아웃해도 데몬 유지(대상 계정 지정은 sudo 있는 쪽에서)
systemctl --user enable docker && systemctl --user start docker
docker info | grep -i rootless      # 값 나오면 성공
```
`No cpuset/io.weight support` 경고는 rootless cgroup 제약이라 무시 가능(이 프로젝트는 미사용).

## GPU 카드 격리 & 포트

- `.env`의 `GPU_DEVICE_ID=<nvidia-smi 인덱스>` → `training`/`inference`/`llm` 서비스가
  `device_ids`로 그 카드만 사용(`count: all`은 타 팀 카드까지 잡으므로 금지). `inference`는
  상시 기동이라 `training`/`llm`을 돌리는 시간대엔 같은 카드를 나눠 써야 함 —
  `gpu-memory-utilization` 류 제한 필요(실측 후 조정, `architecture.md`의 "추론 인프라" 참고)
- 컨테이너 **내부** 포트는 겹쳐도 무관, **호스트** 포트만 충돌 주의: `sudo ss -tlnp | grep <포트>`로 사전 확인
- `docker compose ps`의 `PORTS` 칸이 비면(컨테이너 `Up`인데 매핑 안 보임) 이전 실패로 이상 상태 남은 것 —
  지우고 재생성:
  ```bash
  docker compose down && docker compose --profile training down
  docker compose up -d --build && docker compose --profile training up -d --build training
  ```

## 외부 접속 — SSH 터널 (2222 외 포트포워딩 불가)

> **`-L`(GPU서버→로컬 보기)에 `inference` API 포트 추가 필요** — GPU 연동 방식이 "라즈베리
> 파이→GPU 서버 RTSP 상시 전송"에서 "로컬 백엔드가 프레임을 샘플링해 GPU 추론 API를 호출"로
> 바뀌면서(`architecture.md`의 "탐지 파이프라인" 참고), 로컬 백엔드가 GPU 서버의 `inference`
> API 포트에 닿아야 함 — 방향이 `-R`이 아니라 `-L`(로컬이 GPU 서버 쪽을 보러 가는 방향).
> 정확한 포트는 `inference` 컨테이너 구현 시 확정(TBD). `llm` 포트는 여전히 실시간
> 경로용으로는 불필요(학습 준비 단계의 자동 라벨링 검증은 `training`↔`llm`이 둘 다 GPU
> 서버 안에 있어서 컨테이너 간 통신으로 충분).
> **`-R`(로컬→GPU서버 보내기)의 Mongo 포트는 상시 필요** — `training`이 학습용 원본
> 이미지를 로컬 GridFS에서 직접 가져오기로 확정(`architecture.md`)했기 때문.
> **RTSP 포트(8554) 역터널은 더 이상 불필요** — 과거엔 TOP 카메라 RTSP를 GPU 서버
> `inference`가 SSH 역터널로 직접 당겨받는 방식이었으나, 프레임 샘플링 API 호출 방식으로
> 바뀌면서 라즈베리파이가 GPU 서버와 직접 연결될 일이 없어짐(`decisionLog.md` 참고) —
> 이 역터널이 갖고 있던 "끊기면 탐지 전체가 멈추는 단일 장애점" 리스크가 해소됨. 로컬
> 백엔드 → GPU API 연결(`-L`)은 여전히 끊기면 그 동안 AI 판정이 안 되므로, 재연결 전략
> (`autossh` 등)은 이쪽으로 옮겨서 검토 필요.

```bash
# GPU 서버 서비스를 노트북/로컬 백엔드에서 보기(-L). inference API 포트는 컨테이너 구현
# 후 추가(TBD), 8100(llm)은 실시간 경로에 안 쓰는 한 불필요
ssh -p 2222 -L 8899:localhost:8899 -L 8100:localhost:8100 soma@<GPU_SERVER_IP>
# 노트북/로컬 DB를 GPU 서버로 보내기(-R, 반대 방향). 27020은 로컬 MongoDB(학습용 원본
# 이미지 조회, training이 사용)
ssh -p 2222 -R 27020:localhost:27020 soma@<GPU_SERVER_IP>
```
`-R`로 받은 포트는 컨테이너 안에서 호스트의 `localhost`에 직접 못 닿으므로, `training`
서비스에 `extra_hosts: ["host.docker.internal:host-gateway"]`를 적용하고 MongoDB 접속
주소를 `host.docker.internal:27020`처럼 지정(과거엔 `inference`의 RTSP 카메라 소스에도
이 방식이 필요했으나, 프레임 샘플링 API 호출 방식으로 바뀌면서 `inference`는 더 이상
해당 없음 — RTSP 자체를 안 받으므로).

## 팀 공유 MongoDB 계정 (GPU 서버로 이전 시) — 현재 보류

> ⚠️ **DB를 GPU 서버로 이전하는 것 자체가 "백엔드+DB는 로컬" 재조정으로 보류됨**
> (`architecture.md` 참고). 이미 만들어둔 계정/데이터는 남겨뒀지만 지금은 안 씀 — 나중에
> 다시 GPU 서버로 옮기게 되면 아래 절차 재사용.

`.30`과 물리적으로 다른 인스턴스라 계정을 새로 만들어야 함. **순서 중요**(계정 없이 `--auth`부터
켜면 아무도 로그인 못 함):
1. `docker-compose.yml`의 mongo `command: ["mongod", "--auth"]` 주석 처리 후 `docker compose up -d mongo`
2. `docker exec -it sortmaster-mongo mongosh`에서 root+`user01~05` 계정 생성(`db.createUser`,
   비밀번호는 문서에 적지 말고 팀원에게 직접 전달)
3. `--auth` 주석 해제 후 `docker compose up -d mongo`(볼륨 유지)
4. `.env`: backend도 같은 서버면 `MONGO_HOST=mongo`/`DB_PORT=27017`(내부망), 외부 접속이면
   `MONGO_HOST=<서버IP>`/`DB_PORT=27020`

## 메인보드(라즈베리파이) 참고

Jetson Orin Nano Super(icbanq 무료 렌탈) 발주 건은 **완전히 취소** — 라즈베리파이로 확정
대체. 이유: 애초 Orin을 쓰려던 목적(YOLO26 엣지 상시 추론)을 GPU 서버(`inference`)로
이관하기로 하면서 메인보드에 고성능 NPU/GPU가 더 이상 필요 없어짐(`architecture.md`의
"탐지 파이프라인"/"배포 전략" 참고). 라즈베리파이는 표준 Raspberry Pi OS(Python 3.11+)라
`WebApps/backend`와 문법 호환성 문제 없음 — 과거 Jetson Nano 4GB의 Python 3.6 제약 이슈는
애초에 해당 없음.

**라즈베리파이는 추론을 하지 않음** — 캡처+RTSP 송신+GPIO(전구 릴레이)+스피커(경고음)만
담당. **TOP/SIDE 둘 다 로컬 백엔드로만** RTSP를 보내면 됨(GPU 서버와 직접 연결되는
라즈베리파이는 없음 — 과거 "TOP만 8554 역터널로 GPU까지 도달" 방식 폐기, `decisionLog.md`
참고). TOP 카메라의 YOLO26 추론(감지+추적+분류)은 로컬 백엔드가 프레임을 샘플링해서 GPU
서버 `inference` 컨테이너의 API를 호출하는 방식으로 이루어짐. 학습 가중치(`.pt`)는
`training`→`inference` 둘 다 GPU 서버 안에 있으므로 원격 배포 없이 로컬 파일/볼륨 공유로
충분(과거 "젯슨에 SCP로 배포" 문제 자체가 사라짐).
