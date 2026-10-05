"""Stagnation Agent: Case03/04/10 흐름, 지원자 선정, Human-in-the-loop, RESOLVED 조건, 정책 단위 규칙."""

import json
from datetime import timedelta

import pytest

from contrilog.agent.stagnation import StagnationPolicy, StagnationThresholds, interpret_status_reply
from contrilog.data_access import load_project_input
from contrilog.schemas import ActionStatus, DecisionType, ReplySemantic, StagnationState as S
from contrilog.schemas import SupportCandidateAssessment, TaskSignals, TaskStatus
from tests.stagnation_fixtures import kst, monitor, unit_runs

FULL = load_project_input("P001")
TIMES = {**{r.revision_id: r.edited_at for r in FULL.document_history},
         **{m.message_id: m.sent_at for m in FULL.messages}}


@pytest.fixture(scope="module")
def full():
    return monitor()


def _one(runs, task, member):
    (r,) = unit_runs(runs, task, member)
    return r


# ---------------------------------------------------------------- A. Case03 vs Case04
def test_A_case03_and_case04_look_alike_then_diverge_after_check_in(full):
    runs = full[3]
    c03, c04 = _one(runs, "T03", "M_C"), _one(runs, "T04", "M_D")
    s03, s04 = c03.observed_signals[0], c04.observed_signals[0]
    assert c03.started_at == c04.started_at == kst(9, 19, 9)
    assert s03.status == s04.status == TaskStatus.IN_PROGRESS and s03.hours_until_due_end == s04.hours_until_due_end
    assert c03.candidate_checks[0].conditions == c04.candidate_checks[0].conditions and \
        all(c03.candidate_checks[0].conditions.values())
    assert s03.hours_since_last_task_activity >= 72 and s04.hours_since_last_task_activity >= 72
    sem03 = c03.check_ins[0].reply_interpretations[0].semantic
    sem04 = c04.check_ins[0].reply_interpretations[0].semantic
    assert (sem03, sem04) == (ReplySemantic.REPORTS_BLOCKED, ReplySemantic.REPORTS_ON_TRACK)
    assert c03.state_sequence == [S.NORMAL, S.STAGNATION_CANDIDATE, S.CONFIRMED_BLOCK]
    assert c04.state_sequence == [S.NORMAL, S.STAGNATION_CANDIDATE, S.NORMAL]


def test_case03_external_dependency_is_not_forced_into_support(full):
    r = _one(full[3], "T03", "M_C")
    assert r.support_analysis.block_kind == "EXTERNAL_DEPENDENCY" and r.support_analysis.selected_member_id is None
    assert r.intervention is None and r.state_at(kst(10, 13)) == S.CONFIRMED_BLOCK
    assert r.follow_ups and not any(f.resolved for f in r.follow_ups)
    assert r.check_ins[0].question_intent.value == "STATUS_CHECK" and r.check_ins[0].target_member_id == "M_C"


def test_case04_never_confirmed_and_not_asked_again_before_due(full):
    runs = unit_runs(full[3], "T04", "M_D")
    assert len(runs) == 1 and S.CONFIRMED_BLOCK not in runs[0].state_sequence
    assert runs[0].confirmed_state == S.NORMAL and runs[0].intervention is None
    assert runs[0].state_at(kst(9, 24)) == S.NORMAL


def test_status_check_question_is_about_the_task_not_the_person(full):
    for r in full[3]:
        for c in r.check_ins:
            assert "작업 상황을 확인" in c.question and "도움이 필요한 부분" in c.question
            for word in ["왜", "안 하", "게으", "책임", "늦"]:
                assert word not in c.question


# ---------------------------------------------------------------- B. Case10 E2E
def test_B_case10_full_e2e_timeline_in_order(full):
    r = _one(full[3], "T11", "M_C")
    kinds = [e.kind for e in r.timeline]
    expected = ["OBSERVE", "DECISION", "CHECK_IN", "REPLY", "DECISION", "SUPPORT_ANALYSIS", "INTERVENTION", "HUMAN",
                "ACTION", "SUPPORT_RESPONSE", "FOLLOW_UP", "DECISION"]
    it = iter(kinds)
    assert all(any(k == e for k in it) for e in expected), kinds
    times = [e.at for e in r.timeline]
    assert times == sorted(times)
    assert r.state_sequence == [S.NORMAL, S.STAGNATION_CANDIDATE, S.CONFIRMED_BLOCK, S.RESOLVED]


def test_B_supporter_found_by_evidence_and_explained(full):
    r = _one(full[3], "T11", "M_C")
    a = r.support_analysis
    assert a.block_kind == "INTERNAL_ISSUE" and a.selected_member_id == "M_B"
    chosen = next(c for c in a.candidates if c.member_id == "M_B")
    assert chosen.best_related_source_id == "REV-064" and chosen.prior_help_source_ids == ["MSG-021", "MSG-022"]
    assert chosen.available and not chosen.urgent_task_ids
    assert "REV-064" in a.reason and "MSG-021" in a.reason
    assert "M_C" not in {c.member_id for c in a.candidates}  # 막힌 담당자 자신은 후보가 아니다
    for field in SupportCandidateAssessment.model_fields:
        assert not any(w in field for w in ("score", "rank", "rating", "expertise", "skill"))


