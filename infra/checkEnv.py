"""
개발 환경 통합 스크립트 (설치 + 체크, requirements.txt 불필요).

이 파일 하나로:
1. Python 버전이 3.11인지 확인
2. 필요한 패키지 목록을 여기서 직접 정의 → 누락/버전 불일치면 자동 설치
3. Docker 설치 여부 확인
4. MongoDB 접속 확인 — .env의 MONGO_HOST/DB_PORT/DB_USER/DB_PASSWORD를 그대로
   사용하므로 팀원마다 자기 .env만 맞추면 각자 환경(로컬 Docker, 팀 공유 서버 등)에
   맞게 ping함. debug/db/testDbConnection.py와 동일한 키를 사용하며, 쓰기 도구인
   testCrud.py/seedTestEvents.py는 별도로 로컬 sortMasterTest만 허용.

실행:
    python checkEnv.py

가상환경(venv) 활성화 후 실행할 것.
새 패키지가 필요해지면 requiredPackages 목록에만 추가하면 됨 — 별도 txt 없음.
"""
import os
import subprocess
import sys
import time
from importlib import metadata

# (pip install에 쓸 문자열, importlib.metadata로 조회할 배포판 이름) 쌍.
# 팀원마다 설치 시점이 달라도 같은 버전이 깔리도록 전부 정확히 고정(==).
# 새 버전으로 올릴 땐 팀 합의 후 이 목록만 갱신하면 전원 동일하게 맞춰짐.
requiredPackages = [
    ("fastapi==0.141.1", "fastapi"),
    ("uvicorn[standard]==0.52.1", "uvicorn"),
    ("pydantic==2.13.4", "pydantic"),
    ("pydantic-settings==2.15.0", "pydantic-settings"),
    ("motor==3.7.1", "motor"),
    ("python-multipart==0.0.32", "python-multipart"),
    ("opencv-python==4.14.0.94", "opencv-python"),
    ("Pillow==11.1.0", "Pillow"),
    ("jinja2==3.1.6", "jinja2"),
    ("python-dotenv==1.2.2", "python-dotenv"),
]

requiredPython = (3, 11)
mongodbTimeoutMs = 5000  # Windows Docker Desktop(WSL2)은 첫 연결이 느릴 수 있어 여유있게
mongodbRetries = 2


def checkPythonVersion() -> bool:
    current = sys.version_info[:2]
    ok = current == requiredPython
    status = "OK " if ok else "FAIL"
    print(f"[{status}] Python {sys.version.split()[0]} (요구: {requiredPython[0]}.{requiredPython[1]}.x)")
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
    for installSpec, checkName in requiredPackages:
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
    """Docker 설치 + Compose V2(`docker compose`, 하이픈 없는 플러그인) 지원 여부 확인.
    docker-compose.yml이 profiles/GPU deploy.resources 문법을 쓰기 때문에 Compose V2 필수 —
    구버전 standalone docker-compose(V1)는 미지원. 정확한 버전을 고정하진 않되(팀원마다
    설치 시점 다름), v29.6.2/Compose v5.3.1 조합으로 실제 빌드+구동 검증 완료."""
    try:
        result = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            print("[FAIL] docker --version 실행 실패")
            return False
        print(f"[OK ] {result.stdout.strip()}")

        composeResult = subprocess.run(
            ["docker", "compose", "version"], capture_output=True, text=True, timeout=5
        )
        if composeResult.returncode != 0:
            print("[FAIL] Docker Compose V2 미지원 - docker-compose.yml의 profiles/GPU 문법에 필요(V1 docker-compose로는 안 됨)")
            return False
        print(f"[OK ] {composeResult.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("[FAIL] Docker가 설치되어 있지 않거나 PATH에 없음")
        return False
    except Exception as e:
        print(f"[FAIL] Docker 확인 중 오류: {e}")
        return False


def checkMongodb() -> bool:
    """MongoDB 접속 가능 여부 확인.
    .env의 MONGO_HOST/DB_PORT/DB_USER/DB_PASSWORD를 그대로 사용 —
    debug/db/testDbConnection.py와 동일한 대상을 ping한다. 쓰기 도구인
    debug/db/testCrud.py/seedTestEvents.py는 공유 DB 오작동을 막기 위해 별도로
    loopback+sortMasterTest만 허용한다.
    Windows Docker Desktop은 첫 연결이 느릴 수 있어 재시도 포함."""
    try:
        import asyncio
        from urllib.parse import quote_plus

        from dotenv import load_dotenv
        from motor.motor_asyncio import AsyncIOMotorClient

        load_dotenv()

        mongoHost = os.getenv("MONGO_HOST", "localhost")
        mongoPort = os.getenv("DB_PORT", "27020")
        mongoUser = os.getenv("DB_USER")
        mongoPassword = os.getenv("DB_PASSWORD")
        mongoDbName = os.getenv("DB_NAME", "sortMaster")

        if mongoUser and mongoPassword:
            auth = f"{quote_plus(mongoUser)}:{quote_plus(mongoPassword)}@"
        else:
            auth = ""

        # authSource를 명시 안 하면 드라이버가 admin DB를 인증 기준으로 삼음 —
        # 계정을 DB_NAME(예: sortMaster)에 스코프해서 만들었으면 인증 실패남.
        mongoUri = (
            f"mongodb://{auth}{mongoHost}:{mongoPort}/"
            f"?appName=sortMasterDB&authSource={mongoDbName}"
        )
        target = f"{mongoHost}:{mongoPort}"

        async def _ping():
            client = AsyncIOMotorClient(
                mongoUri, serverSelectionTimeoutMS=mongodbTimeoutMs
            )
            await client.admin.command("ping")
            client.close()

        lastError = None
        for attempt in range(1, mongodbRetries + 1):
            try:
                asyncio.run(_ping())
                print(f"[OK ] MongoDB 접속 성공 ({target})")
                return True
            except Exception as e:
                lastError = e
                if attempt < mongodbRetries:
                    print(f"      접속 시도 {attempt}/{mongodbRetries} 실패, 재시도 중...")
                    time.sleep(1.5)

        print(f"[FAIL] MongoDB 접속 실패 ({target}) - .env의 MONGO_HOST/DB_PORT 확인: {lastError}")
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
