"""Claim 검증 Agent: Ground Truth가 있는 모든 입력 Claim + Case07 B SUPPORT(테스트용 Claim)."""

import re

import pytest

from contrilog.data_access import load_project_input
from contrilog.evaluation.claim_comparison import compare_claim_run
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.schemas import ClaimStatus as CS
from contrilog.schemas import ClaimVerificationRun
from contrilog.schemas import ContributionType as CT
from contrilog.schemas import EvidenceRelation as R
from contrilog.tools import ToolSession
from contrilog.agent.claim_verification import ClaimVerificationAgent
from tests.claim_fixtures import claim, load_raw, run_claims, write_data_root
from tests.timeline_helpers import kst

AS_OF = kst(10, 16)
GT = load_ground_truth("P001")
FULL = load_project_input("P001")
CLAIM_IDS = sorted({j.claim_id for j in GT.claim_judgments})


@pytest.fixture(scope="module")
def session_and_runs():
    session = ToolSession("P001", AS_OF)
    agent = ClaimVerificationAgent(tools=session.tools)
    return session, {cid: agent.verify_claim(claim_id=cid) for cid in CLAIM_IDS}


@pytest.fixture(scope="module")
def runs(session_and_runs):
    return session_and_runs[1]


def _result(run, ctype):
    (r,) = [r for r in run.atomic_results if r.predicted_contribution_type == ctype]
    return r


# ---------------------------------------------------------------- Ground Truth 전체 비교
@pytest.mark.parametrize("claim_id", CLAIM_IDS)
def test_every_ground_truth_claim_matches(runs, claim_id):
    for cmp in compare_claim_run(runs[claim_id], GT):
        assert cmp.expected_status is not None, f"과분해: {cmp}"
        assert cmp.predicted_status is not None, f"미분해: {cmp}"
        assert cmp.status_match, cmp
        assert not cmp.contradicting_missing, cmp
        assert not cmp.inaccessible_cited, cmp
        # 기대 지지 근거의 대부분을 찾아야 한다
        exp = len(cmp.supporting_found) + len(cmp.supporting_missing)
        assert len(cmp.supporting_found) >= exp * 0.6, cmp


# ---------------------------------------------------------------- Case별
def test_case01_a_idea_verified(runs):
    r = _result(runs["CLM-01"], CT.IDEA)
    assert r.claimant_id == "M_A" and r.predicted_status == CS.VERIFIED
    assert {"UT-MT02-03", "REV-005"} <= set(r.supporting_source_ids)


def test_case02_b_idea_insufficient_not_conflicting(runs):
    """D의 최초 제안(UT-MT05-04)은 반박 기록이지만, B를 제안 행위와 연결하는 지지 기록이 없으므로
    프로젝트 정의상 CONFLICTING(지지+반박)이 아니라 INSUFFICIENT_EVIDENCE다."""
    r = _result(runs["CLM-02"], CT.IDEA)
    assert r.predicted_status == CS.INSUFFICIENT_EVIDENCE
    assert r.supporting_source_ids == [] and r.contradicting_source_ids == ["UT-MT05-04"]
    ev = next(e for e in runs["CLM-02"].evidence if e.source_id == "UT-MT05-04")
    assert ev.member_id == "M_D" and ev.contribution_type == CT.IDEA
    # B의 슬라이드 작업(실행)은 아이디어 제안 근거로 쓰지 않는다
    assert "REV-048" not in r.supporting_source_ids and "MSG-033" not in r.supporting_source_ids
    assert "기여가 없었다는 뜻이 아니라" in r.rationale


def test_case05_a_review_verified(runs):
    r = _result(runs["CLM-03"], CT.REVIEW)
    assert r.predicted_status == CS.VERIFIED
    assert {"MSG-018", "REV-033"} <= set(r.supporting_source_ids)


def test_case06_b_execution_verified_without_ranking(runs):
    r = _result(runs["CLM-04"], CT.EXECUTION)
    assert r.predicted_status == CS.VERIFIED and r.claimant_id == "M_B"
    b_midreport = {x.revision_id for x in FULL.document_history
                   if x.document_id == "DOC-MIDREPORT" and x.author_id == "M_B"}
    others_midreport = {x.revision_id for x in FULL.document_history
                        if x.document_id == "DOC-MIDREPORT" and x.author_id != "M_B"}
    assert b_midreport <= set(r.supporting_source_ids)
    assert not others_midreport & set(r.supporting_source_ids + r.contradicting_source_ids)
    run = runs["CLM-04"]
    text = run.rationale + " ".join(q for q in run.unresolved_questions)
    for word in ["보다 많", "더 많", "가장", "순위", "랭킹", "점수", "중요도", "%"]:
        assert word not in text
    for name in ["윤서진", "박지후", "이하은"]:  # 다른 팀원과 비교하지 않는다
        assert name not in r.rationale


def test_case07_b_support_verified(tmp_path):
    raw = load_raw()
    raw["claims"].append(claim("CLM-21", "M_B", "2026-10-15T21:10:00+09:00",
                               "지후님의 대시보드 API 배포 중 생긴 CORS 오류 해결을 도왔습니다."))
    run = run_claims(AS_OF, ["CLM-21"], write_data_root(tmp_path, raw))["CLM-21"]
    r = _result(run, CT.SUPPORT)
    assert r.predicted_status == CS.VERIFIED
    gtc = next(c for c in GT.contributions if c.case_id == "CASE07" and c.contribution_type == CT.SUPPORT)
    assert set(gtc.expected_evidence_ids) <= set(r.supporting_source_ids)
    assert "MSG-020" in r.context_source_ids  # C의 문제 보고는 맥락
    assert all(e.member_id == "M_B" for e in run.evidence if e.relation == R.SUPPORTS)


