"""Question-aware simulation: 같은 사람·같은 Task라도 질문 의도에 맞는 응답이 오고, Agent가 그 의미를 해석한다."""

import ast
import json
from datetime import timedelta
from pathlib import Path

import pytest

import contrilog
from contrilog.agent.claim_verification import ClaimVerificationAgent
from contrilog.agent.claim_verification.interactive import INTENT_FOR_GAP
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.interactive_evaluation import build_episode_root, evaluate_run, run_episode
from contrilog.runtime import run_interactive_verification
from contrilog.schemas import ClaimStatus as CS
from contrilog.schemas import EvidenceRelation as R
from contrilog.schemas import QuestionIntent as QI
from contrilog.schemas import ReplySemantic as RS
from contrilog.simulation.loader import load_simulated_replies
from contrilog.tools import ToolSession
from tests.timeline_helpers import kst

GT = load_ground_truth("P001")
SC = {s.scenario_id: s for s in GT.interactive_scenarios}
SIM = {r.reply_id: r for r in load_simulated_replies("P001")}


def _ask(at, intent, question="T11 관련해서 확인 부탁드려요.", member="M_C", task="T11", wait=180):
    s = ToolSession("P001", at)
    s.tools["CheckInTool"].send(task_id=task, member_id=member, question=question, question_intent=intent)
    s.advance_to(at + timedelta(minutes=wait))
    return [r.text for r in s.tools["InboxTool"].list_replies().replies]


def _texts(transform_ids: dict[str, str]):
    def apply(sim):
        for r in sim:
            if r["reply_id"] in transform_ids:
                r["reply_text"] = transform_ids[r["reply_id"]]
        return sim
    return apply


# ---------------------------------------------------------------- Test 1
def test_1_same_person_task_time_different_intent_different_reply():
    at = kst(10, 10, 9)
    completion = _ask(at, QI.COMPLETION_CONFIRMATION)
    counterpart = _ask(at, QI.COUNTERPART_CONFIRMATION)
    status = _ask(at, QI.STATUS_CHECK)
    assert completion == [SIM["SIM-016"].reply_text]
    assert counterpart == [SIM["SIM-017"].reply_text]
    assert status == [SIM["SIM-006"].reply_text]
    assert len({completion[0], counterpart[0], status[0]}) == 3


def test_1b_agent_asks_both_intents_to_same_person_and_interprets_each(tmp_path):
    """같은 세션·같은 시각에 C/T11로 두 질문(완료 확인, 상대방 확인)이 나가고, 다른 응답을 다르게 해석한다."""
    c_claim, b_claim = SC["ISC-04"], SC["ISC-05"]

    def add_b_claim(raw):
        raw["claims"].append({"claim_id": "CLM-66", "project_id": "P001", "member_id": "M_B",
                              "submitted_at": "2026-10-09T22:55:00+09:00", "source": "SELF_REPORT_FORM",
                              "source_message_id": None, "text": b_claim.probe_claim.text, "parent_claim_id": None,
                              "claimed_type": None, "status": "PENDING_VERIFICATION"})
        return raw

    root = build_episode_root(c_claim, tmp_path, input_transform=add_b_claim)
    session = ToolSession("P001", c_claim.verify_at, data_root=root)
    agent = ClaimVerificationAgent(tools=session.tools)
    c_run = agent.verify_claim(claim_id="CLM-64")
    b_run = agent.verify_claim(claim_id="CLM-66")
    (ci,), (bi,) = c_run.interactions, b_run.interactions
    assert (ci.target_member_id, ci.task_id, ci.sent_at) == (bi.target_member_id, bi.task_id, bi.sent_at) == \
           ("M_C", "T11", c_claim.verify_at)
    assert (ci.question_intent, bi.question_intent) == (QI.COMPLETION_CONFIRMATION, QI.COUNTERPART_CONFIRMATION)
    session.advance_to(c_claim.verify_at + timedelta(minutes=30))
    c_run, b_run = agent.continue_verification(c_run), agent.continue_verification(b_run)
    c_reply = next(e for e in c_run.evidence if e.source_type.value == "INBOUND_REPLY")
    b_reply = next(e for e in b_run.evidence if e.source_type.value == "INBOUND_REPLY")
    assert c_reply.excerpt != b_reply.excerpt
    assert c_run.interactions[0].reply_interpretations[0].semantic == RS.CONFIRMS_COMPLETION
    assert b_run.interactions[0].reply_interpretations[0].semantic == RS.CONFIRMS_COUNTERPART
    assert c_run.atomic_results[0].predicted_status == b_run.atomic_results[0].predicted_status == CS.VERIFIED


