"""Stagnation Agent 평가 (평가 계층 전용).

한 번의 연속 모니터링 실행(프로젝트 시작~종료, Agent 하나)에서 나온 StagnationRun들을
Ground Truth의 GroundTruthStagnation 항목과 비교한다. 각 항목은 자기 evaluation_as_of 기준으로 채점한다.
Ground Truth에 없는 (Task, 담당자)에서 생긴 후보는 '라벨 없는 후보'로 따로 보고한다 (채점하지 않음).

주의: 시나리오가 3개뿐인 synthetic 데이터이고 Agent와 같은 작성자가 만들었다. 개수 집계는 회귀 확인용이다.
"""

import json
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

from pydantic import Field

from contrilog.agent.stagnation import StagnationAgent
from contrilog.data_access import load_project_input
from contrilog.data_access.paths import DATA_ROOT, INPUT_FILES
from contrilog.runtime import run_stagnation_monitoring
from contrilog.schemas import ActionStatus, ReplySemantic, StagnationRun, StagnationState
from contrilog.schemas.base import StrictModel
from contrilog.schemas.ground_truth import GroundTruthBundle, GroundTruthStagnation
from contrilog.simulation.human import HumanDecisionSimulator
from contrilog.simulation.loader import HUMAN_DECISIONS_FILE, REPLIES_FILE, SIMULATION_DIRNAME
from contrilog.tools import ToolSession

KST = timezone(timedelta(hours=9))
CAVEAT = ("Agent와 같은 팀이 만든 synthetic 데이터의 Ground Truth 정체 항목에 대한 개수다. "
          "탐지율·정확도 추정치로 해석하지 않는다.")


class StagnationEvaluation(StrictModel):
    gt_stagnation_id: str
    case_id: str
    task_id: str
    member_id: str
    run_ids: list[str]
    state_sequence: list[StagnationState]
    runs_after_block_episode: list[str] = Field(default_factory=list)  # Block 에피소드 이후 같은 단위에서 다시 열린 후보
    candidate_detected: bool
    candidate_expected: Optional[bool] = True  # Ground Truth (None이면 후보 여부를 채점하지 않음)
    candidate_correct: Optional[bool] = None
    first_candidate_at: Optional[datetime] = None
    check_in_correct: Optional[bool]  # 담당자에게, 그 Task로, STATUS_CHECK (확인이 없어도 되는 항목에서 없으면 None)
    reply_semantic: Optional[ReplySemantic] = None
    expected_reply_semantic: Optional[ReplySemantic] = None
    reply_interpretation_correct: Optional[bool]  # 기대 응답 의미가 없거나, 확인이 없어도 되는 항목에서 응답이 없으면 None
    confirmed_block: bool
    confirmed_at: Optional[datetime] = None
    block_classification_correct: bool
    block_kind: Optional[str] = None
    expected_block_kind: Optional[str] = None
    block_kind_correct: Optional[bool] = None  # Ground Truth에 Block 종류가 있고 Agent가 Block을 확정했을 때만
    forbidden_state_violations: list[StagnationState] = Field(default_factory=list)
    sequence_correct: Optional[bool] = None  # 기대 경로가 없으면 None
    final_state: StagnationState
    final_state_correct: bool
    intervention_scored: bool
    intervention_proposed: bool
    intervention_correct: Optional[bool] = None
    supporter_selected: Optional[str] = None
    supporter_correct: Optional[bool] = None
    support_reasons: Optional[str] = None
    sent_only_after_approval: Optional[bool] = None
    approver_id: Optional[str] = None
    support_reply_semantic: Optional[ReplySemantic] = None
    support_reply_correct: Optional[bool] = None
    follow_up_observed: Optional[bool] = None
    resolved_at: Optional[datetime] = None
    resolution_source_ids: list[str] = Field(default_factory=list)
    resolved_before_fix: Optional[bool] = None
    resolved_after_fix_evidence: Optional[bool] = None
    detection_delay_candidate_hours: Optional[float] = None
    detection_delay_confirmed_hours: Optional[float] = None
    status_check_expectations: list[dict] = Field(default_factory=list)

    @property
    def all_correct(self) -> bool:
        flags = [self.block_classification_correct, not self.forbidden_state_violations, self.final_state_correct]
        optional = [self.candidate_correct, self.check_in_correct, self.reply_interpretation_correct,
                    self.block_kind_correct, self.sequence_correct, self.intervention_correct, self.supporter_correct,
                    self.sent_only_after_approval, self.support_reply_correct, self.resolved_after_fix_evidence]
        return all(flags) and all(v is not False for v in optional) and self.resolved_before_fix is not True


