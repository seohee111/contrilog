"""Memory OFF / CONTEXT_ONLY / MEMORY_ONLY / ON (+ 약한 UNRESOLVED 변형) 전체 재생 비교.

사용법: python scripts/compare_memory.py [PROJECT_ID]   (기본 P001)
"""

import json
import sys

from contrilog.data_access import load_project_input
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.memory_evaluation import CAVEAT, MODES, memory_checks, mode_metrics, run_mode


def main(project_id: str = "P001") -> None:
    gt = load_ground_truth(project_id)
    members = load_project_input(project_id).members
    results, agents = {}, {}
    for mode in MODES:
        _, agent, store = run_mode(mode, project_id=project_id)
        results[mode] = mode_metrics(mode, agent, store, gt)
        agents[mode] = (agent, store)
    agent, store = agents["ON"]
    checks = memory_checks(agent, store, gt, members, results["OFF"], results["ON"])
    print(json.dumps({"modes": {k: v.model_dump(mode="json") for k, v in results.items()},
                      "memory_checks_on": checks.model_dump(mode="json"),
                      "memories_on": [m.model_dump(mode="json") for m in store.all()],
                      "caveat": CAVEAT}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:])
