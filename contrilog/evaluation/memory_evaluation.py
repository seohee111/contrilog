"""Memory + Feedback 평가 (평가 계층 전용).

같은 프로젝트를 여러 모드로 처음부터 시간순 재생해 비교한다 (Memory는 빈 저장소에서 시작해 재생 중에만 쌓인다).
  OFF            : 기존 StagnationPolicy
  CONTEXT_ONLY   : 팀 전체 휴지기 맥락만 (학습 아님)
  MEMORY_ONLY    : 과거 피드백 Memory 보정만
  ON             : 맥락 + Memory
  ON_WEAK_UNRESOLVED : ON + UNRESOLVED(활동 재개)를 약한 근거로 쓰는 변형 (비교용)

FALSE_NEGATIVE(관찰하지 않은 실제 Block)는 Ground Truth로만 계산한다 — Agent Memory는 만들지 않는다.
주의: synthetic 프로젝트 하나의 재생 결과다. 개수 비교는 회귀 확인용이며 일반 성능으로 해석하지 않는다.
"""

import json
import re
from dataclasses import replace
from typing import Optional

from pydantic import Field

from contrilog.agent.stagnation import FeedbackSettings, StagnationAgent
from contrilog.memory import AdjustmentBounds, InMemoryMemoryStore
from contrilog.schemas import AgentMemory, FeedbackLabel, ReplySemantic, StagnationRun, StagnationState
from contrilog.schemas.base import StrictModel
from contrilog.schemas.ground_truth import GroundTruthBundle

from .stagnation_evaluation import evaluate_all, run_monitoring

CAVEAT = "synthetic 프로젝트 하나의 시간순 재생 비교다. 개수 차이는 회귀 확인용이며 일반 성능으로 해석하지 않는다."
MODES = {
    "OFF": None,
    "CONTEXT_ONLY": dict(use_team_context=True, use_memory=False),
    "MEMORY_ONLY": dict(use_team_context=False, use_memory=True),
    "ON": dict(use_team_context=True, use_memory=True),
    "ON_WEAK_UNRESOLVED": dict(use_team_context=True, use_memory=True,
                               bounds=replace(AdjustmentBounds(), weak_unresolved_weight=0.5)),
}


class ModeMetrics(StrictModel):
    mode: str
    candidates: int
    status_checks: int
    true_positive: int  # 후보 → 막힘 응답
    false_positive: int  # 후보 → 정상 진행 응답
    unresolved: int  # 후보 → 상태 확인 못 하고 종료
    still_open: int
    confirmed_blocks: int
    gt_blocks_detected: list[str]
    false_negatives: list[str]  # Ground Truth 기준 (평가 계층 전용)
    non_block_correct: dict[str, bool]  # Block이 아닌 Ground Truth 항목(gt_stagnation_id)별 전체 정답 여부
    resolved_correct: dict[str, bool]  # RESOLVED가 기대된 항목별 최종 상태 RESOLVED 여부
    detection_delay_candidate_hours: dict[str, Optional[float]]
    detection_delay_confirmed_hours: dict[str, Optional[float]]
    memories: int
    memory_labels: dict[str, int]
    adjusted_checks: int  # Memory 보정이 0이 아니었던 판단 수
    suppressed_by_adjustment: int  # 기본 정책이면 후보였으나 보정으로 정상 처리된 판단 수


class MemoryChecks(StrictModel):
    memory_created_correctly: bool
    no_person_profile: bool
    no_future_memory: bool
    applied_memory_traceable: bool
    bounded_adjustment: bool
    false_positive_change: int
    question_count_change: int
    true_positive_preserved: bool
    detection_delay_change: dict[str, Optional[float]]
    problems: list[str] = Field(default_factory=list)


def outcome_of(run: StagnationRun) -> str:
    semantics = [i.reply_interpretations[0].semantic for i in run.check_ins if i.reply_interpretations]
    if ReplySemantic.REPORTS_BLOCKED in semantics:
        return "TRUE_POSITIVE"
    if ReplySemantic.REPORTS_ON_TRACK in semantics or ReplySemantic.CONFIRMS_COMPLETION in semantics:
        return "FALSE_POSITIVE"
    return "UNRESOLVED" if run.final_state != StagnationState.STAGNATION_CANDIDATE else "OPEN"


def run_mode(mode: str, workdir=None, store=None, **kwargs):
    """kwargs는 run_monitoring으로 전달된다 (project_id, 데이터 변형 등)."""
    cfg = MODES[mode]
    store = store if store is not None else InMemoryMemoryStore()
    feedback = None if cfg is None else FeedbackSettings(store=store, **cfg)
    session, agent, human = run_monitoring(
        workdir, agent_factory=lambda tools: StagnationAgent(tools=tools, feedback=feedback), **kwargs)
    return session, agent, store


