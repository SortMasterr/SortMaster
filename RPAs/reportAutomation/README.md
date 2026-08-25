# SortMaster 자동 통계 보고서 RPA

MongoDB에 직접 접근하지 않고 현재 구현된 `GET /api/statistics`와 `GET /api/events`만 읽어
일일·주간 HTML 이메일과 UTF-8 CSV를 생성합니다. 현재 스키마에 맞춰 쓰레기 클래스는
`normal`, `paper`, `recyclables`, `coffeeCup` 네 종류를 사용합니다.

## 실행

프로젝트 루트에서 Python 3.11로 실행합니다.

```powershell
# 전날 보고서 미리보기(이메일 미발송)
.\WebApps\backend\.venv\Scripts\python.exe -m RPAs.reportAutomation.reportAutomation daily --dry-run

# 전날 일일 보고서 발송
.\WebApps\backend\.venv\Scripts\python.exe -m RPAs.reportAutomation.reportAutomation daily

# 이전 월~일 주간 보고서 발송
.\WebApps\backend\.venv\Scripts\python.exe -m RPAs.reportAutomation.reportAutomation weekly

# 특정 날짜 재발송(weekly의 날짜는 반드시 월요일)
.\WebApps\backend\.venv\Scripts\python.exe -m RPAs.reportAutomation.reportAutomation daily --date 2026-08-24 --force
```

`--dry-run`은 `output/`에 HTML과 CSV를 생성하며 발송 이력은 남기지 않습니다. `--force`는
이미 성공한 실행 키도 다시 보내고 제목 앞에 `[재발송]`을 붙입니다.

## 대시보드에서 수신 이메일 설정

`/statistics`의 **이메일 설정** 버튼에서 자동 보고서를 받을 이메일 한 개를 저장합니다.
확인 버튼은 메일을 즉시 발송하지 않습니다. 저장 주소는
`state/recipientSettings.json`에 기록되며 이후 일일·주간 자동 발송이 공통으로 사용합니다.
새 설정은 다음 예약 시각부터 적용되며 지난 예약 작업을 즉시 소급 발송하지 않습니다.
아직 화면에서 설정하지 않은 경우에만 `.env`의 `RPA_REPORT_RECIPIENTS`를 CLI 호환 폴백으로
사용합니다. SMTP 발신 계정과 앱 비밀번호는 브라우저에 노출하지 않고 서버 `.env`에만 둡니다.

## 예약 실행

FastAPI 프로세스 내부에는 스케줄러를 두지 않습니다. Docker Compose의 별도
`report-scheduler` 서비스가 다음 작업을 실행하며, `backend`와 `report-state` 볼륨을 공유합니다.

- 매일 09:00: 전날 일일 보고서
- 매주 월요일 09:10: 이전 월~일 주간 보고서

Docker를 사용하지 않을 때는 Windows 작업 스케줄러에서 프로젝트 루트를 시작 위치로
설정하고 다음 두 작업을 등록할 수 있습니다.

- 매일 09:00: `python -m RPAs.reportAutomation.reportAutomation daily`
- 매주 월요일 09:10: `python -m RPAs.reportAutomation.reportAutomation weekly`

cron도 같은 명령을 각각 `0 9 * * *`, `10 9 * * 1`에 등록하면 됩니다. 서버 운영체제의
시간대는 `Asia/Seoul`로 맞추고, RPA 자체의 조회 기간도 `RPA_REPORT_TIMEZONE`을 사용합니다.

## 동작 및 안전장치

- KST 기간을 UTC로 변환한 뒤 두 API에 동일한 `from`/`to`를 전달합니다.
- API 합계·필드·기간·클래스별 수치를 교차 검증하고 불일치 시 메일을 보내지 않습니다.
- 일일 데이터는 검증 직후 `state/dailyReportSnapshots/YYYY-MM-DD.json`에 이벤트 메타데이터만
  저장하고 최근 7개 날짜만 유지합니다. GIF, 이미지 원본, SMTP 자격 증명은 저장하지 않습니다.
- 주간 보고서는 DB를 다시 조회하지 않고 이전 월~일의 일일 스냅샷 7개를 합산합니다. 하나라도
  없거나 검증에 실패하면 불완전한 메일을 보내지 않습니다.
- 전주 비교용으로는 원본 이벤트를 추가 보관하지 않고 주간 집계만 저장하며 최근 2개 집계만
  유지합니다. 최초 운영 주에는 이전 집계가 없어 전주 비교 표가 생략될 수 있습니다.
- API와 SMTP 일시 오류는 기본 1분, 5분, 15분 간격으로 재시도합니다.
- `state/sentReports.json`에 성공 수신자를 기록하고, 파일 잠금으로 동시 실행을 막습니다.
- 일부 수신자만 성공한 경우 다음 시도에는 아직 성공하지 않은 수신자만 보냅니다.
- 로그에 SMTP 비밀번호나 API 응답 본문을 남기지 않습니다.

실행 상태와 로그는 기본적으로 이 디렉터리 아래 `state/`에 저장됩니다. 상태 파일을 삭제하면
중복 발송 보호 이력과 주간 보고서용 일일 스냅샷이 사라지므로 운영 중에는 보존해야 합니다.
새로 배포한 뒤에는 일일 스냅샷 7개가 쌓인 다음 주간 보고서를 정상 생성할 수 있습니다.
