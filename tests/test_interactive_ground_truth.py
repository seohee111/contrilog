"""interactive Ground Truth 기대값을 '평가 계층에서만' 사용해 Agent 행동을 채점한다."""

import pytest

from contrilog.evaluation.claim_comparison import compare_interactions
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.schemas import ClaimStatus as CS
from tests.interactive_fixtures import SCENARIOS, run_scenario

GT = load_ground_truth("P001")


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    return {n: run_scenario(tmp_path_factory.mktemp(n), s)[2] for n, s in SCENARIOS.items()}


@pytest.mark.parametrize("owner,scenarios", [
    ("GTS-01", ["github_blocked"]),                          # Case03
    ("GTS-02", ["dataset_local"]),                           # Case04
    ("GTS-03", ["claim_api_blocked", "claim_api_fixed"]),   # Case10 정체 흐름의 담당자 응답
    ("GTC-12", ["support_via_dm"]),                          # Case10 B 지원
])
def test_expected_checkin_replies_are_obtained_and_used(runs, owner, scenarios):
    results = compare_interactions([runs[n] for n in scenarios], GT, owner_ids={owner})
    checkins = [r for r in results if r.kind == "CHECKIN_REPLY"]
    assert checkins and all(r.satisfied for r in checkins), results
    for r in results:
        if r.kind == "SUPPORT_REPLY":  # 지원 요청은 사람 승인이 필요한 별도 행동 — Claim 검증 Agent 범위 밖
            assert not r.satisfied and "범위 밖" in r.note


def test_case10_support_label_reached_through_interaction(runs):
    gtc = next(c for c in GT.contributions if c.gt_contribution_id == "GTC-12")
    run = runs["support_via_dm"]
    r = run.atomic_results[0]
    assert (run.claimant_id, r.predicted_contribution_type, r.predicted_status) == (gtc.member_id, gtc.contribution_type,
                                                                                      CS.VERIFIED)
    assert set(gtc.expected_evidence_ids) <= set(r.supporting_source_ids)  # 공개 근거 REV-058
    assert not set(gtc.inaccessible_source_ids) & {e.source_id for e in run.evidence}


def test_reply_content_matches_expected_meaning(runs):
    """기대값의 의미(막힘/진행 중/해결)와 응답 근거의 역할이 맞는지 확인한다."""
    roles = {n: {e.note.split(":")[0] for e in runs[n].evidence if e.source_type.value == "INBOUND_REPLY"}
             for n in SCENARIOS}
    assert roles["github_blocked"] == {"incomplete_report"}      # 403·승인 대기
    assert roles["dataset_local"] == {"incomplete_report"}       # 로컬 작업 중
    assert roles["claim_api_blocked"] == {"incomplete_report"}   # 0건으로 막힘
    assert roles["claim_api_fixed"] == {"completion"}            # 해결
    assert roles["support_via_dm"] == {"counterpart_confirmation"}
