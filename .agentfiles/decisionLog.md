# decisionLog.md

`architecture.md`에서 옮겨온 과거 결정 이력(해결된 TBD). **자동 로드 안 함** — 현재 상태는
`architecture.md` 본문에 이미 반영돼 있으니, "왜 이렇게 정했는지" 이유가 궁금할 때만 열어볼 것.

## 해결된 TBD

- Git 브랜치 전략 → `Docs/skills/github/README.md`
- IDE/AI 코딩 툴 → 개인별 사용
- **탐지 모델 최종: MVP는 YOLO26 단독, Qwen3-VL-8B는 고도화 전용** → 여러 단계를 거쳐 확정
  (①YOLOv8-Nano+Qwen3-VL-8B 실시간 병행 → ②엣지 YOLO26+중앙 LLM 실시간 하이브리드 → ③현재:
  YOLO26이 쓰레기 종류 분류까지 흡수해서 MVP는 LLM을 아예 안 씀). YOLOv8-Medium은 애초에
  Qwen3-VL-8B로 대체됐던 것도 이 흐름에 포함. 최종 상태는 `architecture.md`의 "탐지
  파이프라인"/"LLM 활용" 참고
- GPU 배분 → L40S 4장 중 팀당 1장 전용 할당(타 팀과 경합 없음)
- **손 감지 트리거 조건 폐지** → "손 O/X + 쓰레기 O" 조합 판정 대신 쓰레기 감지 자체가
  트리거로 확정. 투기(위 카메라 단독)/넘침(옆 카메라 단독, 위치 특정 없이 즉시 알림) 두
  카테고리로 완전히 분리(`architecture.md`의 "탐지 파이프라인" 참고)
- **넘침 판정에서 위 카메라 연동 폐지** → 옆 카메라 단독으로 처리(위 카메라가 위치를
  재확인하는 단계는 없음). 단, "어느 통인지"는 옆 카메라 자체가 보고 있는 물리 통 4개
  (`binId`) 중 하나로 여전히 식별함 — `BIN_STATES`로 지속 추적하다 `NORMAL`→`FULL` 전환
  시점에만 이벤트 생성(상세는 `Docs/ERD.md` 참고)
- **설치 위치** → "엘리베이터 2대" 계획은 착오였던 것으로 정정, 실제로는 12층 엘리베이터 앞
  쓰레기통 1개뿐(`ELEV` 명칭 유래). 카메라 지점 2개(위+옆), `CameraId`는 `ELEV-TOP`/`ELEV-SIDE`로
  확정 — 설치 위치가 1곳이라 번호 불필요. "카메라 1대 = 지점 1개 = `CameraId` 1개 = 독립
  젯슨나노 1대" 규칙 자체는 유지(안 깨짐)
- **투기(misclassification) 판정 담당 카메라** → 위 카메라 단독으로 확정(넘침은 옆 카메라
  단독 — 위 항목 참고, 위/옆이 서로의 판정에 관여하지 않음)
- **메인보드 하드웨어** → Jetson Nano 4GB 발주 무산, Jetson Orin Nano Super Developer Kit로
  확정(icbanq 무료 렌탈). Python 3.6 제약 문제 자체가 해소됨(JetPack 6.x/Python 3.10)
- **`EVENT`는 카메라별 물리 분리 안 함, GridFS 영상만 카메라별 버킷 2개로 분리** → `EVENT`
  컬렉션은 하나로 유지(`GET /api/events`가 카메라 구분 없이 한 번에 조회하는 구조라 나누면
  손해만 큼). 영상 저장은 물리 DB가 아니라 같은 DB 안 GridFS 버킷만 `topMedia`(위 카메라)/
  `sideMedia`(옆 카메라)로 나눔 — 저장 구조 관리 편의 목적, 보관정책 차이는 없음(상세는
  `Docs/ERD.md` 참고)
- **물리 쓰레기통 4개(`binId`) + `BIN_STATES` 지속 상태 추적 확정** → 옆 카메라 시야 안에
  일반/플라스틱·캔/커피컵/종이 통 4개가 고정 설치. 각 통의 `NORMAL`/`FULL` 상태를 `BIN_STATES`
  컬렉션(신규)으로 지속 추적하다가 `NORMAL`→`FULL` 전환 시점에만 overflow `EVENT` 생성.
  `EVENT.binId`는 misclassification(투척 통)/overflow(가득 찬 통) 둘 다에서 사용