# ---------------------------------------------------------------- Test 2
@pytest.mark.parametrize("intent", [QI.COMPLETION_CONFIRMATION, QI.COUNTERPART_CONFIRMATION])
def test_2_question_wording_does_not_change_selected_reply(intent):
    wordings = ["완료됐나요?", "혹시 이거 했나요?", "Is it done?", "도윤님이 실제로 도와주셨는지 궁금해요.",
                "작업 상태를 한 문장으로 알려 주세요."]
    replies = {tuple(_ask(kst(10, 10, 9), intent, question=w)) for w in wordings}
    assert len(replies) == 1 and replies.pop()


# ---------------------------------------------------------------- Test 3
def test_3_different_intent_never_gets_another_intents_reply():
    at = kst(10, 9, 12)  # 수정 전: 완료 확인 응답(SIM-015)만 있고 상대방 확인 응답은 없는 시간대
    assert _ask(at, QI.COMPLETION_CONFIRMATION) == [SIM["SIM-015"].reply_text]
    assert _ask(at, QI.COUNTERPART_CONFIRMATION, question="작업이 완료됐는지 알려 주세요.") == []
    assert _ask(at, QI.STATUS_CHECK) == [SIM["SIM-004"].reply_text]
    # 질문 문장이 다른 의도를 암시해도 선택은 의도만 따른다
    assert _ask(kst(10, 10, 9), QI.COMPLETION_CONFIRMATION, question="B가 실제로 지원했나요?") == \
           [SIM["SIM-016"].reply_text]


