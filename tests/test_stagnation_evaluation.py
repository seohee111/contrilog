"""Stagnation evaluator: Case03/04/10 채점 결과(machine-readable)와 오류 검출."""

import json

import pytest

from contrilog.agent.stagnation import StagnationAgent
from contrilog.evaluation.stagnation_evaluation import summarize, unlabeled_candidates
from contrilog.schemas import ReplySemantic, StagnationState as S
from tests.stagnation_fixtures import GT, evaluate, kst, monitor


@pytest.fixture(scope="module")
def evals():
    _, _, _, runs = monitor()
    return {e.case_id: e for e in evaluate(runs)}, runs


def test_case03(evals):
    e = evals[0]["CASE03"]
    assert (e.candidate_detected, e.reply_semantic, e.confirmed_block) == (True, ReplySemantic.REPORTS_BLOCKED, True)
    assert e.final_state == S.CONFIRMED_BLOCK and e.final_state_correct and e.sequence_correct
    assert e.intervention_scored is False and e.intervention_proposed is False
    assert e.detection_delay_candidate_hours == 91.3 and e.detection_delay_confirmed_hours == 92.8


def test_case04_false_positive_guard(evals):
    e = evals[0]["CASE04"]
    assert (e.candidate_detected, e.reply_semantic, e.confirmed_block) == (True, ReplySemantic.REPORTS_ON_TRACK, False)
    assert e.final_state == S.NORMAL and e.block_classification_correct and not e.forbidden_state_violations
    assert e.intervention_scored and e.intervention_correct and not e.intervention_proposed


def test_case10_full_e2e(evals):
    e = evals[0]["CASE10"]
    assert e.candidate_detected and e.reply_semantic == ReplySemantic.REPORTS_BLOCKED and e.confirmed_block
    assert e.intervention_proposed and e.intervention_correct and e.supporter_selected == "M_B" and e.supporter_correct
    assert e.sent_only_after_approval and e.approver_id == "M_C"
    assert e.support_reply_semantic == ReplySemantic.ACCEPTS_SUPPORT and e.support_reply_correct
    assert e.follow_up_observed and e.final_state == S.RESOLVED and e.resolution_source_ids == ["REV-058"]
    assert e.resolved_before_fix is False and e.resolved_after_fix_evidence is True
    assert e.detection_delay_candidate_hours == 28.8 and e.detection_delay_confirmed_hours == 29.6
    assert e.status_check_expectations[1]["actual"] is None  # 해결 후 상태 확인은 하지 않음 (후속 근거로 판단)


def test_all_items_correct_and_machine_readable(evals):
    for e in evals[0].values():
        assert e.all_correct, e.model_dump()
        json.loads(json.dumps(e.model_dump(mode="json")))


def test_summary_and_unlabeled_candidates_reported(evals):
    runs = evals[1]
    unlabeled = unlabeled_candidates(runs, GT)
    s = summarize(list(evals[0].values()), len(unlabeled))
    assert (s.block_classification.correct, s.block_classification.total) == (3, 3)
    assert (s.intervention.correct, s.intervention.total) == (2, 2)  # Case03은 채점 안 함
    assert s.unlabeled_candidates == len(unlabeled) > 0 and "추정치로 해석하지 않는다" in s.caveat
    for u in unlabeled:  # 라벨 없는 후보는 모두 확인 없이 Block으로 가지 않았다
        assert "CONFIRMED_BLOCK" not in u["states"]


# ---------------------------------------------------------------- 평가기가 잘못을 잡는가
def _blocked_always(text):
    return ReplySemantic.REPORTS_BLOCKED, "INTERNAL_ISSUE"


def _resolve_on_any_follow_up(revisions, changes):
    return ["T11"], ["T11"]


def test_evaluator_catches_on_track_misread_as_block(tmp_path):
    _, _, _, runs = monitor(tmp_path, agent_factory=lambda tools: StagnationAgent(
        tools=tools, status_interpreter=_blocked_always))
    e = {x.case_id: x for x in evaluate(runs)}["CASE04"]
    assert not e.block_classification_correct and e.forbidden_state_violations and not e.all_correct


def test_evaluator_catches_resolution_without_evidence(tmp_path):
    _, _, _, runs = monitor(tmp_path, agent_factory=lambda tools: StagnationAgent(
        tools=tools, resolution=_resolve_on_any_follow_up))
    e = {x.case_id: x for x in evaluate(runs)}["CASE10"]
    assert e.resolved_before_fix is True and not e.all_correct
    assert e.resolved_at < kst(10, 9, 22, 40)