- **`detectionId`/`trackingId`/`modelVersion` 필드 추가 확정** → `detectionId`(DB 유니크
  인덱스, 중복 저장 방지), `trackingId`(YOLO26 추적 ID, 디버깅용, 전역 유니크 아님),
  `modelVersion`(재학습 이후 이벤트 비교용). 상세는 `Docs/ERD.md` 참고
- **MVP 배포 위치 재조정** → 과거 "백엔드+DB+LLM 추론+학습을 GPU 서버 안에 전부 통합
  배포" 결정을 뒤집음. **백엔드+DB는 로컬(`<LOCAL_BACKEND_IP>`, 실제 값은 Notion 참고)**, **GPU
  서버는 YOLO26 학습(`training`)만** MVP 범위(`llm`은 고도화 단계 전까지 기동 안 함). 이유:
  GPU 서버는 타 팀과 공유하는 자원이라 부담을 줄이고, 백엔드/DB는 원래도 GPU를 안 써서
  로컬에 둬도 기능상 문제없음. GPU 서버에 이미 만들어둔 MongoDB 계정(`root`/`user01`~`05`)은
  당장 안 쓰이지만 보존
- **학습용 원본 이미지는 로컬 GridFS 재사용으로 확정** → GPU 서버 로컬 디스크에 별도로
  누적하는 방식은 기각. `training`(GPU 서버)이 학습마다 로컬(`<LOCAL_BACKEND_IP>`) GridFS에
  네트워크로 직접 접속 — 역방향 SSH 터널이 MVP부터 필요(`architecture.md`의 "배포 전략" 참고)
- **`binType`은 `plasticCan` 유지, `DetectedClass`에 `can` 추가** → 물리 통은 캔·플라스틱을
  같이 받지만 AI는 이미 둘을 별도 클래스로 학습 중이라, `binType` 값을 통일하는 대신
  `DetectedClass`→`binType` 매핑(다대일)으로 처리하기로 확정(`Docs/ERD.md` 참고)
- **`DetectedClass`에서 `mixed`/`uncertain` 제외 확정** → 라벨링 기준을 어떻게 정할지
  고민하다가, 팀 자체 라벨링 시엔 어차피 모든 대상을 5종(general/paper/plastic/can/
  coffeeCup) 중 하나로 분류할 수 있다고 판단해서 아예 클래스에서 뺌. `DetectedClass`가
  `binType`(4종)에 다대일로 완전히 매핑되는 닫힌 집합이 되어, "매핑 없는 값" 예외 처리
  자체가 필요 없어짐(예전에 검토했던 "mixed/uncertain은 매핑 없어서 자동 오분류" 로직도
  같이 폐기 — 애초에 그런 값이 안 나옴)
- **문서에 실제 서버 IP(로컬 배포 서버/과거 팀 공유 서버/GPU 서버, 3개)가 여러 커밋에 걸쳐
  평문으로 올라간 것 발견 → 플레이스홀더로 마스킹** → 레포가 public이라 이미 push된 과거
  커밋(`a5606c1`/`29a427f`/`82c74b9` 등, `origin/dev`/`origin/feature/rtsp-streaming-hardening`)
  에는 여전히 남아있음(history rewrite는 팀 조율 부담이 커서 일단 보류, 프로젝트 종료 시점에
  한 번에 정리하거나 그때 private 전환 검토). 앞으로는 문서에 실값 대신 `<GPU_SERVER_IP>`/
  `<LOCAL_BACKEND_IP>` 같은 플레이스홀더만 쓰기로 확정 — 상세 규칙은 `CLAUDE.md`의 "민감정보
  처리" 절 참고(이 항목 자체도 실제 IP를 다시 적지 않도록 값 대신 설명으로만 남김)
- **메인보드: Jetson Orin Nano Super → 라즈베리파이로 최종 전환, YOLO26 추론도 엣지→GPU
  서버로 이관** → Orin Nano Super 발주 자체는 확정됐었으나, 실제 메인보드 용도가 "YOLO26
  엣지 상시 추론"이었던 게 라즈베리파이로는 성능상 불가능해져서 통째로 재설계. 라즈베리
  파이는 캡처+RTSP 송신+GPIO/스피커만 담당(추론 없음), YOLO26 상시 추론(감지+추적+분류)은
  GPU 서버 신규 `inference` 컨테이너가 API 통신으로 로컬 백엔드와 연동(GPU `inference`는
  프레임 연속성이 필요한 판정까지만 담당하고, 통 상태/쿨다운/최종 이벤트 생성은 여전히
  로컬 백엔드가 소유 — 경량 JSON 신호만 오가므로 지연 영향 작음). 이 결정으로 "MVP는
  GPU/LLM 실시간 호출 없음"이었던 과거 전제가 깨짐 — MVP부터 GPU 서버가 실시간 경로에
  들어오지만 LLM은 여전히 미사용. 상세는 `architecture.md`의 "탐지 파이프라인"/"배포
  전략"/"메인보드(라즈베리파이) 엣지 코드" 참고
