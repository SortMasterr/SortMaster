@README.md
@.agentfiles/architecture.md
@.agentfiles/naming.md
@.agentfiles/envSetup.md
@.agentfiles/gpuServerOps.md

## 민감정보 처리 (항상 적용, 문서/커밋 작업 시 매번 확인)

- **이 레포는 public** — push한 내용은 즉시 공개됨. GPU 서버는 팀 전용이 아니라 학원 공유
  자원이라(다른 팀도 같이 씀) 노출 시 우리 팀만의 문제가 아님
- 문서(`.md`)/커밋 메시지/코드·주석에 **실제 서버 IP, 포트+계정 조합, 비밀번호, 토큰, API 키를
  평문으로 적지 않음** — 실값은 `.env`(gitignore 대상)에만 두고, 문서에는 `<PLACEHOLDER>`로
  쓰고 "실제 값은 Notion 참고"로 안내(예: GPU 서버 IP → `<GPU_SERVER_IP>`, 로컬 배포 서버 IP →
  `<LOCAL_BACKEND_IP>`)
- 새로 문서를 쓰거나 수정할 때 실제 값을 예시로 베껴 넣고 싶어지는 경우(SSH 명령어 예시 등)
  플레이스홀더로 대체할 것 — 과거에 실제 서버 IP가 여러 커밋에 걸쳐 그대로 올라간 적 있음
  (`.agentfiles/decisionLog.md` 참고). 이 규칙을 설명할 때도 실제 값을 예시로 다시 적지 말 것
- 커밋 전 diff에 실제 값이 섞여 들어가지 않았는지 확인

아키텍처 **원본(source of truth)** 은 `Docs/ARCHITECTURE.md` 참고 (자동 로드 안 함).
자동 로드되는 `.agentfiles/architecture.md`는 **색인**이라 확정 계약과 포인터만 있음 —
경위·검증 상태·미해결 사항이 필요하면 원본을 열 것. **아키텍처 서술을 고칠 땐 원본을
고치고**, 색인은 계약 자체(카메라 대수, 클래스 종류, 포트, 판정 방향)가 바뀔 때만 손댈 것.
같은 서술을 양쪽에 중복해서 적지 말 것

API 상세 명세는 `.agentfiles/apiSpec.md`(색인) 참고, 전체 원본은 `Docs/API_SPEC.md` (API 관련 작업 시에만 열어볼 것, 자동 로드 안 함)

DB 스키마/ERD는 `Docs/ERD.md` 참고 (DB 관련 작업 시에만 열어볼 것, 자동 로드 안 함)

LLM 모델 선택·서빙 런타임(vLLM)·설정 근거는 `Docs/LLM.md` 참고 (LLM 관련 작업 시에만 열어볼 것, 자동 로드 안 함)

과거 결정 이력("왜 이렇게 정했는지")은 `.agentfiles/decisionLog.md` 참고 (이유가 궁금할 때만 열어볼 것, 자동 로드 안 함)

학습 데이터셋 클래스/구조는 `Docs/DATASET_DESCRIPTION.md` 참고 (라벨링/학습 관련 작업 시에만 열어볼 것, 자동 로드 안 함)

모델팀 초기 데이터셋 준비 스크립트(`training/` 폴더)는 `training/README.md` 참고 — 자동 재학습 파이프라인(`autoTraining/`)과 별개 (해당 작업 시에만 열어볼 것, 자동 로드 안 함)

라즈베리파이 실기기 셋업 절차/트러블슈팅은 `.agentfiles/piSetupOps.md` 참고 (라즈베리파이 관련 작업 시에만 열어볼 것, 자동 로드 안 함)
