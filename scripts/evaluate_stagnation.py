"""Stagnation Agent 평가: 프로젝트 전체 연속 모니터링 → Ground Truth 정체 항목별 채점(JSON) + 집계.

사용법: python scripts/evaluate_stagnation.py [PROJECT_ID]   (기본 P001)
"""

import json
import sys

from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.stagnation_evaluation import evaluate_all, run_monitoring, summarize, unlabeled_candidates


def main(project_id: str = "P001") -> None:
    gt = load_ground_truth(project_id)
    _, agent, _ = run_monitoring(project_id=project_id)
    runs = agent.runs()
    evals = evaluate_all(gt, runs)
    unlabeled = unlabeled_candidates(runs, gt)
    print(json.dumps({"stagnation_evaluations": [e.model_dump(mode="json") for e in evals],
                      "unlabeled_candidates": unlabeled,
                      "summary": summarize(evals, len(unlabeled)).model_dump(mode="json")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:])
