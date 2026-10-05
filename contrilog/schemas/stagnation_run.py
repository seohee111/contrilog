"""정체 확인 실행 기록 (StagnationRun).

판단 단위는 (Task, 담당자)다. 사람에게 붙는 라벨은 없고 Task의 상태만 기록한다.
기존 모델을 재사용한다:
- 확인 질문·지원 요청과 응답: InteractionRecord (+ ReplyInterpretation)
- 개입 제안과 사람의 결정: OutboundAction (status_history에 PROPOSED → APPROVED/REJECTED → SENT와 결정한 사람)
- 상태 전이·질문·제안 판단: AgentDecision
- Agent가 호출한 Tool: SearchStep (session의 ToolCallLog에도 자동 기록)

새로 추가한 것은 관찰 신호(TaskSignals), 후보 정책 결과(CandidateCheck), 상태 전이(StateTransition),
지원 후보 분석(SupportAnalysis), 후속 관찰(FollowUpObservation), 시간순 요약(TraceEvent)뿐이다.
점수·순위·사람 특성 필드는 두지 않는다.
"""

from datetime import date
from typing import Literal, Optional

from pydantic import AwareDatetime, Field

from .agent_records import AgentDecision, MemoryContext
from .base import EvidenceSourceId, MemberId, ProjectId, StagnationRunId, StrictModel, TaskId
from .claim_run import InteractionRecord, SearchStep
from .enums import StagnationState, TaskStatus
from .tooling import OutboundAction


class TaskSignals(StrictModel):
    """as_of 시점에 Tool로 관찰한 Task 신호 (판단이 아니라 관찰 사실)."""

    task_id: TaskId
    assignee_id: MemberId
    observed_at: AwareDatetime
    status: TaskStatus
    due_date: date
    hours_until_due_end: float
    hours_since_last_task_activity: Optional[float]
    last_activity_source_id: Optional[EvidenceSourceId]
    recent_revision_ids: list[EvidenceSourceId] = Field(default_factory=list)
    unfinished_dependency_ids: list[TaskId] = Field(default_factory=list)


class CandidateCheck(StrictModel):
    """후보 정책을 적용한 결과. 어떤 조건이 충족됐는지와 그때의 기준값을 함께 남긴다.

    Memory·팀 맥락 보정을 쓰면 기본 정책 값과 보정 후 값을 함께 남긴다 (Memory OFF에서는 보정 필드가 비어 있다).
    """

    observed_at: AwareDatetime
    is_candidate: bool
    conditions: dict[str, bool]
    thresholds: dict[str, float]
    reasons: list[str]
    base_is_candidate: Optional[bool] = None  # 보정 없이 기본 정책만 적용했을 때
    raw_idle_hours: Optional[float] = None
    team_pause_overlap_hours: Optional[float] = None  # 공백 중 팀 전체 휴지기와 겹친 시간
    effective_idle_hours: Optional[float] = None
    base_idle_limit_hours: Optional[float] = None
    memory_adjustment_hours: Optional[float] = None
    effective_idle_limit_hours: Optional[float] = None
    context: Optional[MemoryContext] = None
    applied_memory_ids: list[str] = Field(default_factory=list)
    adjustment_explanation: Optional[str] = None


class StateTransition(StrictModel):
    at: AwareDatetime
    from_state: StagnationState
    to_state: StagnationState
    reason: str
    source_ids: list[EvidenceSourceId] = Field(default_factory=list)
    decision_id: str


class SupportCandidateAssessment(StrictModel):
    """지원 가능성 검토 결과 (사람 점수가 아니라 근거 기록과 현재 업무 상태)."""

    member_id: MemberId
    related_source_ids: list[EvidenceSourceId] = Field(default_factory=list)  # 막힌 문제와 관련된 과거 기록
    best_related_source_id: Optional[EvidenceSourceId] = None  # 문제와 가장 관련 깊은 기록
    prior_help_source_ids: list[EvidenceSourceId] = Field(default_factory=list)  # 이 담당자의 문제를 도운 기록
    open_task_ids: list[TaskId] = Field(default_factory=list)
    urgent_task_ids: list[TaskId] = Field(default_factory=list)  # 곧 마감인 본인 업무
    available: bool
    eligible: bool
    notes: list[str] = Field(default_factory=list)


class SupportAnalysis(StrictModel):
    at: AwareDatetime
    block_kind: Literal["INTERNAL_ISSUE", "EXTERNAL_DEPENDENCY"]
    context_source_ids: list[EvidenceSourceId] = Field(default_factory=list)  # 문제 맥락으로 쓴 기록
    context_terms: list[str] = Field(default_factory=list)
    candidates: list[SupportCandidateAssessment] = Field(default_factory=list)
    selected_member_id: Optional[MemberId] = None
    reason: str


class FollowUpObservation(StrictModel):
    at: AwareDatetime
    reference_at: AwareDatetime  # 이 시각 이후의 기록만 후속 근거로 본다 (지원 전송 또는 Block 확정 시각)
    new_source_ids: list[EvidenceSourceId] = Field(default_factory=list)
    resolution_source_ids: list[EvidenceSourceId] = Field(default_factory=list)
    resolved: bool
    note: str


TraceKind = Literal["OBSERVE", "CHECK_IN", "REPLY", "DECISION", "SUPPORT_ANALYSIS", "INTERVENTION", "HUMAN",
                    "ACTION", "SUPPORT_RESPONSE", "FOLLOW_UP"]


class TraceEvent(StrictModel):
    at: AwareDatetime
    kind: TraceKind
    summary: str
    source_ids: list[str] = Field(default_factory=list)


class StagnationRun(StrictModel):
    run_id: StagnationRunId
    project_id: ProjectId
    task_id: TaskId
    assignee_id: MemberId
    started_at: AwareDatetime
    as_of: AwareDatetime
    initial_state: StagnationState
    observed_signals: list[TaskSignals] = Field(default_factory=list)
    candidate_checks: list[CandidateCheck] = Field(default_factory=list)
    transitions: list[StateTransition] = Field(default_factory=list)
    check_ins: list[InteractionRecord] = Field(default_factory=list)
    confirmed_state: Optional[StagnationState] = None  # 확인 질문 이후 상태 (NORMAL / CONFIRMED_BLOCK)
    support_analysis: Optional[SupportAnalysis] = None
    intervention: Optional[OutboundAction] = None
    support_interactions: list[InteractionRecord] = Field(default_factory=list)
    follow_ups: list[FollowUpObservation] = Field(default_factory=list)
    final_state: StagnationState
    decisions: list[AgentDecision] = Field(default_factory=list)
    tool_trace: list[SearchStep] = Field(default_factory=list)
    timeline: list[TraceEvent] = Field(default_factory=list)

    @property
    def state_sequence(self) -> list[StagnationState]:
        return [self.initial_state] + [t.to_state for t in self.transitions]

    def state_at(self, at) -> StagnationState:
        state = self.initial_state
        for t in self.transitions:
            if t.at <= at:
                state = t.to_state
        return state


class PolicyApplication(StrictModel):
    """보정이 판단을 바꾼 정기 확인 기록 (후보가 되지 않아 에피소드가 없는 경우도 남긴다)."""

    task_id: TaskId  # 추적용
    check: CandidateCheck
    decision: AgentDecision