- **SIDE(넘침) 판정은 룰 베이스로 확정, GPU 서버 미사용** → 처음엔 TOP/SIDE 둘 다 GPU
  `inference`(YOLO26)가 처리하는 걸로 논의됐으나, 실제로는 SIDE가 룰 베이스(딥러닝 모델
  아님)로 진행하기로 확정. GPU 연산 자체가 필요 없어서 SIDE는 GPU 서버로 RTSP를 보낼
  이유가 없어짐 — **로컬 백엔드가 SIDE RTSP를 직접 받아 룰 베이스 판정+`BIN_STATES`/
  `EVENT` 생성까지 전부 수행**. 결과적으로 GPU 서버 `inference`는 **TOP 전용**이 되고,
  SSH 역터널도 TOP 카메라 포트 1개만 필요(기존에 TOP/SIDE 2개로 잡았던 계획 정정)
- **자동 라벨링 검증 파이프라인(LLM 활용 ①)을 지금 단계부터 활성화, 파인튜닝은 계속 후순위** →
  "이미지 폴더 → 전처리+자동 라벨링 도구로 1차 라벨 생성 → 자동 라벨링이 100%는 아니라서
  불확실한 라벨만 LLM이 검증/보조"하는 파이프라인을 `training` 컨테이너(전처리+자동
  라벨링)와 `llm` 컨테이너(검증 API)를 조합해 지금부터 진행하기로 확정 — 과거 "고도화,
  MVP 이후"로 미뤄뒀던 `llm` 컨테이너 사용 시점이 앞당겨짐(단, 실시간 탐지 경로엔 여전히
  안 씀). 이 검증은 **베이스 Qwen3-VL-8B-Instruct + 프롬프트만으로 우선 진행**하기로
  확정 — 파인튜닝은 그 자체로 좋은 라벨 데이터가 먼저 있어야 하는데 지금 이 파이프라인의
  목적이 "라벨이 아직 불확실해서 LLM 보조를 받겠다"는 거라 선후 관계가 꼬임, 정확도 부족이
  실제로 확인되면 그때 파인튜닝 착수하기로 함(계속 미착수/후순위)
- **4층 휴게실(`REST-4F-01`) 설치는 사실상 제외** → "고도화 단계 스트레치 목표"로 열어뒀던
  항목을 진행 가능성이 낮다고 판단해 계획에서 뺌(완전 취소 선언은 아니고, 필요해지면 재검토)
- **"MVP 종료, 고도화 단계로 전환" 확정** → 수동 HTTP 스텁(`services/detectionService.py`,
  `debug/detection/`)으로 이벤트 플로우를 시연하는 MVP 데모는 끝났고, 지금부터는 라즈베리
  파이/GPU `inference` 실제 하드웨어·소프트웨어 통합, LLM 자동 라벨링 검증 등 "진짜 구현"
  단계(고도화). 단, 데모가 끝났다고 해서 하드웨어 통합까지 다 끝난 건 아님 — 문서 곳곳의
  "아직 미착수"/TBD 표시는 실제 구현 상태를 그대로 반영한 것이라 안 바뀜. 문서에서
  "MVP는 X로 확정" 같이 **단계를 이유로 결정을 하드지 않는 표현**은 정리 대상이지만,
  "아직 미착수"처럼 **진짜 구현 상태를 나타내는 표현**은 그대로 유지
