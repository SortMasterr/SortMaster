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
- **`inference`/`side-overflow`의 GPU→로컬 백엔드 연결을 `host.docker.internal`+
  `extra_hosts`에서 `network_mode: host`로 전환** → GPU 서버에서 실제로 컨테이너를 처음
  띄워보니 둘 다 `Connection to tcp://host.docker.internal:8299 failed: Connection
  refused`로 계속 재시작 crash loop에 빠짐(SSH 역터널은 로컬 배포 서버 쪽에서 계속 열어둔
  상태였는데도 발생). 원인 파악: SSH `-R` 역터널은 기본적으로 원격 서버(GPU)의
  **루프백(127.0.0.1)에만** 포트를 리스닝하는데, Docker 브리지 네트워크를 거치는
  `host.docker.internal` 경로는 루프백이 아니라 컨테이너↔호스트 간 별도 가상 인터페이스를
  타서 이 리스닝 포트에 닿지 못함. 정공법은 GPU 서버 sshd의 `GatewayPorts`를 켜는 것이지만
  `soma` 계정에 sudo가 없어 불가능. 대신 `inference`/`side-overflow` 둘 다
  `network_mode: host`로 전환해 컨테이너가 호스트 네트워크 네임스페이스를 그대로
  공유하게 함 — 이러면 컨테이너 안 `127.0.0.1`이 GPU 서버 자신의 `127.0.0.1`과 완전히
  동일해져서 SSH 터널의 루프백 리스닝과 자연스럽게 맞음(SSH 세션에서 직접 `python
  tracking2.py`로 돌릴 때와 동일한 경로). 두 서비스 다 `ports:`로 외부 노출하는 게
  없어서(요청을 안 받고 푸시만 하는 워커) 네트워크 격리를 포기해도 손해가 없음.
  `extra_hosts`/`BACKEND_HOST=host.docker.internal` 설정 제거, `tracking2.py`/
  `sideOverflow.py`의 `BACKEND_HOST` 기본값(`127.0.0.1`)은 그대로 유효해서 코드 변경 불필요
- **재학습용 "미확정 방문" 캡처 설계 확정(`VISIT_CLIP`, `trackStarted`/`trackEnded`) —
  presence 기반 무조건 저장 + trackId 기반 정밀 매칭으로 결정** → GPU 서버에서 LLM
  review 단계를 실제 프로덕션 이미지(`waste_events/*.jpg`)로 검증하던 중(`autoTraining`
  README의 Qwen-VL 연결 검증 작업) 발견된 문제에서 출발. 지금 구조는 (1) 사람 존재 감지
  기반 녹화(`presenceGateService.py`)가 GPU 판정과 완전히 독립 동작하고 (2)
  `tracking2.py`는 투입이 **확정된 순간에만** `POST /api/events/aiDisposal`을 보내는데,
  이 둘이 서로 연결이 안 돼 있어서 확정된 이벤트조차 영상이 안 붙고(기존에 알려진
  `imageFileId` 없이 저장되는 문제와 동일 원인), **YOLO가 아예 인지를 못했거나 확정을
  못 낸 방문은 영상이 저장될 경로 자체가 없다**는 게 드러남. 이게 문제인 이유는, 이런
  "YOLO가 놓친 사례"가 바로 `autoTraining` 재학습 파이프라인이 제일 필요로 하는 데이터
  (모델이 지금 뭘 못 맞추는지 보여주는 실패 사례)인데, 지금 Collect 단계는 확정된
  `misclassification` 이벤트만 가져가는 구조라 이런 데이터가 애초에 존재하지 않음.
  - 처음엔 "GPU의 `aiDisposal` 타임스탬프와 presence 녹화 구간을 시간 범위로 매칭"하는
    단순한 안을 검토했으나, 네트워크 지연 등으로 타임스탬프가 어긋나면 매칭을 놓칠 수
    있다는 지적이 나와서 기각. 대신 GPU가 트랙을 **발견한 즉시**(확정 전에) 알리는
    `trackStarted` 신호를 추가해서, 시간 매칭은 "사람 등장 시점"처럼 지연이 훨씬 적은
    지점에서만 쓰고, 이후 `aiDisposal`/`trackEnded`는 `trackId`로 **정확히** 매칭하는
    2단계 방식으로 확정
  - **저장 여부(=presence 감지)와 라벨링(=trackId 매칭)을 명확히 분리**하는 게 핵심 — 이
    분리가 없으면 "GPU가 아예 트랙조차 시작 안 한, 가장 심각한 실패 사례"가 여전히
    안 잡힘(트랙이 없으면 매칭할 trackId 자체가 없으니까). presence 기반 저장은 GPU
    신호와 완전히 무관하게 항상 실행되도록 설계해서, 이 최악의 케이스도 최소한 영상
    자체는 남도록 함(라벨은 "미확정"으로만 남고, 그것만으로 재학습 후보 조건이 성립)
  - `EVENT`(확정 컬렉션)에 미확정 방문까지 섞으면 대시보드 통계/알림이 오염되므로,
    `VISIT_CLIP`이라는 별도 컬렉션으로 분리하기로 확정(재학습 데이터 소스 전용, 대시보드
    미노출)
  - **2026-08-26 설계 확정 후 백엔드 쪽은 구현 완료**(문서 갱신 시점 기준) —
    `visitClips` 스키마/저장소/서비스/API(`POST /api/events/trackStarted`,
    `POST /api/events/trackEnded`)와 `autoTraining` Collect 확장(미확정 클립을
    `unresolvedVisit` 후보로 수집)까지 반영됨. 남은 건 `tracking2.py`(GPU, 모델팀
    작업 필요)가 `trackStarted`/`trackEnded`를 실제로 보내는 것 하나뿐 — 이게 없으면
    `visitClip.trackIds`가 항상 비어있어서 "트랙 시도 후 실패"와 "아예 인지 못함"을
    구분하는 `unresolvedTrackIds` 기반 분류는 아직 사실상 동작하지 않음. 상세는
    `architecture.md`의 "재학습용 미확정 방문 캡처", `Docs/ERD.md`의 `VISIT_CLIP`,
    `.agentfiles/apiSpec.md`의 EP-14/EP-15 참고

