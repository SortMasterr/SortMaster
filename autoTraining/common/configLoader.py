"""파이프라인 YAML 설정을 읽고 기본 구조를 검증하는 공통 모듈입니다.

설정 로딩을 별도 함수로 분리하면 메인 파이프라인, 테스트 코드, 관리 도구가 같은 방식으로
설정을 읽을 수 있습니다. 이 함수는 값의 세부 의미까지 검사하지 않고 YAML 최상위 구조가
키와 값으로 이루어진 mapping인지 먼저 확인합니다.
"""

from pathlib import Path
from typing import Any

import yaml


def loadConfig(configPath: Path) -> dict[str, Any]:
    """UTF-8 YAML 설정 파일을 Python 사전으로 반환합니다.

    Args:
        configPath: 읽을 pipelineConfig.yaml의 경로.

    Returns:
        paths, frames, inference 등의 설정 그룹을 담은 사전.

    Raises:
        FileNotFoundError: 설정 파일이 존재하지 않을 때.
        yaml.YAMLError: YAML 문법이 올바르지 않을 때.
        ValueError: 최상위 값이 mapping이 아닐 때.
    """
    with configPath.open("r", encoding="utf-8") as configFile:
        config = yaml.safe_load(configFile)
    if not isinstance(config, dict):
        raise ValueError("Pipeline configuration must be a mapping.")
    return config