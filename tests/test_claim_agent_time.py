"""Claim Agent의 as_of 준수: 미래 기록이 현재 판단을 지지하면 안 된다."""

import pytest

from contrilog.agent.claim_verification import ClaimNotFoundError
from contrilog.data_access import load_project_input
from contrilog.schemas import ClaimStatus as CS
from contrilog.schemas import ContributionType as CT
from tests.claim_fixtures import claim, load_raw, run_claims, write_data_root
from tests.timeline_helpers import kst

FULL = load_project_input("P001")
TIMES = {**{u.utterance_id: u.spoken_at for u in FULL.utterances},
         **{r.revision_id: r.edited_at for r in FULL.document_history},
         **{m.message_id: m.sent_at for m in FULL.messages}}


@pytest.fixture
def root(tmp_path):
    raw = load_raw()
    raw["claims"] += [
        claim("CLM-31", "M_D", "2026-09-20T10:00:00+09:00", "평가용 샘플 데이터셋과 생성 스크립트를 만들었습니다."),
        claim("CLM-32", "M_A", "2026-09-16T09:00:00+09:00", "타임라인 뷰를 직접 구현했습니다."),
        claim("CLM-33", "M_A", "2026-09-14T18:00:00+09:00", "타임라인 뷰 아이디어를 제가 제안했습니다."),
    ]
    return write_data_root(tmp_path, raw)


def _only(run):
    (r,) = run.atomic_results
    return r


def _assert_no_future(run, as_of):
    for e in run.evidence:
        if e.source_id in TIMES:
            assert TIMES[e.source_id] <= as_of, e.source_id


def test_execution_t1_before_results_not_verified_t2_after_verified(root):
    t1, t2 = kst(9, 21, 12), kst(9, 23, 14)
    r1 = _only(run_claims(t1, ["CLM-31"], root)["CLM-31"])
    assert r1.predicted_status != CS.VERIFIED and r1.predicted_status == CS.PENDING_VERIFICATION
    assert {"REV-019", "REV-020", "MSG-014"}.isdisjoint(r1.supporting_source_ids)
    assert "T04" in r1.context_source_ids  # 그 시점 Task는 진행 중 (완료 근거 아님)
    run2 = run_claims(t2, ["CLM-31"], root)["CLM-31"]
    r2 = _only(run2)
    assert r2.predicted_status == CS.VERIFIED
    assert {"REV-019", "REV-020", "T04"} <= set(r2.supporting_source_ids)
    _assert_no_future(run2, t2)


def test_execution_before_any_implementation_is_not_verified(root):
    """9/16에는 '구현해 볼게요'(의도)와 설계 문서 기록뿐이고 구현 리비전은 아직 없다."""
    run1 = run_claims(kst(9, 16, 12), ["CLM-32"], root)["CLM-32"]
    r1 = _only(run1)
    assert r1.predicted_status == CS.PENDING_VERIFICATION
    timeline_revisions = {r.revision_id for r in FULL.document_history if r.document_id == "DOC-TIMELINE"}
    assert not timeline_revisions & set(r1.supporting_source_ids)
    assert any("완료" in q or "직접" in q for q in r1.unresolved_questions)
    _assert_no_future(run1, kst(9, 16, 12))
    run2 = run_claims(kst(10, 2), ["CLM-32"], root)["CLM-32"]
    assert _only(run2).predicted_status == CS.VERIFIED
    _assert_no_future(run2, kst(10, 2))


def test_idea_judgment_changes_only_when_records_appear(root):
    before = _only(run_claims(kst(9, 14, 18, 30), ["CLM-33"], root)["CLM-33"])
    assert before.predicted_status == CS.INSUFFICIENT_EVIDENCE and not before.contradicting_source_ids
    # MT03 회의(9/14 19:00~20:00) 종료 전: 회의록이 아직 공개되지 않음
    during = _only(run_claims(kst(9, 14, 19, 30), ["CLM-33"], root)["CLM-33"])
    assert "UT-MT03-04" not in during.contradicting_source_ids
    after = run_claims(kst(9, 15, 12), ["CLM-33"], root)["CLM-33"]
    r = _only(after)
    assert r.predicted_contribution_type == CT.IDEA and r.predicted_status == CS.CONFLICTING_EVIDENCE
    assert "UT-MT03-04" in r.contradicting_source_ids and "REV-013" in r.supporting_source_ids
    _assert_no_future(after, kst(9, 15, 12))


def test_claim_not_yet_submitted_cannot_be_verified():
    with pytest.raises(ClaimNotFoundError):
        run_claims(kst(10, 15, 20, 11), ["CLM-06"])


@pytest.mark.parametrize("as_of", [kst(10, 15, 22, 35), kst(10, 16)])
def test_all_evidence_precedes_as_of(as_of):
    runs = run_claims(as_of, ["CLM-01", "CLM-06", "CLM-08"])
    for run in runs.values():
        _assert_no_future(run, as_of)
        assert all(s for s in run.search_steps)