def test_B_support_sent_only_after_human_approval(full):
    session, agent, human, runs = full
    r = _one(runs, "T11", "M_C")
    hist = r.intervention.status_history
    assert [h.status for h in hist] == [ActionStatus.PROPOSED, ActionStatus.APPROVED, ActionStatus.SENT]
    assert hist[0].changed_by is None and hist[1].changed_by == "M_C" and hist[2].changed_by is None
    assert hist[0].changed_at < hist[1].changed_at <= hist[2].changed_at
    assert [a[1] for a in human.applied] == [r.intervention.action_id]
    proposals = [d for d in r.decisions if d.decision_type == DecisionType.INTERVENTION_PROPOSAL]
    assert proposals and proposals[0].supporter_member_id == "M_B"
    sends = [c for c in session.call_log if c.tool_name == "SupportRequestTool" and c.operation == "send"]
    assert len(sends) == 1 and sends[0].as_of >= hist[1].changed_at


def test_C_resolved_only_after_observed_follow_up_evidence(full):
    r = _one(full[3], "T11", "M_C")
    resolved = next(t for t in r.transitions if t.to_state == S.RESOLVED)
    sent_at = r.intervention.status_history[-1].changed_at
    reply = r.support_interactions[0]
    assert reply.reply_interpretations[0].semantic == ReplySemantic.ACCEPTS_SUPPORT
    assert resolved.at > sent_at and resolved.source_ids == ["REV-058"]
    assert TIMES["REV-058"] > sent_at and TIMES["REV-058"] <= resolved.at
    before = [f for f in r.follow_ups if f.at < resolved.at]
    assert before and not any(f.resolved for f in before)  # 지원 전송·수락만으로는 해결이 아니다
    assert any(t.at < TIMES["REV-058"] and t.to_state == S.CONFIRMED_BLOCK for t in r.transitions)


def test_decisions_are_chained_and_typed(full):
    r = _one(full[3], "T11", "M_C")
    types = [d.decision_type for d in r.decisions]
    assert DecisionType.CHECKIN_REQUEST in types and DecisionType.INTERVENTION_PROPOSAL in types
    assert [d.stagnation_state for d in r.decisions if d.decision_type == DecisionType.STAGNATION_ASSESSMENT] == \
           [S.STAGNATION_CANDIDATE, S.CONFIRMED_BLOCK, S.RESOLVED]
    for prev, cur in zip(r.decisions, r.decisions[1:]):
        assert cur.previous_decision_id == prev.decision_id


def test_runs_are_task_centric_without_person_labels(full):
    text = json.dumps([r.model_dump(mode="json") for r in full[3]], ensure_ascii=False)
    for word in ["lazy", "slow member", "unreliable", "ghosting", "low contributor", "problematic", "무임승차",
                 "문제 팀원", "게으", "불성실"]:
        assert word not in text


# ---------------------------------------------------------------- 정책·해석 단위 규칙
def _signals(**kw):
    base = dict(task_id="T90", assignee_id="M_A", observed_at=kst(10, 1, 9), status=TaskStatus.IN_PROGRESS,
                due_date=kst(10, 4).date(), hours_until_due_end=86.0, hours_since_last_task_activity=80.0,
                last_activity_source_id="REV-001", recent_revision_ids=[], unfinished_dependency_ids=[])
    base.update(kw)
    return TaskSignals(**base)


@pytest.mark.parametrize("change,expected", [
    ({}, True),
    ({"hours_until_due_end": 400.0}, False),  # 오래 조용해도 마감이 멀면 후보 아님
    ({"hours_since_last_task_activity": 10.0}, False),  # 마감이 가까워도 최근 활동이 있으면 아님
    ({"status": TaskStatus.TODO}, False),  # 시작 전 Task
    ({"status": TaskStatus.DONE}, False),
    ({"unfinished_dependency_ids": ["T91"]}, False),  # 선행 Task 대기
])
def test_policy_needs_combined_signals(change, expected):
    assert StagnationPolicy().check(_signals(**change)).is_candidate is expected


def test_policy_respects_on_track_trust_and_check_in_cooldown():
    p = StagnationPolicy()
    assert not p.check(_signals(), trusted_until=kst(10, 3)).is_candidate
    assert not p.check(_signals(), last_asked_at=kst(9, 30, 12)).is_candidate
    assert p.check(_signals(), last_asked_at=kst(9, 29)).is_candidate


def test_thresholds_are_separate_from_policy():
    strict = StagnationPolicy(StagnationThresholds(min_idle_hours=100.0, max_idle_hours=120.0))
    assert not strict.check(_signals()).is_candidate  # 같은 신호라도 기준값만 바꾸면 결과가 바뀐다
    assert strict.check(_signals()).thresholds["idle_limit_hours"] == 100.0


@pytest.mark.parametrize("text,semantic", [
    ("API 인증 오류 때문에 진행하지 못하고 있습니다.", ReplySemantic.REPORTS_BLOCKED),
    ("로컬에서 작업 중이고 오늘 17:30에 올릴 예정입니다.", ReplySemantic.REPORTS_ON_TRACK),
    ("로컬에서 하느라 기록이 없었어요. 막힌 건 없어요.", ReplySemantic.REPORTS_ON_TRACK),
    ("다 고쳐서 지금은 정상으로 동작해요.", ReplySemantic.CONFIRMS_COMPLETION),
    ("주말에 얘기해요.", ReplySemantic.NOT_INFORMATIVE),
])
def test_status_reply_interpretation(text, semantic):
    assert interpret_status_reply(text)[0] == semantic


def test_unclear_reply_never_becomes_block(tmp_path):
    def unclear(sim):
        for r in sim:
            if r["question_intent"] == "STATUS_CHECK":
                r["reply_text"] = "주말에 얘기해요."
        return sim
    _, _, _, runs = monitor(tmp_path, simulation_transform=unclear)
    assert not [r for r in runs if S.CONFIRMED_BLOCK in r.state_sequence]
    r03 = unit_runs(runs, "T03", "M_C")[0]
    assert r03.state_at(kst(9, 21)) == S.STAGNATION_CANDIDATE