- **GPU 연동 방식을 "RTSP 상시 pull(SSH 역터널)"에서 "프레임 샘플링 API 호출"로 전환** →
  TOP 카메라 RTSP를 GPU 서버 `inference`가 SSH 역터널로 직접 당겨받던 기존 방식은,
  라즈베리파이→GPU 서버 구간이 끊기면 탐지 전체가 멈추는 단일 장애점이었음(`architecture.md`
  TBD의 최우선 항목이었음). 대신 TOP 카메라 RTSP도 SIDE처럼 로컬 백엔드로만 보내고,
  로컬 백엔드가 `cameraManager.readFrame()`으로 5~10fps 정도만 샘플링해서 GPU `inference`의
  추론 API를 호출하는 방식으로 재설계 — 라즈베리파이는 GPU 서버와 아예 연결될 필요가
  없어지고(로컬 백엔드만 상대), GPU API 연결이 끊겨도 라이브뷰/녹화는 영향 없이 AI 판정만
  그 순간 스킵되는 정도로 실패 범위가 축소됨(도커 PC RTSP 파이프라인 안정화 작업 중,
  기존 GPU 직결 구조의 위험을 다시 검토하다가 나온 결정). 대신 GPU `inference`는 투척
  궤적처럼 프레임 연속성이 필요한 상태를 세션 단위로 관리해야 함(정확한 API 스펙은 TBD).
  상세는 `architecture.md`의 "탐지 파이프라인"/"배포 전략", `gpuServerOps.md`의 "외부 접속" 참고
- **GPU 프레임 전송을 "상시"가 아니라 "사람 존재 감지로 게이팅"하기로 확정** → 위 API
  전환 결정 이후 나온 후속 논의. 처음엔 5~10fps를 24시간 상시로 GPU에 보내는 안을
  검토했으나, 두 가지 반박이 나옴: (1) 이렇게 하면 "GPU RTSP 파이프라인을 안 만들어도
  된다"는 이점은 유지되지만 "GPU 부담을 줄인다"는 이점은 상시 추론으로 인해 희석됨(하루
  대부분은 통 앞에 아무도 없는데 계속 GPU를 씀 — `training`/타 팀과의 카드 경합에 불리),
  (2) 반대로 "모션(움직임) 감지로 게이팅하자"는 대안도 검토했으나, 단순 프레임 차이로는
  실제 투척 동작인지 그냥 지나가는 사람인지 구분 못 하고 트리거가 늦게 걸려 투척 시작
  순간을 놓칠 위험이 있어 기각(정밀 동작 인식이 필요한 실무 사례들은 모션 같은 거친
  프록시로 게이팅하지 않고 실제 탐지를 상시/준상시로 돌리는 경우가 많음). 최종적으로
  "모션"보다 훨씬 안정적이고 이르게 걸리는 신호인 **"사람이 통 근처에 있는지"**로
  게이팅하기로 확정 — 사람이 감지되는 동안만(투척 발생 가능 구간 전체를 보수적으로 커버)
  5~10fps 상시 샘플링하고, 사람이 없으면 GPU 호출 자체가 없음. 이러면 궤적을 놓칠
  걱정도, GPU 자원을 상시로 낭비하는 문제도 둘 다 해소됨(SIDE의 룰 베이스 판정과 마찬가지로
  "완전 자동화 이전에 사람이 실제로 관여하는 순간에만 무거운 연산을 쓴다"는 원칙과도 일치).
  구체적인 사람 존재 감지 구현 방식은 TBD. 상세는 `architecture.md`의 "탐지 파이프라인" 참고
<<<<<<< HEAD
- **GPU 연동 방식을 "로컬 백엔드가 프레임 샘플링해 GPU API 호출·폴링"에서 "GPU가 자체
  판단 후 로컬 백엔드로 결과 푸시"로 재차 전환** → 위 두 항목(세션 API 설계, 존재 감지
  게이팅)은 GPU `inference`를 우리가 새로 만드는 서비스라고 가정하고 세운 설계였음. 실제로
  모델팀이 이미 작성해둔 코드(`models/trashdetect/tracking2.py`)를 확인해보니, 이 스크립트가
  **TOP 카메라 영상을 직접 열어서 YOLO26+BoT-SORT로 자체적으로 투척 완료를 판단**하고
  (쓰레기 bbox가 통 bbox 안에서 머물다 사라지면 확정), `detectedClass`/`binId`/정상·오분류
  판정(`result`)까지 전부 스크립트 안에서 계산해서 **자기가 먼저 로컬 백엔드로 결과를
  POST하는 구조**로 이미 설계돼 있었음(`handle_disposal_event()`에 백엔드 POST 예시가
  주석으로 준비돼 있음). "이미 이걸로 모델링 중이니 스크립트를 고치기보다 백엔드가
  맞추자"는 방향으로 결정 — 로컬 백엔드가 프레임을 보내고 폴링하는 세션 API(`EP-INF-01~03`
  형태로 초안까지 잡았던 것, `Docs/skills`에 반영 전 폐기)는 전제 자체가 틀려서 만들지
  않기로 함. 대신 `POST /api/events/aiDisposal`(신규, `controllers/api.py`)을 만들어
  `tracking2.py`의 JSON을 그대로 받아 내부 `EventCreate`로 변환 후 기존
  `eventService.createEventWithStatus`(쿨다운/멱등성 파이프라인)를 재사용. 사람 존재
  감지 게이팅(`presenceGateService.py`)은 폐기하지 않고 유지하되, 역할이 "GPU 프레임
  전송 트리거"에서 "라이브뷰/DB 클립용 녹화 시작·종료 트리거"로 재정의됨(GPU 판정과는
  무관, 완전히 독립된 경로) — 이 결정으로 `_startGpuSamplingStub`/`_stopGpuSamplingStub`
  스텁도 제거함(GPU에 프레임을 보낼 일 자체가 없어짐). 상세는 `architecture.md`의
  "탐지 파이프라인"/"배포 전략" 참고
