# architecture.md

원본(source of truth). 다른 문서와 내용이 겹치면 이 문서 우선.

## 파이프라인

```
CCTV → 프레임분할 → 객체디텍팅 → 오분류 판정
  ├─ 탐지 시 → 현장알림(전구+경고음)
  └─ 결과전송 → 백엔드(수신API) → 기록/통계
→ 관리자웹(스트리밍/기록/통계, 오분류 시 테두리 빨간색)
```

- 목적: 행정직원 분리수거 감독 부담 경감
- 알림: 전구+스피커 항상 동시 트리거
- 안면인식(투기자 식별) 미포함, CTO 공통과제는 3팀 소관

## 설치 환경

| 항목 | 내용 |
|---|---|
| 위치 | **엘리베이터 2대 계획은 없었던 것으로 정정** — 실제로는 12층 엘리베이터 앞에 쓰레기통 1개만
  고정 설치(`ELEV` 명칭은 여기서 유래). 카메라 지점 2개(위+옆), `CameraId`는 `ELEV-TOP`/`ELEV-SIDE`로
  확정(설치 위치 번호 불필요 — 위치가 1곳뿐이라서). 4층 휴게실(`REST-4F-01`) 추가는 고도화
  단계 스트레치 목표(진행 여부 미정, 시간 남으면 검토) |
| 메인보드 | **Jetson Nano 4GB 발주 무산 → Jetson Orin Nano Super Developer Kit로 확정**(icbanq 무료 렌탈). 8GB 유니파이드 메모리, JetPack 6.x(Ubuntu 22.04, Python 3.10) |
| 카메라 구성 | **"카메라 1대 = 지점 1개 = `CameraId` 1개 = 독립 젯슨 나노 1대" 규칙 유지**(안 깨짐). 설치 위치 1곳(12층 엘리베이터 앞)에 지점 2개(위+옆). `.env` 키는 기존 하이픈 제거 규칙 그대로 `CAMERA_SOURCE_ELEVTOP`/`CAMERA_SOURCE_ELEVSIDE` |
| 카메라 스펙 | 웹캠 실촬영 해상도 **640×480**(약 30만 화소). YOLO 입력 전처리는 **640×640**으로 통일(레터박스 패딩 방식 — 비율 유지, 단순 리사이즈 아님). MVP는 YOLO26 혼자 분류까지 끝내서 별도 모델로 좌표를 넘길 일이 없음(LLM에 좌표 넘기는 보정은 고도화 단계에서 LLM을 실제로 쓰게 될 때 재검토) |
| 배포 구조 | 지점별(카메라별) 독립 메인보드+카메라 1대 — 설치 위치 1곳에 지점(=메인보드+카메라 세트) 2개 |
| 클래스 | general, paper, plastic, can(신규, 플라스틱과 별도지만 같은 통), coffeeCup(별도 통) — 총 5종. `mixed`/`uncertain`은 제외 확정(자체 라벨링 시 전부 5종 중 하나로 분류 가능하다고 판단, 아래 "해결된 TBD" 참고) |

## 탐지 파이프라인