- **자동 라벨링에 Qwen-VL 박스를 쓰지 않기로 확정(위치 지정 역할 배제)** → 검수 UI에 Qwen이
  제시한 박스를 그려주기 시작하면서 위치가 어긋난다는 지적이 나왔고, 배치 2026-08-26 데이터로
  실측한 결과 **사용 불가 수준**으로 확인됨. YOLO가 confidence 0.5 이상으로 찾은 프레임 88개를
  기준점으로 삼아 같은 프레임의 Qwen 박스와 비교했을 때 **IoU 중앙값 0.00, 전혀 안 겹치는
  경우 57%(50/88), IoU≥0.5는 8%, IoU≥0.75는 0%**. 느슨하게 "중심점이라도 상대 박스 안에
  들어가는가"로 채점해도 31%에 그침. 박스 면적도 체계적으로 작음(이미지 대비 중앙값 1.5% vs
  YOLO 3.5%). 프롬프트 튜닝으로 메울 격차가 아니라고 판단.
  - 기준점인 YOLO 박스도 완벽한 정답은 아니지만, IoU≥0.75가 한 건도 없는 수준이라 기준점
    오차를 감안해도 결론이 바뀌지 않음
  - **Qwen의 역할은 프레임 단위 판정("이 프레임에 쓰레기가 있는가")과 YOLO 결과 검증으로
    축소**. 좌표는 쓰지 않음. 검수 UI의 Qwen 패널에는 위치가 부정확하다는 경고를 표시함
  - 같은 이유로 **Qwen 박스를 SAM 프롬프트로 주는 방식도 성립하지 않음**(프롬프트가 틀리면
    SAM은 엉뚱한 물체를 분할함)
  - 부수적으로, Qwen이 절대 픽셀 좌표를 요청받으면 실제 이미지 크기와 다른(내부 리사이즈
    기준으로 보이는) 좌표를 내놓는 문제가 있어 **0~1 정규화 좌표로 받도록 변경**함. 위
    측정치는 이 수정 이후 기준

