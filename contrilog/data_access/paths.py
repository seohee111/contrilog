"""Agent 입력 데이터 경로. 평가용 정답 데이터 경로는 이 모듈에 두지 않는다."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"
INPUT_DIRNAME = "input"

INPUT_FILES = {
    "project": "project.json",
    "members": "members.json",
    "meetings": "meetings.json",
    "utterances": "meeting_utterances.json",
    "document_history": "document_history.json",
    "tasks": "tasks.json",
    "messages": "messages.json",
    "claims": "contribution_claims.json",
}


def input_dir(project_id: str, data_root: Path | None = None) -> Path:
    return (data_root or DATA_ROOT) / INPUT_DIRNAME / project_id
