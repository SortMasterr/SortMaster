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
RPA_COLLECTION_REMINDER_MINUTES=10
RPA_COLLECTION_ESCALATION_MINUTES=20
RPA_COLLECTION_POLL_SECONDS=30
RPA_COLLECTION_RETRY_SECONDS=60
```

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

## 쓰레기통 위치 기반 모드 자동 전환

SIDE 카메라에서 현재 설치된 쓰레기통 3개의 위치를 확인해 수거 작업을 시작한 것으로 판단하면
자동으로 `COLLECT` 모드로 전환합니다. 세 통이 모두 원위치에 돌아와 설정 시간 동안 안정적으로
보이면 `MANAGE` 모드로 복귀합니다. 카메라 장애나 프레임 수신 실패 시에는 오작동을 피하기 위해
현재 모드를 그대로 유지합니다.

각 통의 카메라를 향한 면에 ArUco 마커 0, 1, 2를 하나씩 부착합니다. 마커 이미지는 프로젝트
루트에서 다음 명령으로 생성할 수 있습니다.

```powershell
.\WebApps\backend\.venv\Scripts\python.exe debug\detection\generateBinMarkers.py
```

마커 이미지의 흰 테두리를 자르지 말고 충분히 크게 인쇄해야 합니다. 세 통을 정상 위치에 둔 뒤
백엔드를 재시작하고 원위치를 최초 1회 등록합니다.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8047/api/binPositionMonitor/calibrate
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8047/api/binPositionMonitor/status
```

```env
RPA_BIN_POSITION_ENABLED=true
RPA_BIN_MARKER_IDS=0,1,2
RPA_BIN_POSITION_TOLERANCE_RATIO=0.06
RPA_BIN_AWAY_CONFIRM_SECONDS=3
RPA_BIN_RETURN_CONFIRM_SECONDS=5
RPA_BIN_POSITION_POLL_SECONDS=0.5
```

사람이 화면의 모드 버튼을 누르면 수동 선택이 우선합니다. 특히 자동 수거 모드가 된 뒤 사람이
다시 모드를 선택한 경우, RPA는 그 선택을 덮어쓰지 않으며 세 통이 원위치에 돌아온 뒤 다음 이동부터
자동 감지를 다시 시작합니다. 환경변수와 원위치 파일은 백엔드 시작 시 읽으므로 설정 변경이나
재등록 파일 교체 후에는 백엔드를 재시작해야 합니다.
