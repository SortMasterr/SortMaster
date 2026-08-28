# SortMaster 수거 업무 자동화 RPA

`BIN_STATES`가 `NORMAL`에서 `FULL`로 전환될 때 활성 수거 작업을 한 건 생성하고,
별도 `collection-scheduler` 프로세스가 담당자 최초 알림, 재알림, 관리자 에스컬레이션을
순서대로 발송합니다. 작업과 실행 이력은 MongoDB에 저장되므로 프로세스 재시작 후에도
중복 작업이나 중복 알림을 방지합니다.

## 실행

백엔드와 MongoDB를 먼저 실행한 뒤 프로젝트 루트의 별도 터미널에서 실행합니다.

```powershell
.\WebApps\backend\.venv\Scripts\python.exe -m RPAs.collectionAutomation.collectionScheduler
```

Docker에서는 다음 서비스가 담당합니다.

```powershell
docker compose --profile local up -d --build backend mongo collection-scheduler
```

## 환경설정

```env
RPA_COLLECTION_ENABLED=true
RPA_COLLECTION_ASSIGNEE_EMAIL=worker@example.com
RPA_COLLECTION_MANAGER_EMAIL=manager@example.com
RPA_COLLECTION_INITIAL_DELAY_MINUTES=10
RPA_COLLECTION_REMINDER_MINUTES=10
RPA_COLLECTION_ESCALATION_MINUTES=20
RPA_COLLECTION_POLL_SECONDS=30
RPA_COLLECTION_RETRY_SECONDS=60
```

`RPA_COLLECTION_INITIAL_DELAY_MINUTES`는 `FULL` 감지부터 담당자 최초 이메일까지의
대기 시간입니다. 재알림과 관리자 에스컬레이션 시간은 최초 이메일이 성공적으로 발송된
시점부터 각각 계산합니다. 기본 설정은 최초 알림 10분 후, 재알림은 그로부터 10분 후,
관리자 에스컬레이션은 최초 알림으로부터 20분 후입니다.

SMTP 발신 설정은 보고서 RPA와 동일한 `RPA_REPORT_FROM`, `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`를 사용합니다. 이메일 주소와 비밀번호는
저장소에 커밋하지 않습니다.

## API 및 화면

- `GET /api/collectionTasks`: 최근 수거 작업 조회
- `POST /api/collectionTasks/{collectionTaskId}/acknowledge`: 담당자 확인 처리
- `POST /api/collectionTasks/{collectionTaskId}/complete`: 수거 완료 처리
- `GET /api/collectionAutomation/status`: 워커 상태, 처리 지표, 최근 발송 이력
- `/statistics`: 수거 작업과 실행 이력 표시 및 확인·완료 처리

공통 사이드바의 `쓰레기통 가득참` 표시는 `OPEN` 또는 `ACKNOWLEDGED` 수거 작업이 하나라도
있을 때 유지됩니다. 마지막 활성 작업을 `COMPLETED` 처리하면 즉시 숨겨지며, 다른 화면이나
브라우저에서 상태가 바뀐 경우에도 15초 주기로 동기화됩니다.

자동화는 기본적으로 비활성화되어 있습니다. `RPA_COLLECTION_ENABLED=true`로 변경한 뒤
백엔드와 `collection-scheduler`를 모두 재시작해야 새 `FULL` 전환부터 작업이 생성됩니다.
