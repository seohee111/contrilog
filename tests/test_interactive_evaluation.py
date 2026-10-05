"""Interactive Evaluator: Ground Truth 시나리오로 질문 대상·Task·의도·응답 사용·의미 해석·최종 판정을 채점한다."""

import json

import pytest

from contrilog.agent.claim_verification import ClaimVerificationAgent
from contrilog.agent.claim_verification.interactive import RuleBasedInteractivePlanner, task_title
from contrilog.agent.claim_verification.protocols import PlannedCheckIn
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.interactive_evaluation import (
    InteractionEvaluation,
    evaluate_run,
    evaluate_scenarios,
    run_episode,
    summarize,
)
from contrilog.schemas import QuestionIntent as QI
from contrilog.schemas.ground_truth import InteractiveScenario
from tests.test_claim_agent_generalization import _noise

GT = load_ground_truth("P001")
SCENARIOS = GT.interactive_scenarios


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    return evaluate_scenarios(SCENARIOS, tmp_path_factory.mktemp("eval"))


def _metrics(e: InteractionEvaluation) -> dict:
    """ID·경로와 무관한 채점 결과."""
    d = e.model_dump(mode="json")
    for c in d["interactions"]:
        c.pop("action_id"), c.pop("reply_ids")
    d.pop("run_id")
    return d


# ---------------------------------------------------------------- 평가 결과
def test_all_scenarios_pass_every_metric(baseline):
    assert [e.scenario_id for e, _ in baseline] == ["ISC-01", "ISC-02", "ISC-03", "ISC-04", "ISC-05"]
    for e, _ in baseline:
        assert e.all_correct, e.model_dump()


def test_evaluation_result_is_machine_readable(baseline):
    e, _ = baseline[4]
    d = json.loads(json.dumps(e.model_dump(mode="json")))
    (c,) = d["interactions"]
    for key in ["target_correct", "task_correct", "intent_correct", "reply_used", "semantic_interpretation_correct"]:
        assert c[key] is True
    assert d["final_judgment_correct"] is True and c["actual_semantic"] == "CONFIRMS_COUNTERPART"


def test_summary_reports_counts_with_caveat(baseline):
    s = summarize([e for e, _ in baseline])
    assert (s.question_intent.correct, s.question_intent.total) == (5, 5)
    assert (s.final_judgment.correct, s.final_judgment.total) == (5, 5) and s.unexpected_questions == 0
    assert "성능 추정치로 해석하지 않는다" in s.caveat
    assert "%" not in json.dumps(s.model_dump(mode="json"), ensure_ascii=False)


def test_evaluator_detects_wrong_target_task_and_semantic(baseline):
    e, run = baseline[4]
    sc = SCENARIOS[4]
    wrong = sc.model_copy(update={"expected_interactions": [sc.expected_interactions[0].model_copy(update={
        "responder_id": "M_B", "task_id": "T06", "expected_semantic_outcome": "DENIES_COUNTERPART"})]})
    (c,) = evaluate_run(run, wrong).interactions
    assert not c.target_correct and not c.task_correct and not c.semantic_interpretation_correct and c.intent_correct


# ---------------------------------------------------------------- Test 8: 의도 mutation은 평가에서 실패한다
class _SwappedIntentPlanner(RuleBasedInteractivePlanner):
    def plan(self, gap, atomic, ctx, already_asked):
        p = super().plan(gap, atomic, ctx, already_asked)
        if not isinstance(p, PlannedCheckIn):
            return p
        swapped = {QI.COMPLETION_CONFIRMATION: QI.COUNTERPART_CONFIRMATION,
                   QI.COUNTERPART_CONFIRMATION: QI.COMPLETION_CONFIRMATION}[p.question_intent]
        return PlannedCheckIn(p.target_member_id, p.task_id, p.question, p.target_reason, swapped)


def test_8_intent_mutation_is_caught_by_evaluation(tmp_path):
    results = evaluate_scenarios(SCENARIOS, tmp_path, agent_factory=lambda tools: ClaimVerificationAgent(
        tools=tools, interactive_planner=_SwappedIntentPlanner()))
    for e, _ in results:
        assert not e.all_correct
        assert not any(c.intent_correct for c in e.interactions)
        assert not any(c.semantic_interpretation_correct for c in e.interactions)
    s = summarize([e for e, _ in results])
    assert s.question_intent.correct == 0
    assert s.final_judgment.correct < s.final_judgment.total  # 응답을 못 받아 VERIFIED에 도달하지 못함


