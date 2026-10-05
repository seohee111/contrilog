"""AgentDecision / AgentMemory.

AgentMemory는 사람을 평가하기 위한 저장소가 아니라 Agent 자신의 과거 판단과 그 결과를
기록해 이후 판단을 보정하기 위한 것이다. 그래서 AgentMemory에는 member_id 같은
사람 식별 필드를 두지 않고, '어떤 신호 패턴에서 어떤 판단을 했고 결과가 어땠는지'만 남긴다.

Memory의 검색·보정 키는 MemoryContext(상황 구간)뿐이다. evidence_ids에는 재현·추적을 위한 원본 기록·Task ID가
들어갈 수 있지만 검색 키로 쓰지 않는다.
"""

from typing import Literal, Optional

from pydantic import AwareDatetime, Field, model_validator

from .base import (
    EvidenceSourceId,
    ClaimId,
    DecisionId,
    EvidenceId,
    EvidenceSourceId,
    MemberId,
    MemoryId,
    ProjectId,
    StrictModel,
    TaskId,
)
from .enums import (
    ClaimStatus,
    Confidence,
    ContributionType,
    DecisionOutcome,
    DecisionType,
    FeedbackLabel,
    InterventionType,
    StagnationState,
)


class AgentDecision(StrictModel):
    decision_id: DecisionId
    project_id: ProjectId
    decision_type: DecisionType
    as_of: AwareDatetime  # Agent가 이 시각까지의 데이터만 보고 판단했음을 의미
    created_at: AwareDatetime
    subject_member_id: Optional[MemberId] = None
    task_id: Optional[TaskId] = None
    claim_id: Optional[ClaimId] = None

    contribution_type: Optional[ContributionType] = None
    claim_status: Optional[ClaimStatus] = None
    previous_stagnation_state: Optional[StagnationState] = None
    stagnation_state: Optional[StagnationState] = None

    intervention_type: Optional[InterventionType] = None
    supporter_member_id: Optional[MemberId] = None

    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    source_ids: list[EvidenceSourceId] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    confidence: Confidence
    previous_decision_id: Optional[DecisionId] = None
    applied_memory_ids: list[MemoryId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields_by_type(self):
        t = self.decision_type
        if t == DecisionType.CLAIM_VERIFICATION and (self.claim_id is None or self.claim_status is None):
            raise ValueError("CLAIM_VERIFICATION requires claim_id and claim_status")
        if t == DecisionType.CONTRIBUTION_ATTRIBUTION and (
            self.subject_member_id is None or self.contribution_type is None
        ):
            raise ValueError("CONTRIBUTION_ATTRIBUTION requires subject_member_id and contribution_type")
        if t == DecisionType.STAGNATION_ASSESSMENT and (
            self.subject_member_id is None or self.task_id is None or self.stagnation_state is None
        ):
            raise ValueError("STAGNATION_ASSESSMENT requires subject_member_id, task_id, stagnation_state")
        if t == DecisionType.INTERVENTION_PROPOSAL and self.intervention_type is None:
            raise ValueError("INTERVENTION_PROPOSAL requires intervention_type")
        if self.created_at < self.as_of:
            raise ValueError("created_at must not be earlier than as_of")
        return self


class MemoryContext(StrictModel):
    """판단 당시의 상황 구간. 사람·Task 식별자가 없다 (같은 상황이면 누구의 Task든 같은 키)."""

    kind: Literal["CANDIDATE", "INTERVENTION"]
    deadline_bucket: Optional[Literal["OVERDUE", "DUE_LE_48H", "DUE_48_96H", "DUE_96_168H", "DUE_GT_168H"]] = None
    idle_ratio_bucket: Optional[Literal["LT_0_5", "0_5_TO_1", "GE_1"]] = None  # 공백 / 남은 시간
    task_status: Optional[str] = None
    team_context: Optional[Literal["TEAM_ACTIVE", "TEAM_WIDE_LOW_ACTIVITY"]] = None
    block_kind: Optional[str] = None  # 개입 Memory: INTERNAL_ISSUE / EXTERNAL_DEPENDENCY
    selection_basis: list[str] = Field(default_factory=list)  # 개입 Memory: 지원자 선정에 쓴 근거 종류

    def key(self) -> tuple:
        return (self.kind, self.deadline_bucket, self.idle_ratio_bucket, self.task_status, self.team_context,
                self.block_kind, tuple(self.selection_basis))


class AgentMemory(StrictModel):
    memory_id: MemoryId
    project_id: ProjectId
    created_at: AwareDatetime
    source_decision_ids: list[DecisionId] = Field(min_length=1)
    decision_type: DecisionType
    signal_pattern: str  # 판단 당시 관찰한 신호 (예: "Task 관련 리비전 7일 이상 없음, 다른 채널 활동도 없음")
    agent_judgment: str  # 당시 Agent의 판단
    observed_outcome: DecisionOutcome
    lesson: str  # 이후 판단을 보정하기 위한 Agent 자신에 대한 교훈
    # ---- 5단계 확장 (모두 선택 항목: 이전 Memory와 호환)
    feedback_label: Optional[FeedbackLabel] = None
    context: Optional[MemoryContext] = None
    previous_decision: Optional[StagnationState] = None  # 피드백 대상이 된 Agent 판단 (예: STAGNATION_CANDIDATE)
    observed_signal: Optional[str] = None  # 관찰된 결과 (예: REPORTS_ON_TRACK, ACTIVITY_RESUMED_WITHOUT_REPLY)
    policy_adjustment: Optional[Literal["RELAX", "RESTORE", "NONE"]] = None  # 이 피드백이 정책에 주는 방향
    evidence_ids: list[EvidenceSourceId] = Field(default_factory=list)  # 추적용 (검색 키 아님)
