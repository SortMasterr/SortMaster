@echo off
REM 개발 환경 통합 설치+체크 - 더블클릭으로 실행 가능
REM 가상환경(venv)을 먼저 활성화한 상태에서 실행하는 것을 권장
REM requirements.txt 없이 checkEnv.py가 패키지 목록/설치/체크를 모두 담당

echo.
echo ============================================
echo   CCTV 분리수거 프로젝트 - 환경 설치+체크
echo ============================================
echo.

python checkEnv.py

echo.
pause
