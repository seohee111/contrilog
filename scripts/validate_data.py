"""데이터 계층 전체 검증: schema → 입력 참조 무결성 → 시뮬레이션 → Ground Truth.

사용법: python scripts/validate_data.py [PROJECT_ID]
"""

import sys
from collections import Counter

from contrilog.data_access import load_project_input
from contrilog.data_access.integrity import check_input_integrity
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.integrity import check_ground_truth_integrity
from contrilog.simulation.loader import (
    check_human_decision_integrity,
    check_simulation_integrity,
    load_human_decisions,
    load_simulated_replies,
)


def main(project_id: str = "P001") -> int:
    data = load_project_input(project_id)
    print(f"[input] {project_id}: members={len(data.members)} meetings={len(data.meetings)} "
          f"utterances={len(data.utterances)} revisions={len(data.document_history)} "
          f"tasks={len(data.tasks)} messages={len(data.messages)} claims={len(data.claims)}")
    replies = load_simulated_replies(project_id)
    decisions = load_human_decisions(project_id)
    print(f"[simulation] replies={len(replies)} human_decisions={len(decisions)}")
    gt = load_ground_truth(project_id)
    print(f"[ground_truth] cases={len(gt.cases)} contributions={len(gt.contributions)} "
          f"claim_judgments={len(gt.claim_judgments)} stagnations={len(gt.stagnations)} "
          f"interactive_scenarios={len(gt.interactive_scenarios)} reply_labels={len(gt.reply_labels)}")
    print("  contribution types:", dict(Counter(c.contribution_type.value for c in gt.contributions)))
    print("  claim statuses:", dict(Counter(j.expected_status.value for j in gt.claim_judgments)))

    errors = (
        [f"input: {e}" for e in check_input_integrity(data)]
        + [f"simulation: {e}" for e in check_simulation_integrity(replies, data)]
        + [f"simulation: {e}" for e in check_human_decision_integrity(decisions, data)]
        + [f"ground_truth: {e}" for e in check_ground_truth_integrity(gt, data, replies)]
    )
    for e in errors:
        print("ERROR", e)
    print("OK: schema + referential integrity passed" if not errors else f"FAILED: {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
