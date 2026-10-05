"""data/input/<project_id>/ 를 읽어 ProjectInput으로 검증·로드한다."""

import json
from pathlib import Path

from contrilog.schemas import ProjectInput

from .paths import INPUT_DIRNAME, INPUT_FILES, input_dir


class InputPathError(ValueError):
    """입력 데이터 디렉터리가 아닌 곳을 읽으려 할 때 발생."""


def _resolve_input_dir(project_id: str, data_root: Path | None) -> Path:
    path = input_dir(project_id, data_root).resolve()
    # 심볼릭 링크나 '..' 을 통해 input/ 밖(예: 평가용 디렉터리)을 가리키지 못하게 한다.
    if path.parent.name != INPUT_DIRNAME or path.name != project_id:
        raise InputPathError(f"not an agent input directory: {path}")
    return path


def load_raw_input(project_id: str, data_root: Path | None = None) -> dict:
    base = _resolve_input_dir(project_id, data_root)
    raw = {}
    for key, filename in INPUT_FILES.items():
        with open(base / filename, encoding="utf-8") as f:
            raw[key] = json.load(f)
    return raw


def load_project_input(project_id: str, data_root: Path | None = None) -> ProjectInput:
    return ProjectInput.model_validate(load_raw_input(project_id, data_root))