- **`DetectedClass`를 5종(general/paper/plastic/can/coffeeCup)에서 4종(general/paper/
  plasticCan/coffeeCup)으로 축소, plastic·can 통합** → 위 결정 과정에서 `tracking2.py`의
  실제 YOLO26 모델이 plastic과 can을 구분하지 못하고 `recyclables` 하나로만 낸다는 게
  확인됨(**당시엔 "8클래스 모델: 쓰레기 4종+통 4종"로 오인했으나, 이후 아래 항목에서
  실제로는 쓰레기 4종만 학습된 모델이라는 게 확인됨** — 이 축소 결정 자체(plastic/can
  통합)는 영향 없이 그대로 유효). 과거 "plastic/can을 별도 클래스로 유지하고 `binType`에
  다대일로 매핑"하기로 확정했던 결정(위 `binType`은 `plasticCan` 유지 항목)을 다시 뒤집음
  — 모델이 애초에 구분을 못 하는 상황에서 스키마만 분리해봤자 `can` 값이 영구히 안 나오는
  죽은 값이 되고, 물리적으로도 플라스틱과 캔은 같은 통에 버려서 실용상 구분할 이유가
  약하다고 판단. `DetectedClass.PLASTIC_CAN = "plasticCan"` 하나로 통합해서
  `BinType.PLASTIC_CAN`과 값이 완전히 일치하게 됨(예전의 "여러 DetectedClass가 하나의
  binType에 매핑"되는 다대일 관계가 사실상 해소). 관련 테스트/디버그 스크립트 전부
  `plasticCan`으로 갱신, `schemas/event.py`/`services/eventService.py` 참고
- **통(bin) 위치 판정은 YOLO 모델이 아니라 룰 베이스(고정 ROI)로 확정, `tracking2.py`의
  YOLO26 모델은 쓰레기 4종만 담당** → 바로 위 항목에서 "8클래스 모델(쓰레기 4종+통 4종)"로
  판단했던 게 실제로는 착오였음이 실기기 테스트로 드러남. GPU 서버에서 `tracking2.py`를
  실제로 돌려보니 `model.names`가 쓰레기 4종만 반환(통 클래스 0개, `[WARNING] class 4~7:
  actual=None`)하고 투입 확정 이벤트가 하나도 안 생김 — 처음엔 "모델 파일이 잘못됐다"고
  판단했으나, 모델팀에 확인한 결과 **통 위치는 애초에 러닝 베이스가 아니라 룰 베이스로
  설계된 것**이었음(SIDE 카메라의 `roi.json` 고정 좌표 패턴과 동일한 원리를 통 4개로
  확장). 실제로 받은 개선 버전 스크립트에는 `RULE_BASED_BIN_ROIS`(통 4개의 화면 비율
  좌표, 0~1 정규화)가 이미 반영돼 있었고, 이걸로 재테스트하니 정상적으로 투입 이벤트가
  생성됨(데모 영상 기준 최초 확정 이벤트: `result: correct`, `POST
  /api/events/aiDisposal`까지 end-to-end 성공). 즉 `current.pt`(쓰레기 4종만 학습)는
  처음부터 올바른 모델 파일이었고, 문제는 모델 파일이 아니라 `tracking2.py`의 구버전이
  통 위치까지 모델에 요청하도록(`model.predict(classes=BIN_CLASS_IDS)`) 잘못 짜여 있었던
  것 — 상세는 `architecture.md`의 "탐지 파이프라인" 참고
- **SIDE(넘침) 판정을 룰 베이스에서 MobileNet_V3_Small로 재전환** → 위 "SIDE(넘침) 판정은
  룰 베이스로 확정" 항목(2026-08-19)을 다시 뒤집음. `models/trashoverflow/trashoverflowApi.py`
  (`ukjin`, 커밋 `9cee215`/`653f13e`)가 이미 이 모델로 구현·푸시된 상태라 이걸 실제 SIDE
  판정으로 채택하기로 확정 — 처음엔 독립 실행형 FastAPI 앱으로 `main.py`에 마운트 안 되고
  이벤트 저장도 TODO로 비어있었으나, 이후 `feature/side-overflow-integration` 브랜치
  (2026-08-21~22, `ed7f325`)에서 `services/overflowDetectionService.py`로 옮겨
  `cameraManager`(ELEV-SIDE 프레임)+`eventService`(이벤트 저장/WS 브로드캐스트)와 실제
  연동 완료. **단, "GPU 서버 미사용" 원칙은 그대로 유지** — MobileNet_V3_Small은 경량
  모델이라 로컬 백엔드에서 CPU로 추론 가능(`torch.cuda.is_available()`로 GPU 있으면 쓰고
  없으면 CPU로 자동 폴백하도록 이미 구현됨), SIDE가 GPU 서버와 연결될 필요는 여전히 없음.
  원래 트레이드오프였던 "룰 베이스라 가볍다"는 이제 "모델이 가벼워서 로컬 CPU로 충분하다"로
  대체됨. ROI로 크롭한 이미지를 모델에 넣어 `normal`/`overflow` 2클래스로 분류하고, 연속
  30초 이상 `overflow` 유지 시 최종 판정(세션 상태 기반). 모델 가중치 파일(`bestSide.pt`)은
  `.gitignore` 대상이라 레포에 없음 — 실제 추론 테스트는 가중치 파일 확보 후 가능. 이 브랜치는
  `dev`에 merge 완료(2026-08-25). `architecture.md`/`README.md`/`Docs/ERD.md`/
  `Docs/API_SPEC.md`/`.agentfiles/apiSpec.md`/`Docs/DATASET_DESCRIPTION.md`의 SIDE 관련
  서술도 이 결정에 맞춰 갱신됨
- **SIDE(넘침) 판정을 로컬 백엔드 CPU 추론에서 GPU 서버로 재이관, TOP과 완전히 동일한
  구조로 통일** → 위 "GPU 서버 미사용 원칙 유지" 결정(같은 날, 2026-08-25)을 몇 시간 만에
  다시 뒤집음. 기술적 필요(SIDE는 여전히 GPU 연산이 굳이 필요 없음, MobileNet_V3_Small은
  CPU로도 충분)가 아니라 **아키텍처 일관성**이 이유 — TOP/SIDE가 서로 다른 위치(GPU 서버 vs
  로컬 백엔드)에서 도는 구조는 팀 밖 설명(CTO 등)에 설득력이 떨어진다고 판단, "탐지 모델은
  전부 GPU 서버에서 돈다"로 통일. `services/overflowDetectionService.py`(로컬 인프로세스
  버전, `main.py` 연동 포함)와 `models/trashoverflow/trashoverflowApi.py`(구버전 독립
  FastAPI 서버)는 전부 제거하고, `models/trashoverflow/sideOverflow.py`(신규)로 대체 —
  `models/trashdetect/tracking2.py`(TOP)와 완전히 같은 패턴: 로컬 백엔드가 서빙하는
  `GET /api/stream/ELEV-SIDE`를 GPU가 SSH 역터널(`-R 8299`)로 구독해서 자체 판정 후,
  `POST /api/binStates`(EP-11)로 로컬 백엔드에 결과 푸시(로컬 백엔드가 SIDE를 호출하는 게
  아니라 GPU가 호출). **폴백 없음** — GPU 서버/터널이 끊기면 TOP처럼 SIDE도 그 동안 판정이
  멈춤(오분류 이벤트와 동일한 리스크 프로필로 통일하는 것도 일관성 목적에 포함). 로컬
  백엔드는 이제 torch/torchvision이 필요 없어져서 `infra/checkEnv.py`의 `requiredPackages`
  에서 제거(GPU 서버 쪽 venv에서만 필요, `gpuServerOps.md` 참고). **실제 GPU 서버 배포/
  실행+end-to-end 검증 완료**(2026-08-25 — `python sideOverflow.py` 실행 → 실제 SIDE
  스트림 구독 → 연속 30초 `overflow` 유지 → `POST /api/binStates -> 200`까지 확인, TOP과
  동일하게 검증됨). 아직 안 된 것: 상시 서비스화(TOP과 같은 TBD), `RULE_BASED_BIN_ROIS`처럼
  `roi.json` 좌표도 데모 기준값 그대로라 재보정 필요(지금 판정 결과 자체는 무의미 — 통
  없이 테스트해서 confidence만 높게 나오는 상태)