def mode_metrics(mode: str, agent, store, gt: GroundTruthBundle) -> ModeMetrics:
    runs = agent.runs()
    outcomes = [outcome_of(r) for r in runs]
    evals = {e.gt_stagnation_id: e for e in evaluate_all(gt, runs)}
    blocks = [s for s in gt.stagnations if s.is_actual_block]
    detected = [s.case_id for s in blocks if evals[s.gt_stagnation_id].confirmed_block]
    memories = store.all() if store is not None else []
    checks = [c for r in runs for c in r.candidate_checks] + [p.check for p in agent.policy_applications()]
    return ModeMetrics(
        mode=mode, candidates=len(runs), status_checks=sum(len(r.check_ins) for r in runs),
        true_positive=outcomes.count("TRUE_POSITIVE"), false_positive=outcomes.count("FALSE_POSITIVE"),
        unresolved=outcomes.count("UNRESOLVED"), still_open=outcomes.count("OPEN"),
        confirmed_blocks=sum(StagnationState.CONFIRMED_BLOCK in r.state_sequence for r in runs),
        gt_blocks_detected=detected, false_negatives=[s.case_id for s in blocks if s.case_id not in detected],
        non_block_correct={s.gt_stagnation_id: evals[s.gt_stagnation_id].all_correct
                           for s in gt.stagnations if not s.is_actual_block},
        resolved_correct={s.gt_stagnation_id: evals[s.gt_stagnation_id].final_state == StagnationState.RESOLVED
                          for s in gt.stagnations if s.expected_final_state == StagnationState.RESOLVED},
        detection_delay_candidate_hours={s.case_id: evals[s.gt_stagnation_id].detection_delay_candidate_hours
                                         for s in blocks},
        detection_delay_confirmed_hours={s.case_id: evals[s.gt_stagnation_id].detection_delay_confirmed_hours
                                         for s in blocks},
        memories=len(memories),
        memory_labels={label.value: sum(m.feedback_label == label for m in memories) for label in FeedbackLabel},
        adjusted_checks=sum(bool(c.memory_adjustment_hours) for c in checks),
        suppressed_by_adjustment=sum(1 for p in agent.policy_applications()
                                     if p.check.base_is_candidate and not p.check.is_candidate))


PERSON_FIELDS = ("member", "assignee", "person", "name", "score", "reliab", "diligen", "productiv", "risk", "blocker")


def memory_checks(agent, store, gt, members, off: ModeMetrics, on: ModeMetrics, bounds=None) -> MemoryChecks:
    bounds = bounds or AdjustmentBounds()
    problems = []
    memories = {m.memory_id: m for m in store.all()}
    runs = agent.runs()
    # 1) 각 Memory는 Agent가 관찰한 그 에피소드의 결과와 맞아야 한다
    by_decision = {d.decision_id: r for r in runs for d in r.decisions}
    for m in memories.values():
        run = next((by_decision[d] for d in m.source_decision_ids if d in by_decision), None)
        if run is None:
            problems.append(f"{m.memory_id}: source decision not found")
            continue
        expected = outcome_of(run) if m.feedback_label != FeedbackLabel.RESOLUTION_SUCCESS else "RESOLUTION_SUCCESS"
        if m.feedback_label != FeedbackLabel.RESOLUTION_SUCCESS and expected != m.feedback_label.value:
            problems.append(f"{m.memory_id}: label {m.feedback_label.value} != observed {expected}")
        if m.feedback_label == FeedbackLabel.RESOLUTION_SUCCESS and not (
                run.final_state == StagnationState.RESOLVED and run.intervention is not None):
            problems.append(f"{m.memory_id}: RESOLUTION_SUCCESS without resolved intervention")
    created_ok = not [p for p in problems if "label" in p or "RESOLUTION" in p or "source" in p]
    # 2) 사람 정보 없음
    text = json.dumps([m.model_dump(mode="json") for m in memories.values()], ensure_ascii=False)
    ids = [m.member_id for m in members if re.search(rf"\b{re.escape(m.member_id)}\b", text)]
    names = [n for m in members for n in {m.name, m.name[1:] if len(m.name) >= 3 else m.name} if n in text]
    leaked = ids + names
    fields = [f for f in list(AgentMemory.model_fields) + list(type(next(iter(memories.values())).context).model_fields)
              if any(w in f for w in PERSON_FIELDS)] if memories else []
    if leaked or fields:
        problems.append(f"person info in memory: {leaked} {fields}")
    # 3) 미래 Memory 미사용, 4) 추적 가능
    checks = [c for r in runs for c in r.candidate_checks] + [p.check for p in agent.policy_applications()]
    future = [(c.observed_at, mid) for c in checks for mid in c.applied_memory_ids
              if mid not in memories or memories[mid].created_at >= c.observed_at]
    if future:
        problems.append(f"future or unknown memory applied: {future[:3]}")
    decisions = [d for r in runs for d in r.decisions] + [p.decision for p in agent.policy_applications()]
    untraceable = [d.decision_id for d in decisions for mid in d.applied_memory_ids if mid not in memories]
    for p in agent.policy_applications():
        if p.decision.applied_memory_ids != p.check.applied_memory_ids:
            untraceable.append(p.decision.decision_id)
    if untraceable:
        problems.append(f"untraceable applied memories: {untraceable[:3]}")
    # 5) 보정 범위
    bad = [c.memory_adjustment_hours for c in checks if c.memory_adjustment_hours is not None and not (
        bounds.min_relax_hours <= c.memory_adjustment_hours <= bounds.max_relax_hours
        and c.memory_adjustment_hours % bounds.step_hours == 0)]
    if bad:
        problems.append(f"adjustment out of bounds: {bad[:3]}")
    return MemoryChecks(
        memory_created_correctly=created_ok, no_person_profile=not leaked and not fields, no_future_memory=not future,
        applied_memory_traceable=not untraceable, bounded_adjustment=not bad,
        false_positive_change=on.false_positive - off.false_positive,
        question_count_change=on.status_checks - off.status_checks,
        true_positive_preserved=set(off.gt_blocks_detected) <= set(on.gt_blocks_detected),
        detection_delay_change={k: (None if on.detection_delay_candidate_hours.get(k) is None
                                    or off.detection_delay_candidate_hours.get(k) is None
                                    else round(on.detection_delay_candidate_hours[k]
                                               - off.detection_delay_candidate_hours[k], 1))
                                for k in off.detection_delay_candidate_hours},
        problems=problems)
