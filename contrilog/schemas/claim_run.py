"""Claim 검증 실행 기록 (ClaimVerificationRun).

기존 모델을 재사용한다.
- atomic claim: ContributionClaim (parent_claim_id + claimed_type)
- 판단 근거: ContributionEvidence (claim_id = atomic claim ID)
- atomic claim별 판단: AgentDecision (decision_type = CLAIM_VERIFICATION)

새로 추가한 것은 실행 단위를 묶는 ClaimVerificationRun, Agent가 수행한 검색 단계 SearchStep,
평가 계층이 Ground Truth와 비교하기 쉬운 machine-readable 요약 AtomicClaimResult뿐이다.

Interactive Verification(4단계)에서 추가된 실행 trace:
- VerificationGap: PENDING의 구조화된 이유와, 확인 행동으로 해결 가능한지
- InteractionRecord: Agent가 보낸 확인 질문(CheckInTool)과 받은 응답(RPL-*)
- VerificationRound: 관찰 → 판정 → (행동) 단위의 스냅샷. 최초 판정과 재판정을 순서대로 남긴다.
trace에는 Agent가 Tool로 관찰한 정보와 Agent 자신의 판단만 들어간다 (Ground Truth·접근 불가 기록 없음).

rationale은 사람에 대한 평가가 아니라 'Evidence와 판단 사이의 설명'이다.
점수·순위·활동량 비교 필드는 두지 않는다.
"""

from typing import Any, Literal, Optional

from pydantic import AwareDatetime, Field, model_validator

from .agent_records import AgentDecision
from .base import (
    ActionId,
    ClaimId,
    ClaimRunId,
    EvidenceId,
    EvidenceSourceId,
    MemberId,
    ProjectId,
    ReplyId,
    StrictModel,
    TaskId,
)
from .contribution import ContributionClaim, ContributionEvidence
from .enums import (
    ClaimStatus,
    Confidence,
    ContributionType,
    EvidenceRelation,
    InteractionStatus,
    QuestionIntent,
    ReplySemantic,
    VerificationGapKind,
)


class SearchStep(StrictModel):
    step: int = Field(ge=1)
    atomic_claim_id: Optional[ClaimId] = None  # None = 실행 공통 단계 (예: 용어 통계용 조회)
    tool_name: str
    operation: str
    parameters: dict[str, Any]
    purpose: str
    returned_source_ids: list[str] = Field(default_factory=list)
    result_count: int = Field(default=0, ge=0)


class AtomicClaimResult(StrictModel):
    """평가용 요약: atomic claim 하나에 대한 예측."""

    atomic_claim_id: ClaimId
    parent_claim_id: ClaimId
    claimant_id: MemberId
    text: str
    predicted_contribution_type: ContributionType
    predicted_status: ClaimStatus
    supporting_source_ids: list[EvidenceSourceId] = Field(default_factory=list)
    contradicting_source_ids: list[EvidenceSourceId] = Field(default_factory=list)
    context_source_ids: list[EvidenceSourceId] = Field(default_factory=list)
    used_evidence_ids: list[EvidenceId] = Field(default_factory=list)
    confidence: Confidence
    rationale: str
    unresolved_questions: list[str] = Field(default_factory=list)


class VerificationGap(StrictModel):
    atomic_claim_id: ClaimId
    kind: VerificationGapKind
    description: str  # 확인이 필요한 사실 하나
    basis_source_ids: list[EvidenceSourceId] = Field(default_factory=list)  # 이 gap을 만든 근거
    resolvable: bool  # Agent가 쓸 수 있는 Tool 행동으로 해결을 시도할 수 있는가
    action_id: Optional[ActionId] = None  # 시도한 확인 행동
    unresolvable_reason: Optional[str] = None


class ReplyInterpretation(StrictModel):
    """Agent가 확인 응답 하나를 어떻게 해석했는가 (가장 최근 라운드 기준)."""

    reply_id: ReplyId
    round: int = Field(ge=1)
    role: str  # EvidenceEvaluator가 부여한 근거 역할
    relation: EvidenceRelation
    semantic: ReplySemantic


