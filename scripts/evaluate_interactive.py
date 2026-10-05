"""Interactive Verification 평가 실행: Ground Truth 시나리오별 machine-readable 결과와 집계를 출력한다.

사용법: python scripts/evaluate_interactive.py [PROJECT_ID]   (기본 P001)
"""

import json
import sys
import tempfile
from pathlib import Path

from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.interactive_evaluation import evaluate_scenarios, summarize


def main(project_id: str = "P001") -> None:
    gt = load_ground_truth(project_id)
    with tempfile.TemporaryDirectory() as tmp:
        results = evaluate_scenarios(gt.interactive_scenarios, Path(tmp), project_id=project_id)
    evaluations = [e for e, _ in results]
    print(json.dumps({"interaction_evaluations": [e.model_dump(mode="json") for e in evaluations],
                      "summary": summarize(evaluations).model_dump(mode="json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:])
