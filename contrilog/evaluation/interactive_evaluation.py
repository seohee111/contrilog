"""Interactive Verification 평가 (평가 계층 전용).

시나리오(Ground Truth의 InteractiveScenario)마다:
1. 입력·시뮬레이션 데이터를 격리된 작업 디렉터리에 복사하고 probe claim을 제출한다 (원본 데이터는 그대로).
2. Agent에게는 ToolSession.tools만 주고 runtime으로 interactive 루프를 실행한다.
   Agent는 시나리오의 기대값을 보지 못한다.
3. Agent의 실행 trace(ClaimVerificationRun)를 기대값과 비교한다.

채점 항목 (기대 질문 하나당):
  A. target_correct   — 올바른 사람에게 물었는가
  B. task_correct     — 올바른 Task로 물었는가
  C. intent_correct   — 올바른 사실(question_intent)을 확인하려 했는가
  D. reply_used       — 도착한 응답(RPL)을 근거·판정에 실제로 사용했는가
  E. semantic_interpretation_correct — 응답 의미를 기대와 같게 해석했는가 (ReplySemantic)
시나리오 단위:
  F. final_judgment_correct — 응답 반영 후 최종 Claim 상태가 맞는가 (+ 유형, 최초 상태)

주의: 시나리오 수가 매우 적고 Agent와 같은 사람이 작성한 synthetic 데이터다. 집계는 회귀 확인용 개수이며
성능 추정치로 해석하면 안 된다.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from pydantic import Field

from contrilog.agent.claim_verification import ClaimVerificationAgent
from contrilog.data_access.paths import DATA_ROOT, INPUT_FILES
from contrilog.runtime import run_interactive_verification
from contrilog.schemas import ClaimStatus, ClaimVerificationRun, ContributionType, QuestionIntent, ReplySemantic
from contrilog.schemas.base import StrictModel
from contrilog.schemas.ground_truth import InteractiveScenario
from contrilog.simulation.loader import REPLIES_FILE, SIMULATION_DIRNAME
from contrilog.tools import ToolSession

CAVEAT = ("소수의 synthetic 시나리오(Agent와 같은 작성자)에 대한 회귀 확인용 개수다. "
          "정확도·성능 추정치로 해석하지 않는다.")


class InteractionCheck(StrictModel):
    expected_intent: QuestionIntent
    expected_target: str
    expected_task: str
    expected_semantic: ReplySemantic
    action_id: Optional[str] = None
    actual_intent: Optional[QuestionIntent] = None
    actual_target: Optional[str] = None
    actual_task: Optional[str] = None
    reply_ids: list[str] = Field(default_factory=list)
    actual_semantic: Optional[ReplySemantic] = None
    target_correct: bool = False
    task_correct: bool = False
    intent_correct: bool = False
    reply_received: bool = False
    reply_used: bool = False
    semantic_interpretation_correct: bool = False


class InteractionEvaluation(StrictModel):
    scenario_id: str
    case_id: str
    run_id: str
    interactions: list[InteractionCheck]
    unexpected_action_ids: list[str] = Field(default_factory=list)  # 기대에 없는 추가 질문
    predicted_contribution_type: Optional[ContributionType] = None
    contribution_type_correct: bool
    predicted_initial_status: Optional[ClaimStatus] = None
    initial_status_correct: bool
    predicted_final_status: Optional[ClaimStatus] = None
    final_judgment_correct: bool

    @property
    def all_correct(self) -> bool:
        checks = [getattr(c, f) for c in self.interactions for f in METRIC_FIELDS[:-1]]
        return all(checks) and not self.unexpected_action_ids and self.contribution_type_correct \
            and self.initial_status_correct and self.final_judgment_correct


METRIC_FIELDS = ["target_correct", "task_correct", "intent_correct", "reply_used",
                 "semantic_interpretation_correct", "final_judgment_correct"]


class MetricCount(StrictModel):
    correct: int
    total: int


class InteractiveEvaluationSummary(StrictModel):
    scenarios: int
    question_target: MetricCount
    task_target: MetricCount
    question_intent: MetricCount
    response_usage: MetricCount
    semantic_interpretation: MetricCount
    final_judgment: MetricCount
    unexpected_questions: int
    caveat: str = CAVEAT


# ---------------------------------------------------------------- episode
def build_episode_root(scenario: InteractiveScenario, workdir: Path, *, project_id: str = "P001",
                       data_root: Path | None = None,
                       input_transform: Callable[[dict], dict] | None = None,
                       simulation_transform: Callable[[list], list] | None = None) -> Path:
    """입력·시뮬레이션 데이터를 workdir에 복사하고 probe claim을 제출한다 (Ground Truth는 복사하지 않는다)."""
    src = data_root or DATA_ROOT
    raw = {k: json.loads((src / "input" / project_id / f).read_text(encoding="utf-8")) for k, f in INPUT_FILES.items()}
    p = scenario.probe_claim
    raw["claims"].append({
        "claim_id": p.claim_id, "project_id": project_id, "member_id": p.member_id,
        "submitted_at": p.submitted_at.isoformat(), "source": "SELF_REPORT_FORM", "source_message_id": None,
        "text": p.text, "parent_claim_id": None, "claimed_type": None, "status": "PENDING_VERIFICATION"})
    if input_transform:
        raw = input_transform(raw)
    sim = json.loads((src / SIMULATION_DIRNAME / project_id / REPLIES_FILE).read_text(encoding="utf-8"))
    if simulation_transform:
        sim = simulation_transform(sim)
    base = workdir / "input" / project_id
    base.mkdir(parents=True, exist_ok=True)
    for k, f in INPUT_FILES.items():
        (base / f).write_text(json.dumps(raw[k], ensure_ascii=False, indent=2), encoding="utf-8")
    sim_dir = workdir / SIMULATION_DIRNAME / project_id
    sim_dir.mkdir(parents=True, exist_ok=True)
    (sim_dir / REPLIES_FILE).write_text(json.dumps(sim, ensure_ascii=False, indent=2), encoding="utf-8")
    return workdir


def run_episode(scenario: InteractiveScenario, workdir: Path, *,
                agent_factory: Callable[[dict], ClaimVerificationAgent] | None = None, **build_kwargs):
    root = build_episode_root(scenario, workdir, **build_kwargs)
    session = ToolSession(build_kwargs.get("project_id", "P001"), scenario.verify_at, data_root=root)
    agent = (agent_factory or (lambda tools: ClaimVerificationAgent(tools=tools)))(session.tools)
    run = run_interactive_verification(session, agent, scenario.probe_claim.claim_id)
    return session, run


# ---------------------------------------------------------------- scoring
def evaluate_run(run: ClaimVerificationRun, scenario: InteractiveScenario) -> InteractionEvaluation:
    used_sources = {e.source_id for e in run.evidence}
    actual = list(run.interactions)
    checks = []
    for n, x in enumerate(scenario.expected_interactions):
        check = InteractionCheck(expected_intent=x.question_intent, expected_target=x.responder_id,
                                 expected_task=x.task_id, expected_semantic=x.expected_semantic_outcome)
        if n < len(actual):  # 기대 질문과 실제 질문을 순서대로 짝짓는다
            i = actual[n]
            latest = {r.reply_id: r.semantic for r in i.reply_interpretations}
            semantics = [latest[r] for r in i.reply_ids if r in latest]
            check = check.model_copy(update=dict(
                action_id=i.action_id, actual_intent=i.question_intent, actual_target=i.target_member_id,
                actual_task=i.task_id, reply_ids=list(i.reply_ids),
                actual_semantic=semantics[-1] if semantics else None,
                target_correct=i.target_member_id == x.responder_id, task_correct=i.task_id == x.task_id,
                intent_correct=i.question_intent == x.question_intent, reply_received=bool(i.reply_ids),
                reply_used=bool(i.reply_ids) and all(r in used_sources for r in i.reply_ids),
                semantic_interpretation_correct=bool(semantics) and semantics[-1] == x.expected_semantic_outcome))
        checks.append(check)
    result = next((r for r in run.atomic_results
                   if r.predicted_contribution_type == scenario.expected_contribution_type), None)
    initial = None
    if result and run.rounds:
        initial = next((s.status for s in run.rounds[0].atomic_states
                        if s.atomic_claim_id == result.atomic_claim_id), None)
    return InteractionEvaluation(
        scenario_id=scenario.scenario_id, case_id=scenario.case_id, run_id=run.run_id, interactions=checks,
        unexpected_action_ids=[i.action_id for i in actual[len(scenario.expected_interactions):]],
        predicted_contribution_type=result.predicted_contribution_type if result else None,
        contribution_type_correct=result is not None,
        predicted_initial_status=initial, initial_status_correct=initial == scenario.expected_initial_status,
        predicted_final_status=result.predicted_status if result else None,
        final_judgment_correct=bool(result) and result.predicted_status == scenario.expected_final_status)


def evaluate_scenarios(scenarios: list[InteractiveScenario], workdir: Path, **episode_kwargs):
    out = []
    for sc in scenarios:
        _, run = run_episode(sc, workdir / sc.scenario_id, **episode_kwargs)
        out.append((evaluate_run(run, sc), run))
    return out


def summarize(evaluations: list[InteractionEvaluation]) -> InteractiveEvaluationSummary:
    checks = [c for e in evaluations for c in e.interactions]

    def count(field):
        return MetricCount(correct=sum(getattr(c, field) for c in checks), total=len(checks))

    return InteractiveEvaluationSummary(
        scenarios=len(evaluations), question_target=count("target_correct"), task_target=count("task_correct"),
        question_intent=count("intent_correct"), response_usage=count("reply_used"),
        semantic_interpretation=count("semantic_interpretation_correct"),
        final_judgment=MetricCount(correct=sum(e.final_judgment_correct for e in evaluations), total=len(evaluations)),
        unexpected_questions=sum(len(e.unexpected_action_ids) for e in evaluations))
