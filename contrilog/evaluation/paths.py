from pathlib import Path

from contrilog.data_access.paths import DATA_ROOT

GROUND_TRUTH_DIRNAME = "ground_truth"

GROUND_TRUTH_FILES = {
    "cases": "cases.json",
    "contributions": "contributions.json",
    "claim_judgments": "claim_judgments.json",
    "stagnations": "stagnations.json",
    "interactive_scenarios": "interactive_scenarios.json",
    "reply_labels": "reply_labels.json",
}


def ground_truth_dir(project_id: str, data_root: Path | None = None) -> Path:
    return (data_root or DATA_ROOT) / GROUND_TRUTH_DIRNAME / project_id