- **자동 라벨링 Label 단계에 causal+rgb 입력 앙상블 도입** → Label 단계는 `inputMode: causal`
  (t-2/t-1/t를 B/G/R로 합성)을 쓰는데 운영 `tracking2.py`는 단일 BGR을 쓴다는 불일치를 조사하다
  발견된 결과. 처음엔 causal이 탐지를 망치고 있다고 봤으나 **통제 비교에서 뒤집힘** — causal이
  오히려 더 잘 잡음(60프레임 기준 37% vs 25%, confidence 중앙값 0.665 vs 0.557). 대신 두 입력이
  **서로 다른 프레임을 잡아낸다**는 게 드러남(겹침 8, causal만 14, rgb만 7). 그래서 둘 다
  추론해 IoU 0.5 기준으로 박스를 병합하도록 변경 — 후보 120프레임 실측에서 **탐지 프레임
  30%→50%, 박스 42→79개**로 개선.
  - 학습 데이터 계약인 `inference.inputMode`(Publish/Sync가 샘플을 거르는 기준)는 건드리지
    않고 `labelEnsembleInputModes` 키를 새로 둠 — teacher에 넣는 입력과 학습 이미지 계약은
    별개 문제라서

- **정밀한 박스를 자동으로 얻으려던 다른 시도들은 기각(재시도 방지용 기록)** →
  - **COCO 사전학습 모델 보조 교사(YOLO11x)**: COCO의 `cup`/`bottle`/`book`이 우리 클래스와
    겹치므로 보조 teacher로 검토했으나, bestTop이 못 잡은 프레임 80개에서 **쓰레기류는
    `bottle` 1건**이 전부. 대신 `cell phone`이 239건 잡혔는데 이건 쓰레기가 아니라 벽에 붙은
    패널임. 배경 집기만 자신 있게 잡고 정작 쓰레기는 못 찾음
  - **시간축 보간/추적으로 미탐지 구간 메우기**: 같은 방문 클립에서 앞뒤 프레임이 탐지에
    성공했다면 사이 구멍을 보간할 수 있다는 착안이었으나, 미탐지 1,099개 중 **양쪽이 막힌
    구멍은 8%(86개)뿐**. 영상 135개 중 59개(44%)는 단 한 프레임도 못 잡아서 보간할 앵커
    자체가 없음. 투입 대비 효과가 낮아 보류(앙상블로 탐지율이 오른 뒤 재측정하면 값이
    달라질 수 있음)
  - **YOLO 임계값만 낮추기**: `confidence: 0.20`에 걸려 버려지는 저신뢰 탐지가 있는지 확인
    했으나, 임계값을 낮춰도 미탐지 프레임 상당수는 여전히 아무것도 내놓지 않음
  - **왜 전부 실패했나**: 미탐지 프레임을 눈으로 확인한 결과 쓰레기는 분명히 있었음(통 위
    과자 봉지, 손에 들려 통으로 들어가는 물체 등). 위에서 내려다본 각도, 손·팔에 의한 가림,
    통 표면과 뒤섞인 색, 어두운 조명이 겹친 어려운 사례들. **그리고 이 배치는 애초에
    `collectEventMedia.py`가 "YOLO가 확정하지 못한 방문"만 골라 수집한 것**이라 정의상 현재
    모델의 능력 밖 데이터임 — 실패 사례의 라벨을 실패한 그 모델로 만들려는 시도에는 구조적인
    천장이 있다는 것이 이번 조사의 결론. 그래서 **사람 검수 경로(검수 UI 마우스 드래그 박스
    그리기)를 실질적 해법으로 보고 구현**함
  - 아직 검증 안 한 선택지: **Grounding DINO**(텍스트 프롬프트로 정밀 박스를 내놓도록 설계된
    open-vocabulary 디텍터). 범용 VLM보다 그라운딩이 정확하다고 알려져 있으나 공유 GPU에
    모델 추가 배포가 필요하고 우리 클래스에서의 성능은 실측 전