# ---------------------------------------------------------------- 일반화: 같은 채점 결과가 나와야 한다
def test_claim_id_change(tmp_path, baseline):
    for (base, _), sc in zip(baseline, SCENARIOS):
        moved = sc.model_copy(update={"probe_claim": sc.probe_claim.model_copy(update={"claim_id": "CLM-88"})})
        _, run = run_episode(moved, tmp_path / sc.scenario_id)
        assert _metrics(evaluate_run(run, moved)) == _metrics(base)


def test_case_id_change(tmp_path, baseline):
    for (base, _), sc in zip(baseline, SCENARIOS):
        renamed = sc.model_copy(update={"case_id": "CASE09" if sc.case_id != "CASE09" else "CASE01"})
        _, run = run_episode(renamed, tmp_path / sc.scenario_id)
        got, want = _metrics(evaluate_run(run, renamed)), _metrics(base)
        got.pop("case_id"), want.pop("case_id")
        assert got == want


NEW_NAMES = {"윤서진": "강가람", "한도윤": "문나래", "박지후": "서다온", "이하은": "조라온",
             "서진": "가람", "도윤": "나래", "지후": "다온", "하은": "라온"}


def _rename_text(text):
    for old, new in NEW_NAMES.items():
        text = text.replace(old, new)
    return text


def _rename(obj):
    return json.loads(_rename_text(json.dumps(obj, ensure_ascii=False)))


def test_member_name_change(tmp_path, baseline):
    for (base, _), sc in zip(baseline, SCENARIOS):
        renamed = sc.model_copy(update={"probe_claim": sc.probe_claim.model_copy(
            update={"text": _rename_text(sc.probe_claim.text)})})
        _, run = run_episode(renamed, tmp_path / sc.scenario_id, input_transform=_rename, simulation_transform=_rename)
        assert _metrics(evaluate_run(run, renamed)) == _metrics(base)


class _RewordedPlanner(RuleBasedInteractivePlanner):
    @staticmethod
    def question_text(gap, atomic, ctx, task) -> str:
        return f"[확인 요청] {task_title(task)} 건으로 짧게 답변 부탁드립니다."


def test_question_wording_change(tmp_path, baseline):
    results = evaluate_scenarios(SCENARIOS, tmp_path, agent_factory=lambda tools: ClaimVerificationAgent(
        tools=tools, interactive_planner=_RewordedPlanner()))
    for (base, _), (e, run) in zip(baseline, results):
        assert _metrics(e) == _metrics(base)
        assert all(i.question.startswith("[확인 요청]") for i in run.interactions)


def test_unrelated_noise(tmp_path, baseline):
    results = evaluate_scenarios(SCENARIOS, tmp_path, input_transform=_noise)
    for (base, _), (e, _) in zip(baseline, results):
        assert _metrics(e) == _metrics(base)


# ---------------------------------------------------------------- 새 synthetic 시나리오
def _dark_mode_world(raw):
    raw["tasks"].append({
        "task_id": "T21", "project_id": "P001", "title": "다크 모드 적용", "description": "로그인 화면 다크 모드 색상표 작성과 적용",
        "created_by": "M_B", "created_at": "2026-10-03T11:00:00+09:00", "assignee_ids": ["M_A"], "due_date": "2026-10-08",
        "status": "IN_PROGRESS", "due_date_history": [], "related_document_ids": ["DOC-THEME"], "depends_on_task_ids": [],
        "status_history": [
            {"changed_at": "2026-10-03T11:00:00+09:00", "changed_by": "M_B", "from_status": None, "to_status": "TODO", "note": None},
            {"changed_at": "2026-10-04T09:00:00+09:00", "changed_by": "M_A", "from_status": "TODO", "to_status": "IN_PROGRESS", "note": None}]})
    raw["document_history"].append({
        "revision_id": "REV-920", "project_id": "P001", "document_id": "DOC-THEME", "document_title": "web/src/theme/dark.ts",
        "document_type": "CODE", "author_id": "M_A", "edited_at": "2026-10-05T16:00:00+09:00",
        "change_summary": "다크 모드 색상표 토큰 정의", "diff_excerpt": "+ export const dark = { bg: '#121212' }",
        "chars_added": 820, "chars_deleted": 0})
    return raw


def _helped_world(raw):
    raw["document_history"].append({
        "revision_id": "REV-930", "project_id": "P001", "document_id": "DOC-TIMELINE",
        "document_title": "web/src/views/TimelineView.tsx", "document_type": "CODE", "author_id": "M_A",
        "edited_at": "2026-10-03T21:00:00+09:00", "change_summary": "필터 초기화 시 빈 화면 버그 수정 (하은님 도움)",
        "diff_excerpt": "- setRange(null)\n+ setRange(defaultRange)", "chars_added": 120, "chars_deleted": 80})
    return raw