- **`tracking2.py`/`sideOverflow.py` 상시 서비스화: systemd 대신 Docker화로 확정** → GPU
  서버가 재부팅돼도 알아서 다시 뜨게 만드는 방법으로 라즈베리파이 RTSP 송신에 쓴 systemd
  패턴을 검토했으나, GPU 서버는 이미 rootless Docker + `sudo loginctl enable-linger soma`
  설정이 돼 있어서(`gpuServerOps.md`, 원래 `training`/`llm` 컨테이너 유지 목적으로 구성)
  Docker 데몬 자체가 재부팅 시 자동 기동됨 — 그러면 `restart: unless-stopped`만으로 새
  systemd 유닛 없이 같은 효과를 냄. `WebApps/backend/models/trashdetect/Dockerfile`/
  `WebApps/backend/models/trashoverflow/Dockerfile`(둘 다 `training/Dockerfile`과 같은
  `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime` 베이스, GPU 드라이버 호환 검증된 태그
  재사용) + `docker-compose.yml`의 `inference`/`side-overflow` 서비스로 구현 — 서비스 키를
  처음에 `sideOverflow`(camelCase)로 뒀다가 Docker 이미지 이름 규칙(소문자만 허용)
  위반으로 `docker compose build` 자체가 실패해서 `side-overflow`(케밥케이스)로 즉시
  수정(`naming.md`의 "Docker 이미지/컨테이너는 케밥케이스" 규칙을 서비스 키 자체에는
  놓쳤던 부분). 또한 `backend`/`mongo`(로컬 전용)와 `inference`/`side-overflow`(GPU
  전용)가 같은 `docker-compose.yml`을 공유하는 구조라, 실수로 이름 없이 `docker compose
  up`을 치면 로컬/GPU 어느 쪽에서든 엉뚱한 서비스가 같이 뜰 위험이 있다는 지적을 받고
  `backend`/`mongo`는 `local` profile, `inference`/`side-overflow`는 `gpu` profile로
  분리(`training`/`llm`의 온디맨드 profile과는 목적이 다름 — 상시 기동은 유지하되 "맨 처음
  뭘 켤지"만 안전하게 구분, `restart: unless-stopped`가 재부팅 후 자동 복구를 담당하므로
  profile 자체는 이 상시성에 영향 없음). 가중치 파일(`bestTop.pt`/`bestSide.pt`, 둘 다
  `.gitignore` 대상)은 이미지에 안 굽고 `training`처럼 디렉터리 전체를 볼륨 마운트 —
  재빌드 없이 가중치만 교체 가능. 컨테이너 안에서는 `127.0.0.1`이 컨테이너 자신을
  가리켜서 SSH 터널에 못 닿으므로, `tracking2.py`/`sideOverflow.py`에 `BACKEND_HOST`
  환경변수(기본값 `127.0.0.1`, compose에서 `host.docker.internal`로 오버라이드)를
  추가해서 호스트 직접 실행/Docker 실행 둘 다 코드 수정 없이 지원. **이걸로도 SSH 역터널
  자체가 살아있는지는 안 풀림** — 그건 로컬 배포 서버 쪽 `autossh` 문제로 별개(TBD). 실제
  GPU 서버에서 이 이미지를 빌드+기동해본 적은 아직 없음(코드/설정만 작성, 검증은 다음 단계)