- **수동 학습 모델(`training/`) 반영 경로 → registry 정식 등록으로 확정**(2026-08-28) →
  모델팀이 `training/trash_yolo26n_aug2`로 넘긴 신규 TOP 모델(mAP50 0.932, 자체 테스트
  split 247장 기준)을 반영하면서 세 가지 방법을 검토했다.
  - **기각 ①: 운영 `bestTop.pt`만 직접 덮어쓰기** — 가장 간단하지만 재학습 파이프라인은
    계속 옛 모델을 기준으로 라벨링/학습하게 되어 운영과 파이프라인이 계속 벌어짐
  - **기각 ②: bootstrap `best.pt`까지 같이 덮어쓰기** — 애초 요청은 "운영과 파이프라인을
    동일하게"였으나, `resolveActiveModel`의 docstring이 bootstrap을 **"변경 불가"**로
    명시하고 있고, 진행 중이던 2026-08-27 배치의 `cycleModel.json`이 bootstrap 해시로
    고정돼 있어서 덮어쓰면 그 배치의 `train` 단계가 해시 불일치로 죽는다
  - **채택 ③: registry 등록 + 활성 포인터** — `promoteToRegistry()`로 registry에 불변
    버전 파일을 만들고 `current.json` 포인터를 생성. 이러면 bootstrap은 불변 baseline으로
    남고, 파이프라인(Label/Train)과 운영(`deploy`가 복사)이 **같은 registry 모델**을 쓰게
    되어 원래 요청한 "둘이 동일" 상태가 설계를 깨지 않고 성립한다. 진행 중 배치도
    `cycleModel.json`이 그대로라 영향 없음
  - **`promote` 스테이지는 쓸 수 없었음** — 이 모델은 `autoTraining` 사이클 산출물이 아니라
    수동 학습 결과라 `evaluation.json`이 없고, 따라서 골든테스트 비교(`minimumMap50Gain`)
    게이트를 통과할 수 없다. 내부 함수 `promoteToRegistry()`를 직접 호출하는 방식으로
    우회했으며, 이 사실은 포인터의 `source.note`에 기록해 둠. **즉 이번 모델은 성능이
    기존보다 낫다는 것이 프로젝트 기준으로는 검증되지 않은 상태**(모델팀 자체 테스트
    결과만 신뢰해서 반영)
  - **부수적으로 드러난 사실**: 작업 전 해시를 대조해 보니 운영 `bestTop.pt`(`757f7e8b…`)와
    bootstrap(`714d19c5…`)은 **이미 서로 다른 모델**이었고, registry 디렉터리 자체가 없어
    롤백 수단이 전혀 없는 상태였다. 그래서 신규 등록 전에 기존 운영 모델을 registry에
    먼저 백필해 `rollback --version` 경로를 확보했다

- **LLM 검수에서 좌표(bbox) 출력 제거, 분류 검증만 맡김**(2026-08-28) → `reviewLabels.py`의
  응답 스키마에 있던 `qwenDetections`(클래스+정규화 좌표 배열)를 삭제하고,
  `decision`/`predictedClass`/`issues`/`confidence` 네 필드만 받도록 되돌렸다.
  - **계기**: 2026-08-27 배치 40건 실측에서 Qwen이 **실제로는 아무것도 없는 프레임에
    confidence 0.95로 객체를 만들어내는 환각**이 사람 눈으로 확인됐다. 처음엔 "YOLO가
    놓친 걸 Qwen이 잡아낸 성공 사례"로 잘못 해석했던 3건이 전부 환각이었다. 즉
    `confidence`는 신뢰 신호로 쓸 수 없고, `minimumReviewConfidence: 0.70` 임계값도
    보호 기능을 못 한다
  - 같은 배치에서 `wrongClass`가 40건 중 37건에 붙어 **전부 `manualReview`로 떨어졌다** —
    자동 승인 0건이라 LLM 검수가 사람 부담을 전혀 줄이지 못하는 상태였다
  - **판단**: `architecture.md`가 "4종 분류는 비교적 쉬운 과제"라고 본 건 **분류(검증/보정)**
    기준이었는데, 실제 구현은 좌표까지 요구하고 있었다. 정밀 로컬라이제이션은 VLM의
    구조적 약점이고(검수 UI에 "위치 부정확 — 참고만"이라고 명시해뒀던 것도 같은 인식),
    박스를 내놓으라는 압박이 환각을 유도한 것으로 봤다. 그래서 **파인튜닝보다 먼저
    원래 설계 범위로 되돌리는 쪽을 선택**
  - 프롬프트에도 "확실히 보이는 것만 보고하고, 애매하면 억지로 결론 내지 말고
    `manualReview`로 넘겨라"를 명시해 환각 유인을 더 줄였다
  - 부수 정리: Qwen 박스를 그려 보여주던 `_saveQwenAnnotatedImage`와 검수 UI의 세 번째
    패널("Qwen 라벨링")을 제거. 박스 작성은 검수 UI의 드래그 기능(사람)이 전담한다
  - **다음 선택지(아직 미결)**: 이걸로도 `wrongClass` 남발이 안 잡히면 ①Grounding DINO
    (텍스트 프롬프트 기반 정밀 박스 전용 모델, 위 "기각된 시도" 항목의 미검증 후보) 또는
    ②Qwen LoRA/QLoRA 파인튜닝. 단, 파인튜닝이 VLM의 로컬라이제이션 약점을 얼마나
    개선할지는 불확실해서 우선순위는 ①이 높다
  - **주의**: 이 판단의 근거가 된 2026-08-27 배치는 `collectEventMedia.py`가 "YOLO가 확정
    못 한 방문"만 모은 것이라 정의상 가장 어려운 데이터다. 일반 배치에서도 같은 수준으로
    나쁜지는 아직 측정하지 않았다

