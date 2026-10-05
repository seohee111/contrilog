import json
from pathlib import Path

from contrilog.schemas.ground_truth import GroundTruthBundle

from .paths import GROUND_TRUTH_FILES, ground_truth_dir


def load_ground_truth(project_id: str, data_root: Path | None = None) -> GroundTruthBundle:
    base = ground_truth_dir(project_id, data_root)
    raw = {"project_id": project_id}
    for key, filename in GROUND_TRUTH_FILES.items():
        with open(base / filename, encoding="utf-8") as f:
            raw[key] = json.load(f)
    return GroundTruthBundle.model_validate(raw)
