# gpuServerOps.md

전체 가이드(트러블슈팅 포함): `Docs/skills/gpuServerOps/README.md` (원본, 아직 저장소에 없음 — 작성 전까지 이 문서가 유일한 기준)

GPU 서버(`e8000`, 학교 공용, 다른 팀·수강생과 공유) 운영 실전 절차. `architecture.md`가 "뭘
하기로 했는지"라면 이 문서는 "실제로 어떻게 하는지".

## 서버 특성

- `ssh -p 2222 <계정>@116.42.115.24` — 포트포워딩은 2222만 열려있음(관리자 권한 없어 추가 불가).
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

- `.env`의 `GPU_DEVICE_ID=<nvidia-smi 인덱스>` → `training` 서비스가 `device_ids`로 그 카드만 사용
  (`count: all`은 타 팀 카드까지 잡으므로 금지)
- 컨테이너 **내부** 포트는 겹쳐도 무관, **호스트** 포트만 충돌 주의: `sudo ss -tlnp | grep <포트>`로 사전 확인
- `docker compose ps`의 `PORTS` 칸이 비면(컨테이너 `Up`인데 매핑 안 보임) 이전 실패로 이상 상태 남은 것 —
  지우고 재생성:
  ```bash
  docker compose down && docker compose --profile training down
  docker compose up -d --build && docker compose --profile training up -d --build training
  ```

## 외부 접속 — SSH 터널 (2222 외 포트포워딩 불가)

> **`-L`(GPU서버→로컬 보기)의 `llm` 포트는 MVP엔 필요 없음** — YOLO26(엣지) 단독으로
> 감지+분류+판정이 끝나서 로컬 백엔드가 GPU 서버를 실시간으로 호출할 일이 없음
> (`architecture.md`의 "탐지 파이프라인" 참고). 고도화 단계에서 `llm`을 쓰게 되면 그때부터
> 끊기면 분류가 안 되는 상시 연결이 되므로 `autossh` 등 자동 재연결 방안 검토 필요.
> **`-R`(로컬→GPU서버 보내기)의 Mongo 포트는 MVP부터 필요** — `training`이 학습용 원본
> 이미지를 로컬 GridFS에서 직접 가져오기로 확정(`architecture.md`)했기 때문.

```bash
# GPU 서버 서비스를 노트북/로컬 백엔드에서 보기(-L). 8100(llm)은 고도화 단계 전까지 불필요
ssh -p 2222 -L 8899:localhost:8899 -L 8100:localhost:8100 soma@116.42.115.24
# 노트북/로컬 DB를 GPU 서버로 보내기(-R, 반대 방향). 27020은 로컬 MongoDB(학습용 원본
# 이미지 조회, MVP부터 필요), 8554는 웹캠→RTSP(training 컨테이너 테스트용 등)
ssh -p 2222 -R 27020:localhost:27020 -R 8554:localhost:8554 soma@116.42.115.24
```
`-R`로 받은 스트림은 컨테이너 안에서 호스트의 `localhost`에 직접 못 닿으므로, `backend` 서비스에
`extra_hosts: ["host.docker.internal:host-gateway"]`(적용됨)를 쓰고 `.env`에
`CAMERA_SOURCE_ELEV01=rtsp://host.docker.internal:8554/ELEV-01`처럼 지정. 사설 IP(`192.168.0.x`)
카메라 소스는 GPU 서버가 그 네트워크에 속하지 않아 직접 라우팅이 안 되므로 반드시 이 방식 필요.

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

## 메인보드(Jetson Orin Nano Super) 참고

Jetson Nano 4GB(JetPack 4.6.x, Python 3.6 제약)는 발주 무산으로 더 이상 해당 없음 — **Jetson
Orin Nano Super Developer Kit**(icbanq 무료 렌탈, 8GB 유니파이드 메모리, 67 TOPS, JetPack 6.x/
Ubuntu 22.04/**Python 3.10**)로 확정. `WebApps/backend`(Python 3.11)와 문법 호환성 문제 없음
— 이전에 남겨뒀던 3.6 문법 제약(`str | None` 등 금지)은 더 이상 적용 안 됨.

엣지에서 YOLO26을 직접 돌림(`architecture.md`의 "탐지 파이프라인" 참고) — GPU 서버
(`training`)에서 학습한 `.pt` 가중치를 젯슨에 배포해서 상시 추론. **MVP는 YOLO26이 감지+
분류+판정을 전부 엣지에서 완결**해서 GPU 서버 호출 자체가 없음(과거 "중앙 LLM으로 영상
전송" 하이브리드 구조는 뒤집힘 — Qwen3-VL-8B는 고도화 단계 학습 보조용으로 후순위). `.pt`
배포 절차(SCP 등)는 아직 미정, 확정되면 여기에 추가할 것.
