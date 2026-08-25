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

## 대시보드에서 수동 발송

`/statistics`의 **이메일 발송** 버튼을 누르면 수신 이메일, 보고서 종류, 기준일을 입력해
바로 발송할 수 있습니다. 이 경로에서는 수신 이메일을 요청 Body로 전달하므로
`RPA_REPORT_RECIPIENTS`가 없어도 됩니다. 다만 SMTP 발신 계정과 비밀번호를 브라우저에
노출하면 안 되므로 `RPA_REPORT_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_USE_TLS`는 백엔드 서버 환경 설정에 있어야 합니다.

예약 실행 CLI는 화면 입력이 없으므로 기존처럼 `RPA_REPORT_RECIPIENTS`와
`RPA_REPORT_RECIPIENT_GROUP`을 사용합니다.

## 예약 실행

프로그램 내부에 스케줄러를 두지 않습니다. Windows 작업 스케줄러에서 프로젝트 루트를
시작 위치로 설정하고 다음 두 작업을 등록합니다.

- 매일 09:00: `python -m RPAs.reportAutomation.reportAutomation daily`
- 매주 월요일 09:10: `python -m RPAs.reportAutomation.reportAutomation weekly`

cron도 같은 명령을 각각 `0 9 * * *`, `10 9 * * 1`에 등록하면 됩니다. 서버 운영체제의
시간대는 `Asia/Seoul`로 맞추고, RPA 자체의 조회 기간도 `RPA_REPORT_TIMEZONE`을 사용합니다.

## 동작 및 안전장치

- KST 기간을 UTC로 변환한 뒤 두 API에 동일한 `from`/`to`를 전달합니다.
- API 합계·필드·기간·클래스별 수치를 교차 검증하고 불일치 시 메일을 보내지 않습니다.
- 주간 보고서는 직전 주 데이터도 조회해 전체/카테고리/클래스/수거함 증감을 표시합니다.
- API와 SMTP 일시 오류는 기본 1분, 5분, 15분 간격으로 재시도합니다.
- `state/sentReports.json`에 성공 수신자를 기록하고, 파일 잠금으로 동시 실행을 막습니다.
- 일부 수신자만 성공한 경우 다음 시도에는 아직 성공하지 않은 수신자만 보냅니다.
- 로그에 SMTP 비밀번호나 API 응답 본문을 남기지 않습니다.

실행 상태와 로그는 기본적으로 이 디렉터리 아래 `state/`에 저장됩니다. 상태 파일을 삭제하면
중복 발송 보호 이력이 사라지므로 운영 중에는 보존해야 합니다.
