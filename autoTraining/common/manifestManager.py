"""단계 사이의 작업 장부인 JSONL manifest를 관리하는 공통 모듈입니다.

JSONL은 한 줄에 JSON 객체 하나를 저장합니다. 일반 JSON 배열보다 대용량 처리와 부분 확인이
쉽고, 프레임 하나의 기록이 다른 줄과 독립적입니다. 각 레코드는 이미지 경로, 원본 영상,
프레임 번호, 라벨과 검수 결과 등을 다음 단계로 전달합니다.
"""

import json
import os
from pathlib import Path
from typing import Any


def readManifest(manifestPath: Path) -> list[dict[str, Any]]:
    """manifest의 비어 있지 않은 줄을 모두 읽어 레코드 목록으로 반환합니다.

    파일이 아직 없다는 것은 처리할 결과가 없다는 뜻이므로 빈 목록을 반환합니다.
    줄의 JSON 형식이 잘못되면 예외를 숨기지 않아 손상된 manifest 사용을 방지합니다.
    """
    if not manifestPath.exists():
        return []
    with manifestPath.open("r", encoding="utf-8") as manifestFile:
        return [json.loads(line) for line in manifestFile if line.strip()]


def writeManifest(manifestPath: Path, rows: list[dict[str, Any]]) -> None:
    """레코드를 UTF-8 JSONL로 안전하게 저장합니다.

    목적 파일을 직접 덮어쓰지 않고 먼저 .tmp 파일을 완성합니다. 모든 행의 기록이 끝난 뒤
    os.replace로 교체하므로 실행 중단 시 기존 정상 manifest가 반쯤 작성된 파일로 바뀌는
    위험을 줄입니다. ensure_ascii=False는 한글 문자열을 사람이 읽을 수 있게 보존합니다.
    """
    manifestPath.parent.mkdir(parents=True, exist_ok=True)
    temporaryPath = manifestPath.with_suffix(manifestPath.suffix + ".tmp")
    with temporaryPath.open("w", encoding="utf-8") as manifestFile:
        for row in rows:
            manifestFile.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporaryPath, manifestPath)