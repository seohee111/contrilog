"""Ground Truth evidence가 Agent가 실제로 관찰할 수 있는 정보와 일치하는지."""

import json

import pytest
from pydantic import ValidationError

from contrilog.data_access import load_project_input
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.integrity import check_ground_truth_integrity
from contrilog.evaluation.paths import ground_truth_dir
from contrilog.schemas import ClaimStatus, StagnationState
from contrilog.schemas import ground_truth as G
from contrilog.simulation.loader import load_simulated_replies

GT = load_ground_truth("P001")
FULL = load_project_input("P001")
DMS = {m.message_id for m in FULL.messages if m.channel_type.value == "DIRECT_MESSAGE"}


def _all_static_expected():
    for c in GT.contributions:
        yield c.gt_contribution_id, c.expected_evidence_ids
    for j in GT.claim_judgments:
        yield j.gt_claim_id, j.expected_evidence_ids
    for s in GT.stagnations:
        yield s.gt_stagnation_id, s.expected_evidence_ids


def test_static_expected_evidence_is_agent_accessible():
    for gid, ids in _all_static_expected():
        assert not set(ids) & DMS, gid


def test_dm_references_moved_to_inaccessible_sources():
    inacc = {c.gt_contribution_id: c.inaccessible_source_ids for c in GT.contributions if c.inaccessible_source_ids}
    inacc |= {s.gt_stagnation_id: s.inaccessible_source_ids for s in GT.stagnations if s.inaccessible_source_ids}
    assert inacc == {"GTC-12": ["MSG-039", "MSG-040"], "GTS-01": ["MSG-012", "MSG-013"],
                     "GTS-03": ["MSG-038", "MSG-039", "MSG-040"]}
    assert {i for ids in inacc.values() for i in ids} <= DMS


def test_labels_unchanged_for_case03_and_case10():
    s03 = next(s for s in GT.stagnations if s.case_id == "CASE03")
    s10 = next(s for s in GT.stagnations if s.case_id == "CASE10")
    assert (s03.is_actual_block, s03.expected_final_state) == (True, StagnationState.CONFIRMED_BLOCK)
    assert s10.expected_state_sequence == [StagnationState.STAGNATION_CANDIDATE, StagnationState.CONFIRMED_BLOCK,
                                           StagnationState.RESOLVED]
    assert s10.expected_intervention.supporter_member_id == "M_B"
    gtc12 = next(c for c in GT.contributions if c.gt_contribution_id == "GTC-12")
    assert (gtc12.member_id, gtc12.contribution_type.value) == ("M_B", "SUPPORT")
    assert [j.expected_status for j in GT.claim_judgments if j.case_id == "CASE10"] == [ClaimStatus.VERIFIED]


def test_interactive_expectations_are_semantic_and_reachable():
    """기대값은 RPL/SIM ID 없이 의미로만 표현되고, 실제로 행동하면 얻을 수 있는 응답이어야 한다."""
    text = "".join((ground_truth_dir("P001") / f).read_text(encoding="utf-8")
                   for f in ["contributions.json", "stagnations.json", "claim_judgments.json"])
    assert "RPL-" not in text and "SIM-" not in text
    replies = load_simulated_replies("P001")
    trigger = {"CHECKIN_REPLY": "CHECKIN", "SUPPORT_REPLY": "SUPPORT_REQUEST"}
    expectations = [x for c in GT.contributions for x in c.expected_interactive_evidence] + \
                   [x for s in GT.stagnations for x in s.expected_interactive_evidence]
    assert len(expectations) == 7
    for x in expectations:
        about = x.about_member_id or x.responder_id
        assert any(r.trigger.value == trigger[x.kind.value] and r.task_id == x.task_id
                   and r.responder_id == x.responder_id and r.about_member_id == about for r in replies), x


def test_integrity_rejects_dm_as_expected_evidence():
    broken = GT.model_copy(deep=True)
    broken.contributions[0].expected_evidence_ids.append("MSG-039")
    broken.stagnations[0].inaccessible_source_ids.append("MSG-036")  # 공개 메시지를 접근 불가로 표시
    errors = check_ground_truth_integrity(broken, FULL)
    assert any("MSG-039" in e and "not accessible" in e for e in errors)
    assert any("MSG-036" in e and "not a private" in e for e in errors)


def test_interactive_expectation_schema_rules():
    G.InteractiveEvidenceExpectation(kind="CHECKIN_REPLY", task_id="T11", responder_id="M_C", expected_content="x")
    with pytest.raises(ValidationError):  # 지원 응답인데 지원받는 사람이 없음
        G.InteractiveEvidenceExpectation(kind="SUPPORT_REPLY", task_id="T11", responder_id="M_B", expected_content="x")
    with pytest.raises(ValidationError):  # check-in은 담당자 본인이 답한다
        G.InteractiveEvidenceExpectation(kind="CHECKIN_REPLY", task_id="T11", responder_id="M_B",
                                         about_member_id="M_C", expected_content="x")
    with pytest.raises(ValidationError):
        G.InteractiveEvidenceExpectation(kind="EMAIL_REPLY", task_id="T11", responder_id="M_C", expected_content="x")
    with pytest.raises(ValidationError):  # 같은 기록을 기대 근거이자 접근 불가로 표시
        G.GroundTruthContribution(
            gt_contribution_id="GTC-99", case_id="CASE10", project_id="P001", member_id="M_B",
            contribution_type="SUPPORT", description="x", expected_evidence_ids=["MSG-039"],
            inaccessible_source_ids=["MSG-039"])
