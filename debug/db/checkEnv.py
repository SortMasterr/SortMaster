"""
개발 환경 통합 스크립트 (설치 + 체크, requirements.txt 불필요).

이 파일 하나로:
1. Python 버전이 3.11인지 확인
2. 필요한 패키지 목록을 여기서 직접 정의 → 누락/버전 불일치면 자동 설치
3. Docker 설치 여부 확인
4. MongoDB 접속 확인 — .env의 MONGO_HOST/MONGO_PORT를 그대로 사용하므로
   팀원마다 자기 .env만 맞추면 각자 환경(로컬 Docker, 팀 공유 서버 등)에
   맞게 체크됨. debug/testDbConnection.py, debug/testCrud.py와 동일한
   .env 키를 공유.

실행:
    python check_env.py

가상환경(venv) 활성화 후 실행할 것.
새 패키지가 필요해지면 REQUIRED_PACKAGES 목록에만 추가하면 됨 — 별도 txt 없음.
"""
import os
import subprocess
import sys
import time
from importlib import metadata

# (pip install에 쓸 문자열, importlib.metadata로 조회할 배포판 이름) 쌍.
REQUIRED_PACKAGES = [
    ("fastapi>=0.115", "fastapi"),
    ("uvicorn[standard]>=0.30", "uvicorn"),
    ("pydantic>=2.7", "pydantic"),
    ("pydantic-settings>=2.3", "pydantic-settings"),
    ("motor>=3.5", "motor"),
    ("python-multipart>=0.0.9", "python-multipart"),
    ("opencv-python>=4.9", "opencv-python"),
    ("jinja2>=3.1", "jinja2"),
    ("python-dotenv>=1.0", "python-dotenv"),
]

REQUIRED_PYTHON = (3, 11)
MONGODB_TIMEOUT_MS = 5000  # Windows Docker Desktop(WSL2)은 첫 연결이 느릴 수 있어 여유있게
MONGODB_RETRIES = 2


def checkPythonVersion() -> bool:
    current = sys.version_info[:2]
    ok = current == REQUIRED_PYTHON
    status = "OK " if ok else "FAIL"
    print(f"[{status}] Python {sys.version.split()[0]} (요구: {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}.x)")
    return ok


def _isSatisfied(installSpec: str, installedVersion: str) -> bool:
    try:
        from packaging.requirements import Requirement
        from packaging.version import Version

        req = Requirement(installSpec)
        return Version(installedVersion) in req.specifier if req.specifier else True
    except Exception:
        return True


def _pipInstall(installSpec: str) -> bool:
    print(f"      → 설치 시도: pip install {installSpec}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", installSpec],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"      설치 실패:\n{result.stderr.strip()}")
        return False
    return True


def checkAndInstallPackages() -> bool:
    allOk = True
    for installSpec, checkName in REQUIRED_PACKAGES:
        try:
            installedVersion = metadata.version(checkName)
            satisfied = _isSatisfied(installSpec, installedVersion)
        except metadata.PackageNotFoundError:
            installedVersion = None
            satisfied = False

        if satisfied:
            print(f"[OK ] {checkName} {installedVersion} (요구: {installSpec})")
            continue

        if installedVersion is None:
            print(f"[--- ] {checkName} 미설치 (요구: {installSpec})")
        else:
            print(f"[--- ] {checkName} {installedVersion} (요구: {installSpec}, 버전 불일치)")

        if _pipInstall(installSpec):
            try:
                installedVersion = metadata.version(checkName)
                satisfied = _isSatisfied(installSpec, installedVersion)
            except metadata.PackageNotFoundError:
                satisfied = False

        status = "OK " if satisfied else "FAIL"
        print(f"[{status}] {checkName} {installedVersion} (요구: {installSpec})")
        allOk = allOk and satisfied

    return allOk


def checkDocker() -> bool:
    """Docker/Compose 버전은 팀 TBD라 설치 여부만 확인, 버전은 참고용으로 출력."""
    try:
        result = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            print(f"[OK ] {result.stdout.strip()} (버전 고정값 TBD - 설치 여부만 확인)")
            return True
        print("[FAIL] docker --version 실행 실패")
        return False
    except FileNotFoundError:
        print("[FAIL] Docker가 설치되어 있지 않거나 PATH에 없음")
        return False
    except Exception as e:
        print(f"[FAIL] Docker 확인 중 오류: {e}")
        return False


def checkMongodb() -> bool:
    """MongoDB 접속 가능 여부 확인.
    .env의 MONGO_HOST/MONGO_PORT/MONGO_USER/MONGO_PASSWORD를 그대로 사용 —
    debug/testDbConnection.py, debug/testCrud.py와 동일한 대상을 테스트해서
    "스크립트마다 접속 대상이 다른" 혼선을 방지한다. 팀원마다 자기 .env의
    MONGO_HOST만 바꾸면 각자 환경에 맞게 체크됨.
    Windows Docker Desktop은 첫 연결이 느릴 수 있어 재시도 포함."""
    try:
        import asyncio
        from urllib.parse import quote_plus

        from dotenv import load_dotenv
        from motor.motor_asyncio import AsyncIOMotorClient

        load_dotenv()

        mongoHost = os.getenv("MONGO_HOST", "localhost")
        mongoPort = os.getenv("MONGO_PORT", "27020")
        mongoUser = os.getenv("MONGO_USER")
        mongoPassword = os.getenv("MONGO_PASSWORD")

        if mongoUser and mongoPassword:
            auth = f"{quote_plus(mongoUser)}:{quote_plus(mongoPassword)}@"
        else:
            auth = ""

        mongoUri = f"mongodb://{auth}{mongoHost}:{mongoPort}/?appName=sortMasterDB"
        target = f"{mongoHost}:{mongoPort}"

        async def _ping():
            client = AsyncIOMotorClient(
                mongoUri, serverSelectionTimeoutMS=MONGODB_TIMEOUT_MS
            )
            await client.admin.command("ping")
            client.close()

        lastError = None
        for attempt in range(1, MONGODB_RETRIES + 1):
            try:
                asyncio.run(_ping())
                print(f"[OK ] MongoDB 접속 성공 ({target})")
                return True
            except Exception as e:
                lastError = e
                if attempt < MONGODB_RETRIES:
                    print(f"      접속 시도 {attempt}/{MONGODB_RETRIES} 실패, 재시도 중...")
                    time.sleep(1.5)

        print(f"[FAIL] MongoDB 접속 실패 ({target}) - .env의 MONGO_HOST/MONGO_PORT 확인: {lastError}")
        return False
    except ImportError as e:
        print(f"[FAIL] 필요한 패키지 미설치({e}) - 위 패키지 설치 단계를 먼저 확인하세요")
        return False


def main():
    print("=== 1. Python 버전 체크 ===")
    pythonOk = checkPythonVersion()

    print()
    print("=== 2. 패키지 설치 + 체크 (requirements.txt 없이 이 스크립트가 목록 관리) ===")
    packagesOk = checkAndInstallPackages()

    print()
    print("=== 3. Docker 체크 ===")
    dockerOk = checkDocker()

    print()
    print("=== 4. MongoDB 접속 체크 (포트 27020) ===")
    mongodbOk = checkMongodb()

    print()
    if pythonOk and packagesOk and dockerOk and mongodbOk:
        print("모든 항목 통과. 환경 세팅 완료.")
        sys.exit(0)
    else:
        print("일부 항목 실패. 위 로그에서 FAIL 항목을 확인하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