> **MVP는 LLM(Qwen3-VL-8B) 없이 엣지 YOLO26 단독으로 동작하는 걸로 확정**(과거 "엣지 YOLO26 +
> 중앙 LLM 실시간 하이브리드" 결정을 다시 뒤집음). **YOLO26이 감지+투척위치 추적뿐 아니라
> 쓰레기 종류 분류까지 담당**하도록 기능이 추가돼서, MVP 단계에선 GPU 서버로의 실시간 영상
> 전송/LLM 호출 자체가 없음. LLM은 "고도화" 단계로 완전히 미룸(아래 "LLM 활용(고도화, MVP
> 이후)" 참고) — 방금 만든 `llm`(vLLM) 서비스는 지금 당장 검증할 필요 없음.

- **넘침(overflow) 판정**(**옆 카메라** 단독, 엣지): 옆 카메라 젯슨에서 YOLO가 쓰레기통 넘침
  상태를 감지하면 **바로 알림 + DB에 시간대 저장**(기존과 동일, 변경 없음)
- **투기(misclassification) 판정**(**위 카메라** 단독, **엣지 전용 — MVP엔 GPU/LLM 호출 없음**):
  1. 위 카메라 젯슨에서 **YOLO26(엣지)**이 쓰레기 감지 → 이 시점부터 녹화 시작(DB 저장용)
  2. **YOLO26이 그 자리에서 쓰레기 종류까지 분류**(신규 기능 — 별도 모델 호출 없이 한 번에)
  3. YOLO26이 계속 추적한 투척 결과(어느 통에 들어갔는지)와 자신이 분류한 쓰레기 종류를
     종합해 오분류 여부 판단(전부 엣지에서 완결) → **로컬 백엔드로 결과 전송·저장** → 불일치
     시 RPA 트리거
  4. 투척 완료 후 **약 3초 텀**을 두고 녹화 종료
  - 엣지→로컬 백엔드 결과 저장 시 실제 신호 전달 방식(MQTT/HTTP/WS)은 여전히 TBD
- **역할 분담(MVP)**: 젯슨(엣지)이 캡처+RTSP 송신+GPIO+**YOLO26 추론(감지+추적+분류 전부)**을
  담당. GPU 서버는 **YOLO26 학습**(`training` 컨테이너)만 MVP 범위 — LLM 관련 컨테이너(`llm`)는
  기동 안 함

## LLM 활용(고도화, MVP 이후)

Qwen3-VL-8B는 MVP 실시간 추론 경로에 없음 — **학습/데이터 준비 단계에서만** 쓰는 걸로 용도가
바뀜(둘 다 아직 미착수, 후순위):

1. **불확실한 쓰레기 종류 분류 안정화**: YOLO26 학습 시 결과가 불확실한 케이스를 LLM으로
   검증해서 YOLO26이 틀리는 일이 없도록 안정화(정확한 방식은 TBD)
2. **환경별 통 모양 인식 학습 데이터 생성**: 설치 환경이 달라지면 물리 통 4개의 실제 생김새도
   달라지므로, LLM을 이용해 그런 환경별 통 인식 초기 학습 데이터를 만드는 데 활용(정확한
   방식은 TBD)

**LLM 파인튜닝**: **Qwen3-VL-8B** + LoRA/QLoRA(Unsloth 또는 LLaMA-Factory)로 GPU 1장(48GB) 내 진행(위 두 용도를 위한 것으로, 이 자체도 고도화 범위). 파인튜닝 후 4/8bit 양자화해 추론 시 VRAM 최소화(`training`과 같은 카드에서 동시 서빙 가능하도록). Full fine-tuning이나 32B/235B(MoE) 등 상위 사이즈는 단일 카드로 비현실적이라 배제. 데이터 규모에 따라 수시간~하루 내 소요 예상. 학습 작업과 실시간 서비스가 같은 카드를 쓰므로 트래픽 적은 시간대 학습 권장. 라이선스는 배포 전 해당 사이즈 조항 확인 필요

## 추론 인프라

- NVIDIA L40S 총 4장, **팀당 1장씩 전용 할당**(다른 팀과 경합 없음)
- MVP 모델/역할 분담은 위 "탐지 파이프라인" 참고(YOLO26 엣지 단독, GPU/LLM 미사용)
- **GPU 서버엔 컨테이너 2개**: `training`(라벨링·학습, MVP 범위, 필요할 때만 기동) /
  `llm`(Qwen3-VL-8B 서빙, vLLM — 고도화 전용, **MVP엔 기동 불필요**). `backend`/`mongo`는
  GPU 서버가 아니라 **로컬에서 구동**(아래 "배포 전략" 참고)
- `training` 컨테이너는 JupyterLab을 띄워서 팀원이 브라우저로 같이 접속해 학습 코드 작성
  (`.env`의 `JUPYTER_PORT`/`JUPYTER_TOKEN`, 진짜 멀티유저 격리는 아니라 동시 실행 지양).
  GPU 서버 운영 실무(계정/rootless Docker/포트/SSH 터널 등)는 `gpuServerOps.md` 참고

## 배포 전략

> **MVP 배포 위치 재조정(확정)** — 과거 "백엔드+DB+LLM 추론+학습을 GPU 서버 안에 전부
> 통합 배포"였던 결정을 뒤집음. **백엔드+DB는 로컬**, **GPU 서버는 YOLO26 학습**만 MVP
> 범위(LLM 추론은 MVP에서 아예 안 씀 — 위 "탐지 파이프라인"/"LLM 활용" 참고). 이유: GPU
> 서버는 다른 팀과 공유하는 자원이라 부담을 줄이고, 백엔드/DB는 애초에 GPU를 안 쓰므로
> 로컬에 둬도 기능상 문제없음.

- 개발: Windows+Docker, 로컬 웹캠 테스트(기존과 동일)
- **배포**: `backend`+`mongo`는 로컬 `192.168.0.40`(확정, 단 마지막 옥텟은 유동적일 수 있음)에서
  `docker compose up backend mongo`로 실행. `training`만 GPU 서버로 이전해서
  `docker compose --profile training up`로 실행(MVP 범위). `llm`(vLLM)은 고도화 단계에
  가서야 GPU 서버에서 `docker compose up llm`로 띄우면 됨 — **하나의 `docker-compose.yml`을
  그대로 쓰되, 호스트/단계마다 띄우는 서비스 조합만 다름**(별도 compose 파일 분리 불필요)
- **백엔드(로컬) → LLM(GPU 서버) 연결은 MVP엔 불필요** — 고도화 단계에서 `llm` 서비스를 쓰게
  되면 그때 SSH 터널(예: `ssh -p 2222 -L 8100:localhost:8100 soma@116.42.115.24`)을 상시
  유지해야 함(안정성 확보 방법은 그때 검토)
- **`training`(GPU 서버) → MongoDB(로컬) 연결은 MVP부터 필요** — 학습용 원본 이미지를
  로컬 GridFS에서 그대로 가져다 쓰기로 확정(위 "이벤트 적재" 참고)해서, 학습 돌릴 때마다
  역방향 터널(로컬 PC에서 `ssh -p 2222 -R 27020:localhost:27020 soma@116.42.115.24` 실행)이
  필요함
- **GPU 연산 자체는 `training`/`llm` 컨테이너만 사용**(MVP는 `training`만 실제로 씀) — DB/백엔드가
  로컬로 빠지면서 이 구분은 자연히 유지됨(`docker run --gpus`는 `training`/`llm`에만 적용)
- 서버 CPU/RAM이 팀별로 분리되는지(GPU만 분리되는지)는 서버 관리자 확인 필요(TBD)
- GPU 패스스루: nvidia-docker 필요
- **GPU 서버는 다인 공유 환경**(팀 5명뿐 아니라 다른 수강생들도 같은 호스트 공유) — 계정 격리,
  rootless Docker, GPU 카드 지정, 포트포워딩(SSH 터널) 등 실무 절차는 `gpuServerOps.md` 참고
- 영상 소스는 `.env`의 `CAMERA_SOURCE_<CameraId>`(예: `CAMERA_SOURCE_ELEV01`)만 환경별로 교체, 코드 불변

## 웹캠 시뮬레이션 (메인보드 입고 전) — 구현됨(신규 `CameraId` 반영 전)

> ⚠️ "카메라 1대=지점 1개=1`CameraId`" 구조 자체는 안 바뀜(위 "설치 환경" 참고) — 실제
> 코드는 아직 옛 가정("엘리베이터 2대", `ELEV-01`/`ELEV-02`) 기준 `CameraId`를 씀. 확정된
> `ELEV-TOP`/`ELEV-SIDE`로 `schemas/event.py`의 `CameraId` Enum과 `.env` 키 교체 필요
> (아직 코드 미반영).

- `streaming/cameraManager.py`: `CameraId`(`schemas/event.py`)마다 별도 `CameraManager` 인스턴스로 관리
  (`GET /api/stream/{cameraId}`, role 파라미터 없음 — 카메라 1대=지점 1개=1`CameraId`). 현재 코드의 `.env`
  키는 옛 가정 기준 `CAMERA_SOURCE_ELEV01`/`CAMERA_SOURCE_ELEV02`/`CAMERA_SOURCE_REST4F01`(하이픈 제거+대문자).
  `ELEV-01`만 기본값 `0`이라 로컬 웹캠 1대짜리 개발 환경에서 바로 동작. 나머지는 미설정 시
  해당 `cameraId` 요청만 503(다른 지점엔 영향 없음)
- 입고 후 CameraId별 독립 RTSP로 교체(소스 문자열만 RTSP URL로 교체, 로직 불변)
- `cv2.VideoCapture().read()` 동기 블로킹 → `asyncio.to_thread()`로 감쌈(적용 완료)
- **로컬에서 RTSP 경로 미리 테스트**: `debug/streaming/startRtspSim.py` — 이 PC의 웹캠 여러 대를
  각각 다른 지점(`CameraId`)에 할당해서, 지점별로 독립된 젯슨 나노 역할(FFmpeg+MediaMTX로
  RTSP 송신)을 동시에 흉내냄. `infra/checkEnv.py`처럼 필요한 것 자동 설치하지만, RTSP
  테스트하는 사람만 필요해서 `checkEnv.py`와는 별도 유지(`debug/db/`와 같은 패턴).
  WebApps/backend·docker-compose.yml과 무관 — 백엔드는 수정 없이 그대로 RTSP 수신

## 메인보드(Jetson Orin Nano Super) 엣지 코드 (미착수)

**엣지 단독으로 확정**(위 "탐지 파이프라인" 참고) — 캡처+RTSP 송신+GPIO뿐 아니라
**YOLO26 상시 추론(감지+추적+분류 전부)까지 젯슨이 담당**, MVP는 GPU/LLM 실시간 호출 없음.
Orin Nano Super(8GB, 67 TOPS)라 YOLO26 엣지 추론 여력은 충분. GPU 서버(`training`)에서
학습한 `.pt` 가중치를 젯슨에 배포해야 하는데, 배포 방식(SCP 등)은 TBD.

1. 웹캠→RTSP 송신: GStreamer(JetPack 포함) 예정. 1단계 웹캠 뷰어(Py 3.11)는 노트북 테스트 완료
2. **YOLO26 엣지 추론**: 상시감시(위/옆 카메라 공통) + 위 카메라는 투척 위치 추적+쓰레기
   종류 분류까지(MVP는 LLM 없이 YOLO26 혼자 완결 — 위 "탐지 파이프라인" 참고). 미착수
3. **투척 결과 판정**(위 카메라만): YOLO26이 추적한 투척 위치와 자신이 분류한 쓰레기 종류를
   엣지에서 직접 비교(MVP엔 GPU/LLM 결과 수신 단계 없음). 설계 전
4. 로컬 백엔드로 결과 신호 전송+GPIO 트리거: 설계 전. `RPAs/alertController.py`는 현재
   중앙에서 Mock 처리 중, 젯슨 쪽으로 이전 가능성. 전달 방식(MQTT/HTTP/WS) TBD

> Jetson Nano 4GB(Python 3.6 제약)는 발주 무산으로 더 이상 해당 없음 — Orin Nano Super는
> JetPack 6.x/Python 3.10이라 `WebApps/backend`와 문법 호환성 문제 없음.

## RPA 정책

- 오분류 시 전구+경고음 즉시 자동 트리거(재전파 없음)
- `COLLECT` 모드: 알림 전부 Mute, 탐지 로직은 계속 동작(통계만 갱신)

## 이벤트 적재

- 매 프레임 Insert 금지, 판정 시점만 저장
- `eventCategory`로 구분: misclassification(투기, 분류 결과 포함) / overflow(넘침, 분류 없이 영상만)
- **물리 쓰레기통 4개**(일반/플라스틱·캔/커피컵/종이, `binId`)가 옆 카메라(`ELEV-SIDE`) 시야
  안에 고정 설치. "플라스틱·캔" 통(`binType=plasticCan`)은 캔과 플라스틱을 물리적으로
  같이 받지만, AI는 `DetectedClass`에서 `plastic`/`can`을 별도 클래스로 구분(이미 학습
  중) — `isMisclassified` 판정 시 `plastic`/`can` 둘 다 `plasticCan`에 매핑해서 비교
  (다대일 관계, 상세는 `Docs/ERD.md` 참고). 각 통의 현재 상태(`NORMAL`/`FULL`)를 별도
  `BIN_STATES`로 지속 추적하고,
  **`NORMAL`→`FULL`로 전환되는 순간에만** overflow `EVENT` 생성+알림(기존 "5초 Cooldown"
  방식 폐기 — 상세는 `Docs/ERD.md` 참고). misclassification은 동일 카메라+클래스 5초
  Cooldown 그대로 유지
- **`EVENT`에 `detectionId`(DB 유니크, 중복 저장 방지)/`trackingId`(YOLO26 추적 ID, 디버깅용)/
  `modelVersion`/`binId`(어느 통인지, misclassification·overflow 공통) 필드 확정** — 상세는
  `Docs/ERD.md` 참고, 아직 `schemas/event.py` 등 코드 미반영
- 이미지/영상은 MongoDB GridFS, **버킷을 카메라별로 2개 분리**(`topMedia`=위 카메라/투기,
  `sideMedia`=옆 카메라/넘침) — 물리 DB 분리 아니고 같은 DB 안 GridFS 버킷만 나눈 것(연결/인증
  추가 불필요). 순수 저장 구조 관리 편의 목적, 보관정책 차이는 없음(`EVENT` 컬렉션 자체는
  카메라별로 안 나누고 하나로 유지 — 상세는 `Docs/ERD.md` 참고)
- **학습용 원본 이미지는 로컬 GridFS 재사용으로 확정**(GPU 서버 로컬 디스크 축적 방식은 기각) —
  `training`(GPU 서버)이 학습 때마다 로컬(`192.168.0.40`) GridFS에 네트워크로 직접 접속.
  역방향 SSH 터널 필요(아래 "배포 전략" 참고)

## Event Flow

```
Detect → Create Event → Save Event → Check mode
  ├─ COLLECT: 통계만 갱신
  └─ MANAGE: WS Broadcast + RPA 트리거 → 통계 갱신
```

## 포트

| 항목 | 값 |
|---|---|
| 백엔드 | 8047 (기본값 8000 대신, 타 팀 충돌 방지) |
| MongoDB 호스트 | 27020 (컨테이너 내부 27017) |

## DB 접속 (팀 공유 vs 로컬)

> ⚠️ **MongoDB를 GPU 서버(`e8000`)로 이전했던 최근 작업은 이번 "백엔드+DB는 로컬" 재조정으로
> 보류됨** — GPU 서버 `mongo` 컨테이너에 만들어둔 `root`+`user01`~`05` 계정·데이터는 당장은
> 안 쓰임(나중에 재활용할 수도 있어 지우진 않음). **"로컬" 호스트는 `192.168.0.40`으로 확정**
> (마지막 옥텟은 유동적일 수 있음) — 과거 `192.168.0.30`(팀 공유 서버)과는 별개.

- `.env`의 `MONGO_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`를 팀원마다 다르게 설정
  - **팀 배포(확정)**: `MONGO_HOST=192.168.0.40`(마지막 옥타드는 유동적)
  - 개인 로컬 개발용: `MONGO_HOST=localhost`
- `infra/checkEnv.py`, `debug/db/testDbConnection.py`, `debug/db/testCrud.py` 세 스크립트가 `.env` 키 공유 — 값 다르면 결과 엇갈림
- 디버그 스크립트는 Atlas → 로컬/자체 Docker로 전환(`mongodb+srv://` → `mongodb://`+포트)
- **팀 공유 서버 계정**: 공유 Mongo는 팀원별 계정(`user01`~`user05`, `sortMaster` DB에
  `readWrite` 권한만)으로 인증, root(관리자) 계정은 팀장만 보유. 계정 생성 절차는
  `gpuServerOps.md` 참고(GPU 서버 `mongo`용으로 만든 절차지만 다른 호스트에도 동일하게
  적용 가능). 각 팀원은 자기 `.env`의 `DB_USER`/`DB_PASSWORD`를 배정받은 계정으로 채우면 됨

## TBD

- **로컬 백엔드 → GPU 서버 `llm` 컨테이너 연결 안정성** — 고도화 단계에서 `llm`을 실제로
  쓰게 되면, GPU 서버가 SSH(2222) 외 포트를 안 열어줘서 SSH 터널을 상시 유지해야 함(끊기면
  분류 불가). 자동 재연결 방안(예: autossh) 또는 다른 접속 방식 검토 필요 — MVP엔 해당 없음
- LLM을 이용한 "불확실한 분류 안정화"/"환경별 통 모양 인식 데이터 생성"의 구체적 방식(고도화 단계)
- `DetectedClass`→`binType` 매핑표를 어디에 둘지(엣지 코드 하드코딩 vs 설정 파일 등) — 매핑표
  자체는 확정(`Docs/ERD.md` 참고), 위치만 미정
- misclassification Cooldown 5초 조정 여부(overflow는 상태 전환 기반으로 확정돼 별도
  Cooldown 없음 — 해결된 TBD 참고)
- 경고 전구 HW/GPIO 연동, 젯슨↔중앙 신호 전달 방식
- 안면인식 레포 포함 여부
- 4층 휴게실(`REST-4F-01`) 설치 진행 여부 — 고도화 단계 스트레치 목표, 시간 남으면 진행(불확실)
- **GPU 서버 CPU/디스크/네트워크 병목 실측**: GPU(VRAM)는 팀별 카드 분리로 경합 없음
  확인됨(아래 "해결된 TBD" 참고). CPU(192스레드)/디스크(2.8GB/s)는 여유 있어 보이지만
  다른 팀과 공유라 완전히 보장은 안 됨. **네트워크**는 엣지 YOLO26 확정으로 RTSP가 상시
  송출이 아니라 감지 시에만 전송되는 구조로 바뀌어서 우려가 줄었지만, 여전히 미측정 —
  메인보드 입고 후 실측 필요
- **YOLO26 `.pt` 가중치를 GPU 서버(`training`)에서 젯슨(엣지)으로 배포하는 방식**: SCP 등
  구체적 방법 미정

## 해결된 TBD

과거 결정 이력(왜 이렇게 정했는지)은 `decisionLog.md`로 옮김 — **자동 로드 안 함**, 필요할
때만 열어볼 것. 현재 상태는 위 본문 섹션들에 이미 다 반영돼 있음.