- **`DetectedClass`/`BinType` 값을 `general`/`plasticCan`에서 `normal`/`recyclables`로
  리네임(별도 세션에서 진행, `52bd86a`)하는 과정에서 `tracking2.py`의 `EXPECTED_CLASS_NAMES`/
  `TRASH_CLASSES`/`TRASH_TYPE_MAP` snake_case 값도 같이 camelCase(`trashNormal` 등)로
  "정리"됐다가 발견 즉시 되돌림** → 이 세 dict의 문자열은 API 계약(`DetectedClass`)이
  아니라 **학습된 모델 파일(`bestTop.pt`)의 `model.names`와 비교하는 용도**라 코드
  컨벤션과 무관한 외부 고정값(2026-08-25 GPU 서버 실행 결과: `{0: 'trash_normal', 1:
  'trash_paper', 2: 'trash_recyclables', 3: 'trash_coffeecup'}`, 전부 snake_case).
  camelCase로 바꾸면 `model.names[i]`가 `TRASH_CLASSES`에 하나도 안 걸려서 **TOP 탐지가
  전부 조용히 무시됨**(에러 없이 감지 이벤트가 그냥 하나도 안 생기는 형태라 발견이 늦어질
  위험이 큼) — `dev`에 merge된 상태로 며칠 있었으면 실제 배포에서 조용히 터졌을 사안.
  발견 즉시 snake_case로 되돌리고 `naming.md`에 "모델이 내놓는 고정 문자열은 camelCase
  변환 대상 아님" 예외 추가. `RULE_BASED_BIN_ROIS`/`BIN_TYPE_MAP`의 `boxNormal` 등은
  모델 출력과 무관한 내부 전용 키라 camelCase로 남겨둬도 문제없음(둘 다 서로 일관되게
  이미 바뀌어 있었음, 그쪽은 그대로 유지)
