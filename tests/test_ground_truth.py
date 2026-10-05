"""Ground Truth가 실제 입력 객체를 가리키는지, 10개 Case 기대값과 일치하는지 검사."""

from contrilog.evaluation.integrity import check_ground_truth_integrity
from contrilog.schemas import ClaimStatus as CS
from contrilog.schemas import ContributionType as CT
from contrilog.schemas import StagnationState as SS


def test_ground_truth_integrity(ground_truth, project_input):
    assert check_ground_truth_integrity(ground_truth, project_input) == []


def test_all_expected_evidence_ids_exist(ground_truth, project_input):
    sources = project_input.source_record_ids()
    items = [*ground_truth.contributions, *ground_truth.claim_judgments, *ground_truth.stagnations]
    for item in items:
        missing = set(item.expected_evidence_ids) - sources
        assert not missing, f"{item}: {missing}"


def test_integrity_checker_detects_missing_evidence(ground_truth, project_input):
    broken = ground_truth.model_copy(deep=True)
    broken.contributions[0].expected_evidence_ids.append("REV-999")
    broken.stagnations[0].task_id = "T99"
    errors = check_ground_truth_integrity(broken, project_input)
    assert any("REV-999" in e for e in errors)
    assert any("T99" in e for e in errors)


def test_ten_cases(ground_truth):
    assert [c.case_id for c in ground_truth.cases] == [f"CASE{i:02d}" for i in range(1, 11)]


# ---- Case별 기대값 ---------------------------------------------------------

def _label(project_input):
    return {m.label: m.member_id for m in project_input.members}


def _contribs(gt, case_id):
    return {(c.member_id, c.contribution_type) for c in gt.contributions if c.case_id == case_id}


def _judgments(gt, case_id):
    return {(j.claimant_id, j.claimed_type, j.expected_status) for j in gt.claim_judgments if j.case_id == case_id}


def _stagnation(gt, case_id):
    (s,) = [s for s in gt.stagnations if s.case_id == case_id]
    return s


def test_case01(ground_truth, project_input):
    L = _label(project_input)
    assert _contribs(ground_truth, "CASE01") == {(L["A"], CT.IDEA)}
    assert _judgments(ground_truth, "CASE01") == {(L["A"], CT.IDEA, CS.VERIFIED)}


def test_case02(ground_truth, project_input):
    L = _label(project_input)
    assert _judgments(ground_truth, "CASE02") == {(L["B"], CT.IDEA, CS.INSUFFICIENT_EVIDENCE)}
    assert _contribs(ground_truth, "CASE02") == {(L["D"], CT.IDEA)}  # 최초 제안자는 D


def test_case03(ground_truth, project_input):
    s = _stagnation(ground_truth, "CASE03")
    assert s.member_id == _label(project_input)["C"]
    assert s.is_actual_block and s.block_started_at is not None
    assert s.expected_final_state == SS.CONFIRMED_BLOCK


def test_case04_false_positive(ground_truth, project_input):
    s = _stagnation(ground_truth, "CASE04")
    assert s.member_id == _label(project_input)["D"]
    assert not s.is_actual_block and s.block_started_at is None
    assert s.expected_final_state == SS.NORMAL
    assert SS.CONFIRMED_BLOCK in s.forbidden_states


def test_case05(ground_truth, project_input):
    L = _label(project_input)
    assert _contribs(ground_truth, "CASE05") == {(L["A"], CT.REVIEW)}
    assert _judgments(ground_truth, "CASE05") == {(L["A"], CT.REVIEW, CS.VERIFIED)}


def test_case05_small_change_volume(ground_truth, project_input):
    """A의 REVIEW 근거 리비전은 변경량이 작다 — 변경량과 기여 판단이 무관함을 보여주는 데이터인지 확인."""
    revs = {r.revision_id: r for r in project_input.document_history}
    (c,) = [c for c in ground_truth.contributions if c.case_id == "CASE05"]
    a_revs = [revs[e] for e in c.expected_evidence_ids if e in revs and revs[e].author_id == c.member_id]
    assert a_revs and all(r.chars_added + r.chars_deleted < 1000 for r in a_revs)


def test_case06(ground_truth, project_input):
    L = _label(project_input)
    assert _contribs(ground_truth, "CASE06") == {(L["B"], CT.EXECUTION)}
    assert _judgments(ground_truth, "CASE06") == {(L["B"], CT.EXECUTION, CS.VERIFIED)}
    # B의 중간보고서 수정량이 다른 팀원보다 많은 상황을 실제로 담고 있는지 확인
    volume = {}
    for r in project_input.document_history:
        if r.document_id == "DOC-MIDREPORT":
            volume[r.author_id] = volume.get(r.author_id, 0) + r.chars_added + r.chars_deleted
    assert max(volume, key=volume.get) == L["B"]


def test_case07(ground_truth, project_input):
    L = _label(project_input)
    assert _contribs(ground_truth, "CASE07") == {(L["C"], CT.EXECUTION), (L["B"], CT.SUPPORT)}


def test_case08_atomic_split(ground_truth, project_input):
    L = _label(project_input)
    assert _contribs(ground_truth, "CASE08") == {(L["D"], CT.IDEA), (L["A"], CT.EXECUTION)}
    assert _judgments(ground_truth, "CASE08") == {
        (L["A"], CT.IDEA, CS.CONFLICTING_EVIDENCE),
        (L["A"], CT.EXECUTION, CS.VERIFIED),
    }
    claim_ids = {j.claim_id for j in ground_truth.claim_judgments if j.case_id == "CASE08"}
    assert len(claim_ids) == 1, "두 atomic claim은 같은 원본 Claim에서 나와야 한다"


def test_case09(ground_truth, project_input):
    L = _label(project_input)
    assert _contribs(ground_truth, "CASE09") == {(L["B"], CT.COORDINATION)}
    assert _judgments(ground_truth, "CASE09") == {(L["B"], CT.COORDINATION, CS.VERIFIED)}


def test_case10_flow(ground_truth, project_input):
    L = _label(project_input)
    s = _stagnation(ground_truth, "CASE10")
    assert s.member_id == L["C"]
    assert s.expected_state_sequence == [SS.STAGNATION_CANDIDATE, SS.CONFIRMED_BLOCK, SS.RESOLVED]
    assert s.expected_intervention.supporter_member_id == L["B"]
    assert s.block_started_at < s.resolved_at <= s.evaluation_as_of
    task = next(t for t in project_input.tasks if t.task_id == s.task_id)
    assert s.evaluation_as_of.date() >= task.due_date  # 마감 직전 상황


def test_stagnation_tasks_have_no_records_during_block(ground_truth, project_input):
    """실제 Block 구간에는 해당 Task 문서의 리비전이 없어야 한다 (활동 감소 신호가 데이터에 존재)."""
    tasks = {t.task_id: t for t in project_input.tasks}
    for s in ground_truth.stagnations:
        if not s.is_actual_block:
            continue
        docs = set(tasks[s.task_id].related_document_ids)
        end = s.resolved_at or s.evaluation_as_of
        during = [r for r in project_input.document_history
                  if r.document_id in docs and s.block_started_at < r.edited_at < end]
        assert not during, f"{s.gt_stagnation_id}: {[r.revision_id for r in during]}"