def test_3b_simulation_matching_does_not_read_question_text():
    """시뮬레이션 계층 코드는 질문 문장(message/question)을 읽지 않는다."""
    pkg = Path(contrilog.__file__).parent
    for f in list((pkg / "simulation").glob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("message", "question"), f.name
            if isinstance(node, ast.arg):
                assert node.arg not in ("message", "question"), f.name
    dispatch = ast.parse((pkg / "tools" / "session.py").read_text(encoding="utf-8"))
    for node in ast.walk(dispatch):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "schedule":
            assert "message" not in {k.arg for k in node.keywords}
            assert "question_intent" in {k.arg for k in node.keywords}


# ---------------------------------------------------------------- Test 4
def test_4_support_claim_asks_counterpart_not_claimant_and_verifies(tmp_path):
    sc = SC["ISC-05"]
    session, run = run_episode(sc, tmp_path)
    (i,) = run.interactions
    assert i.target_member_id == "M_C" and i.target_member_id != sc.probe_claim.member_id
    assert i.question_intent == QI.COUNTERPART_CONFIRMATION and i.task_id == "T11"
    assert not [c for c in session.call_log if c.tool_name == "CheckInTool" and c.parameters["member_id"] == "M_B"]
    (interp,) = i.reply_interpretations
    assert (interp.semantic, interp.role, interp.relation) == (RS.CONFIRMS_COUNTERPART, "counterpart_confirmation",
                                                               R.SUPPORTS)
    ev = next(e for e in run.evidence if e.source_id == interp.reply_id)
    assert ev.contribution_type.value == "SUPPORT" and ev.member_id == "M_B"
    assert run.atomic_results[0].predicted_status == CS.VERIFIED
    assert ev.excerpt.startswith(SIM["SIM-017"].reply_text[:40])


# ---------------------------------------------------------------- Test 5
@pytest.mark.parametrize("scenario,override", [
    ("ISC-03", None),
    ("ISC-04", {"SIM-016": "아직 해결하지 못했습니다."}),
])
def test_5_not_yet_resolved_is_not_completion(tmp_path, scenario, override):
    kwargs = {"simulation_transform": _texts(override)} if override else {}
    _, run = run_episode(SC[scenario], tmp_path, **kwargs)
    (interp,) = run.interactions[0].reply_interpretations
    assert interp.semantic == RS.REPORTS_INCOMPLETE and interp.relation == R.CONTEXT
    assert run.atomic_results[0].predicted_status == CS.PENDING_VERIFICATION


# ---------------------------------------------------------------- Test 6
def test_6_explicit_denial_moves_to_conflicting(tmp_path):
    _, run = run_episode(SC["ISC-05"], tmp_path, simulation_transform=_texts(
        {"SIM-017": "아니요, 도윤님은 이 문제에 관여하지 않았어요. 제가 혼자 해결했어요."}))
    (interp,) = run.interactions[0].reply_interpretations
    assert interp.semantic == RS.DENIES_COUNTERPART and interp.relation == R.CONTRADICTS
    assert run.atomic_results[0].predicted_status == CS.CONFLICTING_EVIDENCE


# ---------------------------------------------------------------- Test 7
@pytest.mark.parametrize("scenario,reply_id", [("ISC-04", "SIM-016"), ("ISC-05", "SIM-017")])
def test_7_unrelated_reply_is_not_confirming_evidence(tmp_path, scenario, reply_id):
    _, run = run_episode(SC[scenario], tmp_path, simulation_transform=_texts({reply_id: "내일 회의 몇 시였죠?"}))
    (interp,) = run.interactions[0].reply_interpretations
    assert interp.semantic == RS.NOT_INFORMATIVE and interp.relation == R.CONTEXT
    r = run.atomic_results[0]
    assert interp.reply_id not in r.supporting_source_ids and r.predicted_status == CS.PENDING_VERIFICATION


# ---------------------------------------------------------------- 구조
def test_agent_intent_comes_from_gap_not_text(tmp_path):
    for sc in GT.interactive_scenarios:
        _, run = run_episode(sc, tmp_path / sc.scenario_id)
        for i in run.interactions:
            assert i.question_intent == INTENT_FOR_GAP[i.gap_kind] != QI.STATUS_CHECK


def test_tool_log_keeps_intent_but_redacts_question(tmp_path):
    session, _ = run_episode(SC["ISC-05"], tmp_path)
    (call,) = [c for c in session.call_log if c.tool_name == "CheckInTool"]
    assert call.parameters["question_intent"] == "COUNTERPART_CONFIRMATION"
    assert set(call.parameters["question"]) == {"redacted_chars"}


def test_idea_claims_are_not_sent_counterpart_questions(tmp_path):
    """아이디어는 상대방 확인으로 판정이 해결되지 않으므로 상대방이 있어도 묻지 않는다."""
    sc = SC["ISC-05"].model_copy(update={"probe_claim": SC["ISC-05"].probe_claim.model_copy(update={
        "member_id": "M_A", "text": "로그인 화면 다크 모드 아이디어를 제안했습니다."})})

    def add_mention(raw):
        raw["messages"].append({"message_id": "MSG-960", "project_id": "P001", "channel": "#general",
                                "channel_type": "CHANNEL", "sender_id": "M_C", "recipient_ids": [],
                                "sent_at": "2026-10-03T10:00:00+09:00", "reply_to_message_id": None,
                                "text": "서진님 아이디어대로 로그인 화면에 다크 모드를 넣어 봤어요."})
        return raw

    session, run = run_episode(sc, tmp_path, input_transform=add_mention)
    assert run.atomic_results[0].predicted_status == CS.PENDING_VERIFICATION
    assert run.interactions == [] and "상대방의 확인으로 직접 근거가 되지 않아" in run.rounds[0].gaps[0].unresolvable_reason


def test_scenario_expectations_are_reachable_only_with_matching_intent():
    sims = load_simulated_replies("P001")
    items = [(sc.verify_at, x) for sc in GT.interactive_scenarios for x in sc.expected_interactions]
    for at, x in items:
        same = [r for r in sims if r.trigger.value == "CHECKIN" and r.task_id == x.task_id
                and r.responder_id == x.responder_id and r.available_from <= at < r.available_until]
        assert [r for r in same if r.question_intent == x.question_intent], x
    expectations = [x for c in GT.contributions for x in c.expected_interactive_evidence] + \
                   [x for s in GT.stagnations for x in s.expected_interactive_evidence]
    for x in expectations:
        if x.kind.value == "CHECKIN_REPLY":
            assert any(r.question_intent == x.question_intent and r.task_id == x.task_id
                       and r.responder_id == x.responder_id for r in sims), x


def test_trace_never_contains_expected_outcomes_or_simulation_ids(tmp_path):
    texts = [x.expected_content for sc in GT.interactive_scenarios for x in sc.expected_interactions] + \
            [sc.title for sc in GT.interactive_scenarios]
    for sc in GT.interactive_scenarios:
        _, run = run_episode(sc, tmp_path / sc.scenario_id)
        dumped = json.dumps(run.model_dump(mode="json"), ensure_ascii=False)
        assert "SIM-" not in dumped and "ISC-" not in dumped and "expected" not in dumped
        for t in texts:
            assert t not in dumped
