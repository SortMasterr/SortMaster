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
- **`BIN_STATES` 코드 구현(EP-10/EP-11) 완료** → 설계만 확정돼 있던 `BIN_STATES`를
  `schemas/binState.py`/`repositories/binStateRepository.py`/`services/binStateService.py`로
  구현. `GET /api/binStates`(EP-10)는 대시보드가 지금 어느 통이 가득 찼는지 보여줄 수 있게
  `binId`당 최신 상태 1행을 반환하고, `POST /api/binStates`(EP-11)는 GPU `inference`가 주기
  호출할 상태 갱신 엔드포인트로, 저장된 값과 `currentState`가 달라질 때만 전환으로 처리해
  `NORMAL`→`FULL` 순간에만 `eventService`로 overflow `EVENT`를 만든다(EP-02와 동일한
  `detectionId` 중복 방지 로직 재사용). `FULL`→`NORMAL` 복귀는 `EVENT` 없이
  `activeOverflowEventId`만 리셋 — `Docs/ERD.md`에 이미 확정돼 있던 설계 그대로 구현, 값 자체가
  달라진 건 없음. `EP-02`/`EP-09`로 직접 만드는 overflow는 여전히 상태 전환 검증 없는 수동/
  디버그 경로로 남겨둠(상세는 `Docs/API_SPEC.md`의 EP-10/EP-11, `.agentfiles/apiSpec.md` 참고)
