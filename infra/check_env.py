"""
개발 환경 통합 스크립트 (설치 + 체크, requirements.txt 불필요).

이 파일 하나로:
1. Python 버전이 3.11인지 확인
2. 필요한 패키지 목록을 여기서 직접 정의 → 누락/버전 불일치면 자동 설치
3. Docker 설치 여부 확인
4. MongoDB(Docker, 호스트 포트 27020) 접속 확인

실행:
    python check_env.py

가상환경(venv) 활성화 후 실행할 것.
새 패키지가 필요해지면 REQUIRED_PACKAGES 목록에만 추가하면 됨 — 별도 txt 없음.
"""
import subprocess
import sys
from importlib import metadata

# (pip install에 쓸 문자열, importlib.metadata로 조회할 배포판 이름) 쌍.
# extras([standard] 등)가 붙는 패키지는 설치용 문자열과 조회용 이름이 다르므로 분리.
REQUIRED_PACKAGES = [
    ("fastapi>=0.115", "fastapi"),
    ("uvicorn[standard]>=0.30", "uvicorn"),
    ("pydantic>=2.7", "pydantic"),
    ("pydantic-settings>=2.3", "pydantic-settings"),
    ("motor>=3.5", "motor"),
    ("python-multipart>=0.0.9", "python-multipart"),
    ("opencv-python>=4.9", "opencv-python"),
    ("jinja2>=3.1", "jinja2"),
]

REQUIRED_PYTHON = (3, 11)
MONGODB_URI = "mongodb://localhost:27020"


def check_python_version() -> bool:
    current = sys.version_info[:2]
    ok = current == REQUIRED_PYTHON
    status = "OK " if ok else "FAIL"
    print(f"[{status}] Python {sys.version.split()[0]} (요구: {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}.x)")
    return ok


def _is_satisfied(install_spec: str, installed_version: str) -> bool:
    try:
        from packaging.requirements import Requirement
        from packaging.version import Version

        req = Requirement(install_spec)
        return Version(installed_version) in req.specifier if req.specifier else True
    except Exception:
        return True  # packaging 미설치/파싱 실패 시 설치 여부만으로 통과 처리


def _pip_install(install_spec: str) -> bool:
    print(f"      → 설치 시도: pip install {install_spec}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", install_spec],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"      설치 실패:\n{result.stderr.strip()}")
        return False
    return True


def check_and_install_packages() -> bool:
    all_ok = True
    for install_spec, check_name in REQUIRED_PACKAGES:
        try:
            installed_version = metadata.version(check_name)
            satisfied = _is_satisfied(install_spec, installed_version)
        except metadata.PackageNotFoundError:
            installed_version = None
            satisfied = False

        if satisfied:
            print(f"[OK ] {check_name} {installed_version} (요구: {install_spec})")
            continue

        if installed_version is None:
            print(f"[--- ] {check_name} 미설치 (요구: {install_spec})")
        else:
            print(f"[--- ] {check_name} {installed_version} (요구: {install_spec}, 버전 불일치)")

        if _pip_install(install_spec):
            try:
                installed_version = metadata.version(check_name)
                satisfied = _is_satisfied(install_spec, installed_version)
            except metadata.PackageNotFoundError:
                satisfied = False

        status = "OK " if satisfied else "FAIL"
        print(f"[{status}] {check_name} {installed_version} (요구: {install_spec})")
        all_ok = all_ok and satisfied

    return all_ok


def check_docker() -> bool:
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


def check_mongodb() -> bool:
    """MongoDB(Docker, 호스트 포트 27020) 접속 가능 여부만 확인."""
    try:
        import asyncio

        from motor.motor_asyncio import AsyncIOMotorClient

        async def _ping():
            client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
            await client.admin.command("ping")
            client.close()

        asyncio.run(_ping())
        print(f"[OK ] MongoDB 접속 성공 ({MONGODB_URI})")
        return True
    except ImportError:
        print("[FAIL] motor 미설치 - 위 패키지 설치 단계를 먼저 확인하세요")
        return False
    except Exception as e:
        print(f"[FAIL] MongoDB 접속 실패 ({MONGODB_URI}) - 컨테이너가 떠 있는지 확인: {e}")
        return False


def main():
    print("=== 1. Python 버전 체크 ===")
    python_ok = check_python_version()

    print()
    print("=== 2. 패키지 설치 + 체크 (requirements.txt 없이 이 스크립트가 목록 관리) ===")
    packages_ok = check_and_install_packages()

    print()
    print("=== 3. Docker 체크 ===")
    docker_ok = check_docker()

    print()
    print("=== 4. MongoDB 접속 체크 (포트 27020) ===")
    mongodb_ok = check_mongodb()

    print()
    if python_ok and packages_ok and docker_ok and mongodb_ok:
        print("모든 항목 통과. 환경 세팅 완료.")
        sys.exit(0)
    else:
        print("일부 항목 실패. 위 로그에서 FAIL 항목을 확인하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