- **TOP 모델 클래스명 표기를 snake_case로 영구 고정 확정(재학습해도 camelCase로 전환
  안 함)** → 위 회귀를 되돌리는 과정에서, `autoTraining/README.md`/`pipelineConfig.yaml`에
  팀원 `ukjin`이 별도로 남긴 "다음 재학습부터는 camelCase 목표"라는 계획(`10aff38`)과
  충돌하는 게 발견됨 — 처음엔 "지금 모델은 snake_case 유지, 다음 재학습되는 새 모델부터
  camelCase로 전환, 그 시점에 `tracking2.py`도 같이 바꾼다"는 과도기 방안으로 절충했으나,
  재학습이 당장 가능한 상태가 아니고(`autoTraining/README.md`의 "실행 전 반드시 해결할
  문제"에 입력 영상/기존 데이터셋 미준비, 전체 E2E 미검증 등이 남아있음) 나중에 또 같은
  종류의 혼선이 재발할 여지가 있다고 판단, **"TOP 관련 클래스명은 항상 snake_case"를
  `naming.md`의 영구 예외로 확정**하는 쪽으로 단순화함. `pipelineConfig.yaml`의
  `dataset.classes`도 camelCase 목표값에서 다시 snake_case로 되돌림 — 앞으로 재학습을
  하더라도 이 표기는 그대로 유지(camelCase 전환 계획 자체를 폐기)
- **위 "TOP 클래스명 영구 snake_case 예외" 결정을 팀 재회의로 다시 뒤집음 — 전체
  camelCase 통일 재확정, 다음 TOP 모델도 포함** → 팀에서 다시 논의한 결과 "TOP만 예외로
  영구 snake_case"보다 "전체 다 camelCase로 통일, 다음 재학습되는 TOP 모델도 camelCase로
  만든다"는 `ukjin`의 원래 계획(`10aff38`) 쪽으로 최종 확정. `autoTraining/pipelineConfig.yaml`의
  `dataset.classes`를 다시 camelCase(`trashNormal` 등)로 되돌림. **단, 지금 운영 중인
  `bestTop.pt`가 여전히 snake_case를 내놓는다는 사실 자체는 안 바뀌므로**,
  `tracking2.py`의 `EXPECTED_CLASS_NAMES`/`TRASH_CLASSES`/`TRASH_TYPE_MAP`은 새
  camelCase 모델이 실제로 재학습·Promote·Deploy되기 전까지는 계속 snake_case를 유지 —
  코드는 안 건드리고 문서(`naming.md`/`autoTraining/README.md`)만 "영구 예외"에서 "과도기
  상태, 새 모델 배포 시 함께 전환"으로 다시 정정. 새 모델이 실제로 나오면 그 시점에
  `tracking2.py` 세 값도 camelCase로 바꿀 것 — 이번엔 되돌리지 않고 유지