- **LLM 검수를 "박스별 닫힌 검증"으로 최종 확정**(2026-08-28, 같은 날 두 번째 전환) →
  위 항목(좌표 제거)만으로는 부족했고, 그 뒤 실측으로 원인을 좁혀 지금 형태에 도달했다.
  - **좌표 제거 직후의 실패**: 프레임 단위 `decision`/`predictedClass` 하나만 받도록 줄였더니
    **2,796건 전부 `predictedClass=none`, `issues=[]`, `manualReview`**로 완전히 동일한
    출력이 나왔다(평균 confidence 0.37). 환각은 사라졌지만 정보량이 0이라 이전보다 나을 게
    없었다
  - **원인 두 가지**: ①프레임에 박스가 여럿인데 클래스 필드가 하나뿐이라 "1번은 맞고 2번은
    틀렸다"를 **표현할 방법 자체가 없었다** ②환각을 막으려고 넣은 "애매하면 manualReview로
    넘겨라"가 **항상 고를 수 있는 안전한 탈출구**가 됐다. `decision`은 애초에
    `reviewLabels.review()`가 신뢰도·이슈로 다시 계산하므로 모델에게 물을 이유도 없었다
  - **배제한 가설(실측으로 확인)**: ①**모델이 이미지를 못 보는 것 아님** — 스키마 없이 자유
    서술로 물으니 "쓰레기통 3개, 손이 종이컵을 넣고 있다"까지 정확히 묘사했고, 이미지를 빼고
    같은 질문을 하면 전혀 다른 장면을 지어내 대조가 확실했다 ②**guided decoding 탓도 아님** —
    새 스키마를 적용/미적용으로 각각 물었을 때 답이 일치했다
  - **채택**: 열린 생성("이 프레임에 뭐가 있나")을 닫힌 검증("이 박스가 맞나")으로 바꿨다.
    `boxVerdicts` 배열 길이를 **YOLO 탐지 개수에 정확히 고정**(`minItems == maxItems`)해
    빈 배열로 회피할 수 없게 하고, 박스마다 `actualClass`(4종 + `notTrash`)를 반드시 답하게
    한다. 프레임 단위로는 `hasMissedTrash`(불리언)와 `confidence`만 받고, `issues`/`decision`은
    파이프라인이 YOLO 라벨과 대조해 도출한다(`extraBox`/`wrongClass`/`missingObject`)
  - **실측 결과**: 6프레임 표본에서 `[Coffeecup, Recyclables] → [notTrash, Recyclables]`처럼
    박스별로 판단이 갈리고 confidence도 0.54~0.91로 분포했다. 전부 일치하는 프레임은
    `issues=['none']`이 되어 **자동 승인 경로가 실제로 살아났다**(직전까지는 100%
    manualReview)
  - **남은 검증**: 사람이 검수한 결과와 대조해 `actualClass` 정확도를 실측해야 한다. 강제로
    답하게 만든 구조라 "아무렇게나 찍는" 위험이 있고, 표본 6건으로는 판단할 수 없다. 이게
    안 되면 그때는 Grounding DINO 또는 파인튜닝으로 넘어간다(위 항목 참고)
