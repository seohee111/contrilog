"""Feedback-aware 정책과 Memory 작성기.

FeedbackSettings(use_team_context, use_memory)로 켜고 끈다. 둘 다 끄면 기본 StagnationPolicy와 같다.
- use_team_context: 팀 전체 휴지기와 겹친 공백을 빼고 판단한다 (데이터에서 바로 계산하는 맥락 신호, 학습 아님)
- use_memory: 같은 상황의 과거 피드백으로 허용 공백을 bounded하게 완화·복원한다 (학습)

Memory는 Agent가 실제로 관찰한 결과로만 만든다 (Ground Truth를 보지 않는다).
Memory 본문·검색 키에는 사람 식별 정보가 없다.
"""

from dataclasses import dataclass, field

from contrilog.memory import AdjustmentBounds, MemoryRetriever, compute_adjustment
from contrilog.schemas import (
    AgentMemory,
    CandidateCheck,
    DecisionOutcome,
    DecisionType,
    FeedbackLabel,
    MemoryContext,
    StagnationState,
    TaskSignals,
)

from .context import ContextThresholds, TeamContext, candidate_context
from .policy import StagnationPolicy


@dataclass
class FeedbackSettings:
    use_team_context: bool = True
    use_memory: bool = True
    store: object = None  # contrilog.memory.MemoryStore
    bounds: AdjustmentBounds = field(default_factory=AdjustmentBounds)
    context_thresholds: ContextThresholds = field(default_factory=ContextThresholds)


class FeedbackAwarePolicy:
    def __init__(self, base: StagnationPolicy, settings: FeedbackSettings):
        self.base = base
        self.settings = settings
        self.retriever = MemoryRetriever(settings.store) if settings.use_memory else None

    def check(self, signals: TaskSignals, trusted_until, last_asked_at, team: TeamContext | None,
              last_activity_at) -> CandidateCheck:
        base = self.base.check(signals, trusted_until, last_asked_at)
        raw = signals.hours_since_last_task_activity
        overlap = 0.0
        if self.settings.use_team_context and team is not None and raw is not None and last_activity_at is not None:
            overlap = team.overlap_hours(last_activity_at, signals.observed_at)
        effective = None if raw is None else max(0.0, raw - overlap)
        context = candidate_context(signals.hours_until_due_end, effective, signals.status.value,
                                    team if self.settings.use_team_context else None)
        base_limit = self.base.thresholds.idle_limit_hours(signals.hours_until_due_end)
        adjustment_hours, applied, explanation = 0.0, [], "Memory 미사용"
        if self.retriever is not None:
            adj = compute_adjustment(self.retriever.retrieve(context, signals.observed_at),
                                     signals.hours_until_due_end, self.settings.bounds)
            adjustment_hours, applied, explanation = adj.hours, adj.applied_memory_ids, adj.explanation
        limit = base_limit + adjustment_hours
        conditions = dict(base.conditions)
        conditions["idle_beyond_limit"] = effective is not None and effective >= limit
        reasons = list(base.reasons)
        if overlap:
            reasons.append(f"공백 중 팀 전체 휴지기 {overlap:.1f}시간 제외 → 실질 공백 {effective:.1f}시간")
        if adjustment_hours:
            reasons.append(f"Memory 보정 +{adjustment_hours:.0f}h → 허용 {limit:.1f}시간 ({', '.join(applied)})")
        return CandidateCheck(
            observed_at=signals.observed_at, is_candidate=all(conditions.values()), conditions=conditions,
            thresholds={**base.thresholds, "effective_idle_limit_hours": limit}, reasons=reasons,
            base_is_candidate=base.is_candidate, raw_idle_hours=raw, team_pause_overlap_hours=overlap,
            effective_idle_hours=effective, base_idle_limit_hours=base_limit, memory_adjustment_hours=adjustment_hours,
            effective_idle_limit_hours=limit, context=context, applied_memory_ids=applied,
            adjustment_explanation=explanation)


LESSONS = {
    FeedbackLabel.TRUE_POSITIVE: "이 상황의 후보 판단은 실제 막힘 확인으로 이어졌다. 이 상황에서는 기본 기준을 유지한다.",
    FeedbackLabel.FALSE_POSITIVE: "이 상황의 후보 판단은 확인 결과 정상 진행이었다. 같은 상황에서는 허용 공백을 소폭 늘릴 근거가 된다.",
    FeedbackLabel.UNRESOLVED: "이 상황의 후보 판단은 실제 상태를 확인하지 못한 채 끝났다.",
    FeedbackLabel.RESOLUTION_SUCCESS: "이 근거 종류로 선정한 지원 요청 이후 실제 해결 근거가 관찰되었다.",
}
OUTCOME = {FeedbackLabel.TRUE_POSITIVE: DecisionOutcome.CORRECT, FeedbackLabel.FALSE_POSITIVE: DecisionOutcome.FALSE_POSITIVE,
           FeedbackLabel.UNRESOLVED: DecisionOutcome.UNKNOWN, FeedbackLabel.RESOLUTION_SUCCESS: DecisionOutcome.CORRECT}
DIRECTION = {FeedbackLabel.TRUE_POSITIVE: "RESTORE", FeedbackLabel.FALSE_POSITIVE: "RELAX",
             FeedbackLabel.UNRESOLVED: "NONE", FeedbackLabel.RESOLUTION_SUCCESS: "NONE"}


def describe(context: MemoryContext) -> str:
    if context.kind == "INTERVENTION":
        return f"개입: Block 종류 {context.block_kind}, 지원자 선정 근거 {'+'.join(context.selection_basis)}"
    return (f"후보: 마감 {context.deadline_bucket}, 공백/남은 시간 {context.idle_ratio_bucket}, "
            f"Task {context.task_status}, 팀 {context.team_context or '미사용'}")


def make_memory(store, *, project_id, created_at, label: FeedbackLabel, context: MemoryContext, decision_ids,
                observed_signal: str, judgment: str, evidence_ids, decision_type=DecisionType.STAGNATION_ASSESSMENT,
                previous=StagnationState.STAGNATION_CANDIDATE) -> AgentMemory:
    memory = AgentMemory(
        memory_id=store.next_id(), project_id=project_id, created_at=created_at,
        source_decision_ids=list(decision_ids), decision_type=decision_type, signal_pattern=describe(context),
        agent_judgment=judgment, observed_outcome=OUTCOME[label], lesson=LESSONS[label], feedback_label=label,
        context=context, previous_decision=previous, observed_signal=observed_signal,
        policy_adjustment=DIRECTION[label], evidence_ids=[e for e in dict.fromkeys(evidence_ids) if e])
    return store.append(memory)