class MetricCount(StrictModel):
    correct: int
    total: int


class StagnationEvaluationSummary(StrictModel):
    items: int
    candidate_detection: MetricCount
    check_in: MetricCount
    reply_interpretation: MetricCount
    block_classification: MetricCount
    block_kind: MetricCount
    final_state: MetricCount
    intervention: MetricCount
    support_candidate: MetricCount
    human_in_the_loop: MetricCount
    resolution: MetricCount
    unlabeled_candidates: int
    caveat: str = CAVEAT


# ---------------------------------------------------------------- 환경
def build_environment_root(workdir: Path, *, project_id: str = "P001", data_root: Path | None = None,
                           input_transform: Callable[[dict], dict] | None = None,
                           simulation_transform: Callable[[list], list] | None = None,
                           decisions_transform: Callable[[list], list] | None = None) -> Path:
    """입력·시뮬레이션·사람 결정 데이터를 workdir에 복사한다 (Ground Truth는 복사하지 않는다)."""
    src = data_root or DATA_ROOT
    raw = {k: json.loads((src / "input" / project_id / f).read_text(encoding="utf-8")) for k, f in INPUT_FILES.items()}
    sim_src = src / SIMULATION_DIRNAME / project_id
    sim = json.loads((sim_src / REPLIES_FILE).read_text(encoding="utf-8"))
    decisions = json.loads((sim_src / HUMAN_DECISIONS_FILE).read_text(encoding="utf-8"))
    raw = input_transform(raw) if input_transform else raw
    sim = simulation_transform(sim) if simulation_transform else sim
    decisions = decisions_transform(decisions) if decisions_transform else decisions
    base = workdir / "input" / project_id
    base.mkdir(parents=True, exist_ok=True)
    for k, f in INPUT_FILES.items():
        (base / f).write_text(json.dumps(raw[k], ensure_ascii=False, indent=2), encoding="utf-8")
    out = workdir / SIMULATION_DIRNAME / project_id
    out.mkdir(parents=True, exist_ok=True)
    (out / REPLIES_FILE).write_text(json.dumps(sim, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / HUMAN_DECISIONS_FILE).write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    return workdir


def run_monitoring(workdir: Path | None = None, *, project_id: str = "P001", start: datetime | None = None,
                   until: datetime | None = None, agent_factory: Callable | None = None, use_human: bool = True,
                   **transforms):
    """연속 모니터링 실행 (기본: 프로젝트 시작일 09시 ~ 종료일 21시). 반환: (session, agent, human_simulator)."""
    root = build_environment_root(workdir, project_id=project_id, **transforms) if workdir is not None else None
    if start is None:
        start = datetime.combine(load_project_input(project_id, data_root=root).project.start_date, time(9, 0), KST)
    session = ToolSession(project_id, start, data_root=root)
    if until is None:
        until = datetime.combine(session.snapshot.project.end_date, time(21, 0), KST)
    agent = (agent_factory or (lambda tools: StagnationAgent(tools=tools)))(session.tools)
    human = HumanDecisionSimulator(project_id, root) if use_human else None
    run_stagnation_monitoring(session, agent, until, human)
    return session, agent, human


# ---------------------------------------------------------------- 채점
def _hours(a, b):
    return round((a - b).total_seconds() / 3600, 1) if a and b else None


def evaluate_stagnation(item: GroundTruthStagnation, runs: list[StagnationRun]) -> StagnationEvaluation:
    at = item.evaluation_as_of
    since = item.block_started_at or datetime.min.replace(tzinfo=KST)
    unit = sorted((r for r in runs if r.task_id == item.task_id and r.assignee_id == item.member_id
                   and since <= r.started_at <= at), key=lambda r: r.started_at)
    # 실제 Block 항목은 Block을 확정한 에피소드까지를 채점한다. 그 뒤(해결 후 검토 대기 등)에 다시 열린 후보는
    # Block 처리의 정오가 아니라 추가 질문이므로 runs_after_block_episode로 따로 보고한다.
    after_block = []
    if item.is_actual_block:
        k = next((i for i, r in enumerate(unit) if StagnationState.CONFIRMED_BLOCK in r.state_sequence), None)
        if k is not None:
            unit, after_block = unit[:k + 1], unit[k + 1:]
    transitions = [t for r in unit for t in r.transitions if t.at <= at]
    sequence = [t.to_state for t in transitions]
    first = lambda state: next((t.at for t in transitions if t.to_state == state), None)  # noqa: E731
    check_ins = [c for r in unit for c in r.check_ins if c.sent_at <= at]
    first_check = check_ins[0] if check_ins else None
    semantics = [c.reply_interpretations[0].semantic for c in check_ins if c.reply_interpretations]
    status_expect = [x for x in item.expected_interactive_evidence
                     if x.kind.value == "CHECKIN_REPLY" and x.question_intent and x.question_intent.value == "STATUS_CHECK"]
    support_expect = next((x for x in item.expected_interactive_evidence if x.kind.value == "SUPPORT_REPLY"), None)
    expected_semantic = status_expect[0].expected_semantic_outcome if status_expect else None

    final = unit[-1].state_at(at) if unit else StagnationState.NORMAL
    confirmed = StagnationState.CONFIRMED_BLOCK in sequence
    detected = StagnationState.STAGNATION_CANDIDATE in sequence
    proposed = next((r for r in unit if r.intervention is not None and r.intervention.created_at <= at), None)
    # 외부 의존 Block은 '지원 요청을 하지 않아야 함'을 채점한다
    scored = item.expected_intervention is not None or not item.is_actual_block \
        or item.block_kind == "EXTERNAL_DEPENDENCY"
    # 확인이 꼭 필요한 항목이 아니면, 확인하지 않은 경우 확인·응답 관련 항목은 채점하지 않는다
    check_required = item.candidate_expected is True or bool(check_ins)
    analyses = [r.support_analysis for r in unit if r.support_analysis is not None and r.support_analysis.at <= at]
    agent_kind = analyses[0].block_kind if analyses else None
    result = dict(
        gt_stagnation_id=item.gt_stagnation_id, case_id=item.case_id, task_id=item.task_id, member_id=item.member_id,
        run_ids=[r.run_id for r in unit], state_sequence=sequence,
        runs_after_block_episode=[r.run_id for r in after_block],
        candidate_detected=detected, candidate_expected=item.candidate_expected,
        candidate_correct=None if item.candidate_expected is None else detected == item.candidate_expected,
        first_candidate_at=first(StagnationState.STAGNATION_CANDIDATE),
        check_in_correct=(bool(first_check) and first_check.target_member_id == item.member_id
                          and first_check.task_id == item.task_id
                          and first_check.question_intent.value == "STATUS_CHECK") if check_required else None,
        reply_semantic=semantics[0] if semantics else None, expected_reply_semantic=expected_semantic,
        reply_interpretation_correct=(bool(semantics) and semantics[0] == expected_semantic)
        if expected_semantic is not None and check_required else None,
        confirmed_block=confirmed, confirmed_at=first(StagnationState.CONFIRMED_BLOCK),
        block_classification_correct=confirmed == item.is_actual_block,
        block_kind=agent_kind, expected_block_kind=item.block_kind,
        block_kind_correct=agent_kind == item.block_kind if item.block_kind and agent_kind else None,
        forbidden_state_violations=[s for s in sequence if s in item.forbidden_states],
        sequence_correct=_is_subsequence(item.expected_state_sequence, sequence)
        if item.expected_state_sequence is not None else None,
        final_state=final, final_state_correct=final == item.expected_final_state,
        intervention_scored=scored, intervention_proposed=proposed is not None,
        intervention_correct=(proposed is not None) == (item.expected_intervention is not None) if scored else None,
        detection_delay_candidate_hours=_hours(first(StagnationState.STAGNATION_CANDIDATE), item.block_started_at),
        detection_delay_confirmed_hours=_hours(first(StagnationState.CONFIRMED_BLOCK), item.block_started_at),
        status_check_expectations=[
            {"expected": x.expected_semantic_outcome.value,
             "actual": semantics[i].value if i < len(semantics) else None,
             "note": None if i < len(semantics) else "Agent가 이 시점의 상태 확인을 하지 않음"}
            for i, x in enumerate(status_expect)])
    if proposed is not None:
        action = proposed.intervention
        hist = [h.status for h in action.status_history]
        approval = next((h for h in action.status_history if h.status == ActionStatus.APPROVED), None)
        sent = ActionStatus.SENT in hist
        analysis = proposed.support_analysis
        expected_supporter = item.expected_intervention.supporter_member_id if item.expected_intervention else None
        support_sem = [i.reply_interpretations[0].semantic for i in proposed.support_interactions if i.reply_interpretations]
        result.update(
            supporter_selected=action.recipient_id,
            supporter_correct=action.recipient_id == expected_supporter if expected_supporter else None,
            support_reasons=analysis.reason if analysis else None,
            sent_only_after_approval=(not sent) or (approval is not None and hist.index(ActionStatus.APPROVED)
                                                    < hist.index(ActionStatus.SENT) and approval.changed_by is not None),
            approver_id=approval.changed_by if approval else None,
            support_reply_semantic=support_sem[0] if support_sem else None,
            support_reply_correct=(bool(support_sem) and support_sem[0] == support_expect.expected_semantic_outcome)
            if support_expect and support_expect.expected_semantic_outcome else None,
            follow_up_observed=bool([f for f in proposed.follow_ups if f.at <= at]) if sent else None)
    resolved_at = first(StagnationState.RESOLVED)
    if resolved_at or item.resolved_at:
        resolving = next((f for r in unit for f in r.follow_ups if f.resolved and f.at == resolved_at), None)
        result.update(
            resolved_at=resolved_at, resolution_source_ids=resolving.resolution_source_ids if resolving else [],
            resolved_before_fix=bool(resolved_at and item.resolved_at and resolved_at < item.resolved_at),
            resolved_after_fix_evidence=bool(resolved_at and item.resolved_at and resolved_at >= item.resolved_at
                                             and resolving and resolving.resolution_source_ids))
    return StagnationEvaluation(**result)


def _is_subsequence(expected, actual) -> bool:
    it = iter(actual)
    return all(any(a == e for a in it) for e in expected)


def unlabeled_candidates(runs: list[StagnationRun], gt: GroundTruthBundle) -> list[dict]:
    labeled = {(s.task_id, s.member_id) for s in gt.stagnations}
    return [{"run_id": r.run_id, "task_id": r.task_id, "assignee_id": r.assignee_id,
             "started_at": r.started_at.isoformat(), "states": [s.value for s in r.state_sequence],
             "check_in_status": [c.status.value for c in r.check_ins],
             "closed_by": r.transitions[-1].reason if r.transitions else None}
            for r in runs if (r.task_id, r.assignee_id) not in labeled]


def evaluate_all(gt: GroundTruthBundle, runs: list[StagnationRun]) -> list[StagnationEvaluation]:
    return [evaluate_stagnation(item, runs) for item in gt.stagnations]


def summarize(evals: list[StagnationEvaluation], unlabeled: int = 0) -> StagnationEvaluationSummary:
    def count(values):
        values = [v for v in values if v is not None]
        return MetricCount(correct=sum(bool(v) for v in values), total=len(values))

    return StagnationEvaluationSummary(
        items=len(evals),
        candidate_detection=count(e.candidate_correct for e in evals),
        check_in=count(e.check_in_correct for e in evals),
        reply_interpretation=count(e.reply_interpretation_correct for e in evals),
        block_classification=count(e.block_classification_correct and not e.forbidden_state_violations for e in evals),
        block_kind=count(e.block_kind_correct for e in evals),
        final_state=count(e.final_state_correct for e in evals),
        intervention=count(e.intervention_correct for e in evals),
        support_candidate=count(e.supporter_correct for e in evals),
        human_in_the_loop=count(e.sent_only_after_approval for e in evals),
        resolution=count((e.resolved_after_fix_evidence and not e.resolved_before_fix)
                         if e.resolved_at or e.resolved_after_fix_evidence is not None else None for e in evals),
        unlabeled_candidates=unlabeled)