def test_case07_c_execution_verified(runs):
    r = _result(runs["CLM-05"], CT.EXECUTION)
    assert r.predicted_status == CS.VERIFIED and "REV-031" not in r.supporting_source_ids  # B의 nginx 수정은 C 근거 아님


def test_case08_atomic_split_and_evidence_separation(runs):
    run = runs["CLM-06"]
    assert len(run.atomic_claims) == 2
    assert {c.claim_id for c in run.atomic_claims} == {"CLM-06-01", "CLM-06-02"}
    idea, execution = _result(run, CT.IDEA), _result(run, CT.EXECUTION)
    assert idea.predicted_status == CS.CONFLICTING_EVIDENCE
    assert execution.predicted_status == CS.VERIFIED
    by_source = {(e.claim_id, e.source_id): e for e in run.evidence}
    d_proposal = by_source[(idea.atomic_claim_id, "UT-MT03-04")]
    assert (d_proposal.relation, d_proposal.member_id, d_proposal.contribution_type) == (R.CONTRADICTS, "M_D", CT.IDEA)
    a_ack = by_source[(idea.atomic_claim_id, "UT-MT03-05")]
    assert (a_ack.relation, a_ack.member_id) == (R.CONTRADICTS, "M_D")  # A 본인이 D의 아이디어라고 말함
    assert {"REV-013", "MSG-008"} == set(idea.supporting_source_ids)
    exec_ev = [e for e in run.evidence if e.claim_id == execution.atomic_claim_id]
    assert exec_ev and all(e.member_id == "M_A" and e.contribution_type == CT.EXECUTION for e in exec_ev)
    assert "UT-MT03-04" not in {e.source_id for e in exec_ev}
    assert {"REV-015", "REV-016", "REV-021", "REV-036", "REV-039", "T05"} <= set(execution.supporting_source_ids)


def test_case09_b_coordination_verified(runs):
    r = _result(runs["CLM-07"], CT.COORDINATION)
    assert r.predicted_status == CS.VERIFIED and {"MSG-028", "REV-040"} <= set(r.supporting_source_ids)


# ---------------------------------------------------------------- 구조·추적성
def test_run_structure_and_machine_readable_output(runs):
    for run in runs.values():
        ClaimVerificationRun.model_validate(run.model_dump())
        assert run.as_of == AS_OF and run.search_steps and run.decisions
        for r in run.atomic_results:
            assert r.used_evidence_ids and r.rationale
            assert {e.evidence_id for e in run.evidence if e.claim_id == r.atomic_claim_id} == set(r.used_evidence_ids)
        for d in run.decisions:
            assert d.decision_type.value == "CLAIM_VERIFICATION" and d.claim_status is not None
        for c in run.atomic_claims:
            assert c.parent_claim_id == run.submitted_claim_id and c.claimed_type is not None


def test_evidence_is_subset_of_search_results_and_traceable(runs):
    sources = FULL.source_record_ids()
    dms = {m.message_id for m in FULL.messages if m.channel_type.value == "DIRECT_MESSAGE"}
    for run in runs.values():
        returned = {sid for s in run.search_steps for sid in s.returned_source_ids}
        used = {e.source_id for e in run.evidence}
        assert used <= returned  # 검색 결과에 있던 기록만 근거가 된다
        assert used <= sources and not used & dms
        assert len(used) < len(returned)  # 검색 결과 전체를 근거로 만들지 않는다
        for e in run.evidence:
            assert re.fullmatch(r"(UT-MT\d{2}-\d{2}|REV-\d{3}|T\d{2}|MSG-\d{3})", e.source_id)


def test_tool_calls_are_logged_and_no_human_actions(session_and_runs):
    session, runs = session_and_runs
    log = session.call_log
    assert sum(len(r.search_steps) for r in runs.values()) == len(log)
    assert {c.tool_name for c in log} <= {"ClaimTool", "ProjectStatusTool", "MeetingSearchTool",
                                         "DocumentHistoryTool", "MessageSearchTool"}
    assert all(c.status.value == "OK" for c in log)


def test_rerun_reuses_atomic_claims_and_is_deterministic():
    s1, s2 = ToolSession("P001", AS_OF), ToolSession("P001", AS_OF)
    a1, a2 = ClaimVerificationAgent(tools=s1.tools), ClaimVerificationAgent(tools=s2.tools)
    first = a1.verify_claim(claim_id="CLM-06")
    again = a1.verify_claim(claim_id="CLM-06")
    other = a2.verify_claim(claim_id="CLM-06")
    assert [c.claim_id for c in again.atomic_claims] == ["CLM-06-01", "CLM-06-02"]
    assert first.atomic_results == other.atomic_results


def test_as_of_mismatch_rejected():
    session = ToolSession("P001", AS_OF)
    with pytest.raises(ValueError):
        ClaimVerificationAgent(tools=session.tools).verify_claim(claim_id="CLM-01", as_of=kst(10, 20))
