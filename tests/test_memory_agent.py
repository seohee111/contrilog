"""Memory ON 전체 재생: Memory 내용, applied_memory_ids 추적, Case03/04/10 보호, OFF 동일성."""

import json

import pytest

from contrilog.data_access import load_project_input
from contrilog.evaluation.memory_evaluation import memory_checks, mode_metrics, run_mode
from contrilog.schemas import DecisionType, FeedbackLabel, StagnationState as S
from tests.stagnation_fixtures import GT, kst, monitor, unit_runs

MEMBERS = load_project_input("P001").members


@pytest.fixture(scope="module")
def on():
    session, agent, store = run_mode("ON")
    return agent, store, mode_metrics("ON", agent, store, GT)


@pytest.fixture(scope="module")
def off():
    session, agent, store = run_mode("OFF")
    return agent, store, mode_metrics("OFF", agent, store, GT)


def _memory_for(store, runs, task):
    ids = {d.decision_id for r in runs if r.task_id == task for d in r.decisions}
    return [m for m in store.all() if set(m.source_decision_ids) & ids]


def test_off_mode_is_unchanged(off):
    _, _, _, baseline = monitor()  # 기존 StagnationAgent (feedback 인자 없음)
    agent, _, metrics = off
    assert [r.model_dump(mode="json") for r in agent.runs()] == [r.model_dump(mode="json") for r in baseline]
    assert (metrics.candidates, metrics.status_checks, metrics.memories) == (13, 13, 0)


def test_case04_false_positive_memory_is_about_the_judgment_not_the_person(on):
    agent, store, _ = on
    (m,) = _memory_for(store, agent.runs(), "T04")
    assert m.feedback_label == FeedbackLabel.FALSE_POSITIVE and m.observed_signal == "REPORTS_ON_TRACK"
    assert m.previous_decision == S.STAGNATION_CANDIDATE and m.policy_adjustment == "RELAX"
    assert (m.context.deadline_bucket, m.context.idle_ratio_bucket, m.context.task_status, m.context.team_context) == \
           ("DUE_96_168H", "0_5_TO_1", "IN_PROGRESS", "TEAM_ACTIVE")
    text = json.dumps(m.model_dump(mode="json"), ensure_ascii=False)
    for token in ["M_D", "이하은", "하은", "D는"]:
        assert token not in text
    assert m.created_at == kst(9, 19, 9, 45) and m.evidence_ids[0] == "T04"


def test_case03_and_case10_true_positive_and_resolution_success(on):
    agent, store, _ = on
    runs = agent.runs()
    (m03,) = _memory_for(store, runs, "T03")
    assert m03.feedback_label == FeedbackLabel.TRUE_POSITIVE and m03.observed_signal == "REPORTS_BLOCKED"
    m10 = _memory_for(store, runs, "T11")
    assert [m.feedback_label for m in m10] == [FeedbackLabel.TRUE_POSITIVE, FeedbackLabel.RESOLUTION_SUCCESS]
    success = m10[1]
    assert success.context.kind == "INTERVENTION" and success.context.block_kind == "INTERNAL_ISSUE"
    assert success.context.selection_basis == ["RELATED_RECORD", "PRIOR_HELP", "NO_URGENT_OWN_TASK"]
    assert "REV-058" in success.evidence_ids  # 해결 근거
    text = json.dumps(success.model_dump(mode="json"), ensure_ascii=False)
    for token in ["M_B", "한도윤", "도윤", "좋은 지원자"]:
        assert token not in text


def test_no_false_negative_label_exists_for_agent():
    assert "FALSE_NEGATIVE" not in {label.value for label in FeedbackLabel}


def test_unresolved_memories_record_what_was_observed(on):
    _, store, _ = on
    signals = {m.observed_signal for m in store.all() if m.feedback_label == FeedbackLabel.UNRESOLVED}
    assert signals <= {"ACTIVITY_RESUMED_WITHOUT_REPLY", "TASK_COMPLETED_WITHOUT_REPLY", "NOT_INFORMATIVE_REPLY"}


def test_applied_memory_ids_are_recorded_on_decisions(on):
    agent, store, _ = on
    ids = {m.memory_id for m in store.all()}
    for r in agent.runs():
        cand = next(d for d in r.decisions if d.stagnation_state == S.STAGNATION_CANDIDATE)
        assert cand.applied_memory_ids == r.candidate_checks[0].applied_memory_ids
    apps = agent.policy_applications()
    assert apps and all(p.decision.applied_memory_ids == p.check.applied_memory_ids for p in apps)
    assert all(set(p.decision.applied_memory_ids) <= ids for p in apps)
    assert all(p.decision.decision_type == DecisionType.STAGNATION_ASSESSMENT for p in apps)


def test_team_pause_context_removes_holiday_candidates_with_trace(on, off):
    agent, _, metrics = on
    off_tasks = {(r.task_id, r.started_at) for r in off[0].runs()}
    on_tasks = {(r.task_id, r.started_at) for r in agent.runs()}
    removed = off_tasks - on_tasks
    assert {("T06", kst(9, 26, 9)), ("T07", kst(9, 26, 9))} <= removed
    holiday = [p for p in agent.policy_applications() if p.check.team_pause_overlap_hours and p.task_id in ("T06", "T07")]
    assert holiday and all(p.check.base_is_candidate and not p.check.is_candidate for p in holiday)
    assert all(p.check.context.team_context == "TEAM_WIDE_LOW_ACTIVITY" for p in holiday if p.check.observed_at < kst(9, 27, 14))


def test_real_blocks_preserved(on, off):
    _, _, m_on = on
    assert m_on.gt_blocks_detected == ["CASE03", "CASE10"] and not m_on.false_negatives
    assert m_on.non_block_correct["GTS-02"] and m_on.resolved_correct["GTS-03"]
    agent = on[0]
    t11 = unit_runs(agent.runs(), "T11", "M_C")[0]
    assert t11.state_sequence == [S.NORMAL, S.STAGNATION_CANDIDATE, S.CONFIRMED_BLOCK, S.RESOLVED]
    assert t11.intervention is not None and t11.intervention.recipient_id == "M_B"


def test_memory_checks_pass(on, off):
    agent, store, m_on = on
    checks = memory_checks(agent, store, GT, MEMBERS, off[2], m_on)
    assert checks.problems == []
    assert all([checks.memory_created_correctly, checks.no_person_profile, checks.no_future_memory,
                checks.applied_memory_traceable, checks.bounded_adjustment, checks.true_positive_preserved])
    assert checks.question_count_change == -2 and checks.detection_delay_change == {"CASE03": 0.0, "CASE10": 0.0}
