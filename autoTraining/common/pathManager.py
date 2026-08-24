"""설정 파일의 상대 경로와 절대 경로를 같은 방식으로 처리하는 공통 모듈입니다."""

from pathlib import Path


def resolvePath(projectRoot: Path, pathValue: str | Path) -> Path:
    """설정 경로를 실제 파일시스템 경로로 해석합니다.

    절대 경로는 사용자가 명시한 위치이므로 그대로 유지합니다. 상대 경로는 실행 명령을 내린
    현재 디렉터리가 아니라 projectRoot에 연결합니다. 덕분에 IDE, PowerShell, Docker에서
    실행 위치가 달라져도 같은 입력 데이터와 모델을 참조합니다.

    Args:
        projectRoot: 상대 경로의 기준이 되는 SortMaster 루트.
        pathValue: YAML에서 읽은 상대 또는 절대 경로.

    Returns:
        이후 파일 작업에 사용할 Path 객체.
    """
    candidatePath = Path(pathValue)
    return candidatePath if candidatePath.is_absolute() else projectRoot / candidatePath