def _sim(reply_id, member, task, intent, start, end, text):
    def add(sim):
        return sim + [{"reply_id": reply_id, "project_id": "P001", "trigger": "CHECKIN", "responder_id": member,
                       "about_member_id": member, "task_id": task, "available_from": start, "available_until": end,
                       "reply_text": text, "reply_delay_minutes": 30, "question_intent": intent}]
    return add


def _scenario(sid, member, submitted, text, verify_at, ctype, final, intent, target, task, semantic):
    return InteractiveScenario.model_validate({
        "scenario_id": sid, "case_id": "CASE01", "title": "새 synthetic 시나리오",
        "probe_claim": {"claim_id": "CLM-70", "member_id": member, "submitted_at": submitted, "text": text},
        "verify_at": verify_at, "expected_contribution_type": ctype,
        "expected_initial_status": "PENDING_VERIFICATION", "expected_final_status": final,
        "expected_interactions": [{"kind": "CHECKIN_REPLY", "task_id": task, "responder_id": target,
                                   "about_member_id": None, "expected_content": "-", "question_intent": intent,
                                   "expected_semantic_outcome": semantic}]})


NEW_SCENARIOS = [
    # completion confirmation: 끝났다는 답 → VERIFIED / 아직이라는 답 → PENDING
    (_scenario("ISC-90", "M_A", "2026-10-06T09:00:00+09:00", "다크 모드 색상표를 작성했습니다.", "2026-10-06T10:00:00+09:00",
               "EXECUTION", "VERIFIED", "COMPLETION_CONFIRMATION", "M_A", "T21", "CONFIRMS_COMPLETION"),
     _dark_mode_world, _sim("SIM-920", "M_A", "T21", "COMPLETION_CONFIRMATION", "2026-10-06T00:00:00+09:00",
                            "2026-10-08T00:00:00+09:00", "색상표 작성 끝냈고 로그인 화면에도 적용 완료했어요.")),
    (_scenario("ISC-91", "M_A", "2026-10-06T09:00:00+09:00", "다크 모드 색상표를 작성했습니다.", "2026-10-06T10:00:00+09:00",
               "EXECUTION", "PENDING_VERIFICATION", "COMPLETION_CONFIRMATION", "M_A", "T21", "REPORTS_INCOMPLETE"),
     _dark_mode_world, _sim("SIM-921", "M_A", "T21", "COMPLETION_CONFIRMATION", "2026-10-06T00:00:00+09:00",
                            "2026-10-08T00:00:00+09:00", "토큰만 정의했고 화면 적용은 아직이에요.")),
    # counterpart confirmation: 지원받은 A가 D의 도움을 확인 / 부인
    (_scenario("ISC-92", "M_D", "2026-10-04T09:00:00+09:00", "서진님의 타임라인 필터 빈 화면 버그 수정을 도왔습니다.",
               "2026-10-04T10:00:00+09:00", "SUPPORT", "VERIFIED", "COUNTERPART_CONFIRMATION", "M_A", "T05",
               "CONFIRMS_COUNTERPART"),
     _helped_world, _sim("SIM-930", "M_A", "T05", "COUNTERPART_CONFIRMATION", "2026-10-04T00:00:00+09:00",
                         "2026-10-10T00:00:00+09:00", "네, 하은님이 같이 재현해 주셔서 원인을 찾았어요.")),
    (_scenario("ISC-93", "M_D", "2026-10-04T09:00:00+09:00", "서진님의 타임라인 필터 빈 화면 버그 수정을 도왔습니다.",
               "2026-10-04T10:00:00+09:00", "SUPPORT", "CONFLICTING_EVIDENCE", "COUNTERPART_CONFIRMATION", "M_A",
               "T05", "DENIES_COUNTERPART"),
     _helped_world, _sim("SIM-931", "M_A", "T05", "COUNTERPART_CONFIRMATION", "2026-10-04T00:00:00+09:00",
                         "2026-10-10T00:00:00+09:00", "아니요, 하은님은 이 버그에 관여하지 않았어요.")),
]


@pytest.mark.parametrize("scenario,world,sim", NEW_SCENARIOS, ids=[s[0].scenario_id for s in NEW_SCENARIOS])
def test_new_synthetic_scenarios(tmp_path, scenario, world, sim):
    _, run = run_episode(scenario, tmp_path, input_transform=world, simulation_transform=sim)
    e = evaluate_run(run, scenario)
    assert e.all_correct, e.model_dump()