class InteractionRecord(StrictModel):
    """Agent가 사람에게 보낸 행동(확인 질문·지원 요청)과 받은 응답.

    Claim 검증에서는 atomic_claim_id·gap_kind·question_intent가 항상 채워진다.
    정체 확인(StagnationRun)에서는 atomic claim이 없고, 지원 요청(SupportRequestTool)에는 question_intent가 없다.
    """

    action_id: ActionId
    atomic_claim_id: Optional[ClaimId] = None
    gap_kind: Optional[VerificationGapKind] = None  # 왜 물었는가 (Claim 검증: PENDING의 이유)
    question_intent: Optional[QuestionIntent] = None  # 무엇을 확인하려 했는가 (구조화된 의미)
    tool_name: str
    operation: str
    target_member_id: MemberId
    task_id: TaskId
    question: str  # 사람에게 보여 준 문장 (의미는 question_intent)
    target_reason: str  # 왜 이 사람에게, 이 Task로 물었는가 (근거 ID 포함)
    sent_at: AwareDatetime
    status: InteractionStatus
    reply_ids: list[ReplyId] = Field(default_factory=list)
    reply_interpretations: list[ReplyInterpretation] = Field(default_factory=list)
    last_checked_at: Optional[AwareDatetime] = None


class RoundEvidence(StrictModel):
    source_id: EvidenceSourceId
    relation: EvidenceRelation
    role: str
    attributed_member_id: MemberId


class AtomicRoundState(StrictModel):
    atomic_claim_id: ClaimId
    status: ClaimStatus
    confidence: Confidence
    evidence: list[RoundEvidence] = Field(default_factory=list)
    gap_kinds: list[VerificationGapKind] = Field(default_factory=list)


class VerificationRound(StrictModel):
    round: int = Field(ge=1)
    phase: Literal["INITIAL", "REEVALUATION", "FINAL"]
    as_of: AwareDatetime
    trigger: str  # 이 라운드를 시작한 관찰 (예: 최초 검증, 응답 수신, 대기 종료)
    new_reply_ids: list[ReplyId] = Field(default_factory=list)
    atomic_states: list[AtomicRoundState]
    gaps: list[VerificationGap] = Field(default_factory=list)
    action_ids: list[ActionId] = Field(default_factory=list)  # 이 라운드에서 새로 보낸 확인 행동


class ClaimVerificationRun(StrictModel):
    run_id: ClaimRunId
    project_id: ProjectId
    submitted_claim_id: ClaimId
    claimant_id: MemberId
    as_of: AwareDatetime
    atomic_claims: list[ContributionClaim]
    search_steps: list[SearchStep]
    evidence: list[ContributionEvidence]
    decisions: list[AgentDecision]
    atomic_results: list[AtomicClaimResult]
    overall_status: ClaimStatus  # atomic 판단을 묶은 요약. 판단의 단위는 atomic_results
    rationale: str
    confidence: Confidence
    unresolved_questions: list[str] = Field(default_factory=list)
    rounds: list[VerificationRound] = Field(default_factory=list)
    interactions: list[InteractionRecord] = Field(default_factory=list)

    @property
    def awaiting_action_ids(self) -> list[str]:
        return [i.action_id for i in self.interactions if i.status == InteractionStatus.AWAITING_REPLY]

    @model_validator(mode="after")
    def _check_links(self):
        atomic_ids = {c.claim_id for c in self.atomic_claims}
        for c in self.atomic_claims:
            if c.parent_claim_id != self.submitted_claim_id:
                raise ValueError(f"{c.claim_id} is not derived from {self.submitted_claim_id}")
        evidence_ids = {e.evidence_id for e in self.evidence}
        for e in self.evidence:
            if e.claim_id not in atomic_ids:
                raise ValueError(f"{e.evidence_id} is not linked to an atomic claim of this run")
        for d in self.decisions:
            if d.claim_id not in atomic_ids or not set(d.evidence_ids) <= evidence_ids:
                raise ValueError(f"{d.decision_id} references unknown atomic claim or evidence")
            if d.as_of > self.as_of:
                raise ValueError("decision as_of must not be after run as_of")
        if {r.atomic_claim_id for r in self.atomic_results} != atomic_ids:
            raise ValueError("atomic_results must cover every atomic claim")
        for e in self.evidence:
            if e.collected_at > self.as_of:
                raise ValueError("evidence cannot be collected after as_of")
        times = [r.as_of for r in self.rounds]
        if times != sorted(times) or (times and times[-1] > self.as_of):
            raise ValueError("rounds must be chronological and not after run as_of")
        action_ids = {i.action_id for i in self.interactions}
        for r in self.rounds:
            if not set(r.action_ids) <= action_ids:
                raise ValueError("round references an unknown interaction")
        for i in self.interactions:
            if i.atomic_claim_id not in atomic_ids or i.sent_at > self.as_of:
                raise ValueError(f"invalid interaction {i.action_id}")
        return self
