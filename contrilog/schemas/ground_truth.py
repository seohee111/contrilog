"""평가용 Ground Truth schema.

!! Agent 코드(contrilog.agent / tools / memory / data_access / simulation)는 이 모듈을
!! import 하면 안 된다. tests/test_isolation.py가 이를 검사한다.
!! contrilog.schemas 패키지의 __init__에서도 일부러 re-export 하지 않는다.

Evidence 기대값은 세 종류로 나뉜다.

A. static evidence (expected_*evidence_ids)
   실행 전에 Agent-facing Tool로 검색할 수 있는 공개 원본 기록 ID
   (발언 UT-*, 리비전 REV-*, Task T*, 공유 채널 메시지 MSG-*).
   Agent가 만든 Evidence ID(EV-*)가 아니므로 실행마다 달라지지 않는다.
B. interactive evidence (expected_interactive_evidence)
   Agent가 check-in / 지원 요청을 한 뒤에만 얻을 수 있는 응답(RPL-*).
   RPL 번호는 실행마다 달라지므로 ID 대신 의미(종류, Task, 응답자)로 기대값을 표현한다.
   질문 의도(question_intent)와 기대 응답 의미(expected_semantic_outcome)도 함께 표현한다.
C. inaccessible sources (inaccessible_source_ids)
   사건과 관련은 있지만 Agent 접근 정책상 볼 수 없는 기록(개인 DM).
   기대 evidence가 아니며, Agent 출력에 나타나면 정책 위반으로 평가한다.
"""

import re
from enum import Enum
from typing import Literal, Optional

from pydantic import AwareDatetime, Field, model_validator

from .base import ClaimId, MemberId, ProjectId, SimulatedReplyId, SourceRecordId, StrictModel, TaskId, _id
from .enums import (
    ClaimStatus,
    ContributionType,
    InterventionType,
    QuestionIntent,
    ReplySemantic,
    SimulatedTrigger,
    StagnationState,
)

CaseId = _id(r"^CASE\d{2}$")
GTContributionId = _id(r"^GTC-\d{2}$")
GTClaimJudgmentId = _id(r"^GTCL-\d{2}$")
GTStagnationId = _id(r"^GTS-\d{2}$")


class InteractiveEvidenceKind(str, Enum):
    CHECKIN_REPLY = "CHECKIN_REPLY"  # CheckInTool로 담당자에게 물어 받은 응답
    SUPPORT_REPLY = "SUPPORT_REPLY"  # 승인·전송된 SupportRequest에 대한 지원자의 응답


class InteractiveEvidenceExpectation(StrictModel):
    """행동한 뒤에만 얻는 Evidence의 의미 기반 기대값 (RPL ID를 저장하지 않는다)."""

    kind: InteractiveEvidenceKind
    task_id: TaskId
    responder_id: MemberId  # 응답하는 사람 (CHECKIN_REPLY: 담당자, SUPPORT_REPLY: 지원자)
    about_member_id: Optional[MemberId] = None  # SUPPORT_REPLY에서 지원받는 담당자
    expected_content: str  # 응답이 담고 있어야 할 사실 (평가용 설명)
    question_intent: Optional[QuestionIntent] = None  # CHECKIN_REPLY: 어떤 사실을 확인하는 질문이어야 하는가
    expected_semantic_outcome: Optional[ReplySemantic] = None  # CHECKIN_REPLY: 응답을 어떤 의미로 해석해야 하는가

    @model_validator(mode="after")
    def _check_kind(self):
        if self.kind == InteractiveEvidenceKind.SUPPORT_REPLY and self.question_intent is not None:
            raise ValueError("SUPPORT_REPLY has no question_intent")
        if self.kind == InteractiveEvidenceKind.SUPPORT_REPLY:
            if self.about_member_id is None or self.about_member_id == self.responder_id:
                raise ValueError("SUPPORT_REPLY requires about_member_id different from responder_id")
        elif self.about_member_id not in (None, self.responder_id):
            raise ValueError("CHECKIN_REPLY is answered by the assignee it is about")
        return self


class GroundTruthCase(StrictModel):
    case_id: CaseId
    title: str
    scenario: str
    contribution_ids: list[GTContributionId] = Field(default_factory=list)
    claim_judgment_ids: list[GTClaimJudgmentId] = Field(default_factory=list)
    stagnation_ids: list[GTStagnationId] = Field(default_factory=list)
    evaluation_notes: list[str] = Field(default_factory=list)


class GroundTruthContribution(StrictModel):
    """실제로 일어난 기여 1건 (사람 x 기여 유형 x 대상)."""

    gt_contribution_id: GTContributionId
    case_id: CaseId
    project_id: ProjectId
    member_id: MemberId
    contribution_type: ContributionType
    description: str
    expected_evidence_ids: list[SourceRecordId] = Field(min_length=1)
    related_task_ids: list[TaskId] = Field(default_factory=list)
    related_claim_id: Optional[ClaimId] = None  # 이 기여를 주장한 원본 Claim (없으면 None)
    expected_interactive_evidence: list[InteractiveEvidenceExpectation] = Field(default_factory=list)
    inaccessible_source_ids: list[SourceRecordId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_disjoint(self):
        if set(self.expected_evidence_ids) & set(self.inaccessible_source_ids):
            raise ValueError("inaccessible sources cannot be expected evidence")
        return self


class GroundTruthClaimJudgment(StrictModel):
    """원본 Claim에서 분리된 atomic claim 하나에 대한 정답 판정."""

    gt_claim_id: GTClaimJudgmentId
    case_id: CaseId
    claim_id: ClaimId  # 입력 데이터의 원본 Claim ID
    claimant_id: MemberId
    claimed_type: ContributionType
    atomic_claim: str
    expected_status: ClaimStatus
    expected_supporting_evidence_ids: list[SourceRecordId] = Field(default_factory=list)
    expected_contradicting_evidence_ids: list[SourceRecordId] = Field(default_factory=list)
    related_gt_contribution_id: Optional[GTContributionId] = None

    @property
    def expected_evidence_ids(self) -> list[str]:
        return self.expected_supporting_evidence_ids + self.expected_contradicting_evidence_ids

    @model_validator(mode="after")
    def _check_status_vs_evidence(self):
        s = self.expected_status
        sup, con = self.expected_supporting_evidence_ids, self.expected_contradicting_evidence_ids
        if not re.fullmatch(r"CLM-\d{2}", self.claim_id):
            raise ValueError("claim_id must reference an original (non-atomic) claim")
        if s == ClaimStatus.PENDING_VERIFICATION:
            raise ValueError("ground truth must not be PENDING_VERIFICATION")
        if s == ClaimStatus.VERIFIED and (not sup or con):
            raise ValueError("VERIFIED requires supporting and no contradicting evidence")
        if s == ClaimStatus.CONFLICTING_EVIDENCE and (not sup or not con):
            raise ValueError("CONFLICTING_EVIDENCE requires both supporting and contradicting evidence")
        if s == ClaimStatus.INSUFFICIENT_EVIDENCE and sup:
            raise ValueError("INSUFFICIENT_EVIDENCE must not list supporting evidence")
        if not self.expected_evidence_ids:
            raise ValueError("at least one expected evidence id is required")
        return self


class ExpectedIntervention(StrictModel):
    intervention_type: InterventionType
    supporter_member_id: Optional[MemberId] = None
    earliest_at: Optional[AwareDatetime] = None  # 이 시각 이후(=Block 확인 이후)에 제안되어야 함


BlockKind = Literal["INTERNAL_ISSUE", "EXTERNAL_DEPENDENCY"]


class GroundTruthStagnation(StrictModel):
    """(팀원, Task) 단위 정체 정답.

    candidate_expected: 기록만 보고 상태 확인(후보화)이 필요한 상황인가.
      True = 후보가 되어 확인해야 한다 / False = 확인이 불필요하다 / None = 어느 쪽이든 허용 (채점하지 않음).
    block_kind: 실제 Block의 종류. EXTERNAL_DEPENDENCY(외부 승인·타 팀·외부 업체)면 팀 내 지원 요청은 기대하지 않는다.
    RESOLVED는 팀 내 지원 없이(외부 승인, 본인 해결) 일어날 수도 있으므로 expected_intervention을 요구하지 않는다.
    """

    gt_stagnation_id: GTStagnationId
    case_id: CaseId
    project_id: ProjectId
    member_id: MemberId
    task_id: TaskId
    is_actual_block: bool
    block_started_at: Optional[AwareDatetime] = None
    block_start_tolerance_hours: int = Field(default=24, ge=0)
    block_cause: Optional[str] = None
    evaluation_as_of: AwareDatetime  # 이 시각 기준으로 expected_final_state를 평가
    expected_final_state: StagnationState
    # None이면 경로는 채점하지 않고 최종 상태 + forbidden_states만 채점
    expected_state_sequence: Optional[list[StagnationState]] = None
    forbidden_states: list[StagnationState] = Field(default_factory=list)
    expected_intervention: Optional[ExpectedIntervention] = None
    resolved_at: Optional[AwareDatetime] = None
    expected_evidence_ids: list[SourceRecordId] = Field(min_length=1)
    expected_interactive_evidence: list[InteractiveEvidenceExpectation] = Field(default_factory=list)
    inaccessible_source_ids: list[SourceRecordId] = Field(default_factory=list)
    candidate_expected: Optional[bool] = True
    block_kind: Optional[BlockKind] = None

    @model_validator(mode="after")
    def _check_consistency(self):
        final = self.expected_final_state
        if self.is_actual_block:
            if self.block_started_at is None:
                raise ValueError("actual block requires block_started_at")
            if final not in (StagnationState.CONFIRMED_BLOCK, StagnationState.RESOLVED):
                raise ValueError("actual block must end in CONFIRMED_BLOCK or RESOLVED")
            if self.candidate_expected is False:
                raise ValueError("actual block must not mark the candidate as unnecessary")
            if self.block_kind == "EXTERNAL_DEPENDENCY" and self.expected_intervention is not None \
                    and self.expected_intervention.intervention_type == InterventionType.SUPPORT:
                raise ValueError("external dependency block does not expect a team SUPPORT request")
        else:
            if self.block_started_at is not None or self.block_cause is not None or self.block_kind is not None:
                raise ValueError("non-block case must not have block_started_at/block_cause/block_kind")
            if StagnationState.CONFIRMED_BLOCK not in self.forbidden_states:
                raise ValueError("non-block case must forbid CONFIRMED_BLOCK")
        if final in self.forbidden_states:
            raise ValueError("expected_final_state is forbidden")
        seq = self.expected_state_sequence
        if seq is not None:
            if seq[-1] != final:
                raise ValueError("expected_state_sequence must end with expected_final_state")
            if any(s in self.forbidden_states for s in seq):
                raise ValueError("expected_state_sequence contains a forbidden state")
        if final == StagnationState.RESOLVED:
            if self.resolved_at is None:
                raise ValueError("RESOLVED requires resolved_at")
            if self.block_started_at and self.resolved_at <= self.block_started_at:
                raise ValueError("resolved_at must be after block_started_at")
        elif self.resolved_at is not None:
            raise ValueError("resolved_at is only allowed when final state is RESOLVED")
        if self.block_started_at and self.evaluation_as_of <= self.block_started_at:
            raise ValueError("evaluation_as_of must be after block_started_at")
        if set(self.expected_evidence_ids) & set(self.inaccessible_source_ids):
            raise ValueError("inaccessible sources cannot be expected evidence")
        return self


ScenarioId = _id(r"^ISC-\d{2}$")


class ProbeClaim(StrictModel):
    """평가 시나리오에서 평가 계층이 격리된 환경 복사본에 제출하는 Claim (입력 데이터에는 없다)."""

    claim_id: ClaimId
    member_id: MemberId
    submitted_at: AwareDatetime
    text: str


class InteractiveScenario(StrictModel):
    """Interactive Verification 평가 시나리오. Agent는 probe_claim을 일반 Claim으로만 본다."""

    scenario_id: ScenarioId
    case_id: CaseId
    title: str
    probe_claim: ProbeClaim
    verify_at: AwareDatetime
    expected_contribution_type: ContributionType
    expected_initial_status: ClaimStatus
    expected_final_status: ClaimStatus
    expected_interactions: list[InteractiveEvidenceExpectation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self):
        if self.verify_at < self.probe_claim.submitted_at:
            raise ValueError("verify_at must not be before the probe claim is submitted")
        if not re.fullmatch(r"CLM-\d{2}", self.probe_claim.claim_id):
            raise ValueError("probe claim must be an original (non-atomic) claim id")
        for x in self.expected_interactions:
            if x.kind != InteractiveEvidenceKind.CHECKIN_REPLY or x.question_intent is None \
                    or x.expected_semantic_outcome is None:
                raise ValueError("scenario interactions must be CHECKIN_REPLY with intent and semantic outcome")
        return self


# 응답 의미 정답이 가질 수 있는 값 (질문 의도·행동 종류별)
ALLOWED_REPLY_SEMANTICS = {
    QuestionIntent.STATUS_CHECK: {ReplySemantic.REPORTS_BLOCKED, ReplySemantic.REPORTS_ON_TRACK,
                                  ReplySemantic.CONFIRMS_COMPLETION, ReplySemantic.NOT_INFORMATIVE},
    QuestionIntent.COMPLETION_CONFIRMATION: {ReplySemantic.CONFIRMS_COMPLETION, ReplySemantic.REPORTS_INCOMPLETE,
                                             ReplySemantic.NOT_INFORMATIVE},
    QuestionIntent.COUNTERPART_CONFIRMATION: {ReplySemantic.CONFIRMS_COUNTERPART, ReplySemantic.DENIES_COUNTERPART,
                                              ReplySemantic.NOT_INFORMATIVE},
    SimulatedTrigger.SUPPORT_REQUEST: {ReplySemantic.ACCEPTS_SUPPORT, ReplySemantic.DECLINES_SUPPORT,
                                       ReplySemantic.NOT_INFORMATIVE},
}


class GroundTruthReplyLabel(StrictModel):
    """시뮬레이션 응답 1건의 의미 정답 (응답 해석기 단독 평가용).

    응답이 실제로 전달되는지와 무관하게, 그 문장을 사람이 읽으면 어떻게 이해하는지를 적는다.
    """

    reply_id: SimulatedReplyId
    project_id: ProjectId
    expected_semantic: ReplySemantic
    expected_block_kind: Optional[BlockKind] = None  # REPORTS_BLOCKED일 때만
    note: str = ""  # 해석이 까다로운 이유 (복합 표현, 부정, 숫자 등)

    @model_validator(mode="after")
    def _check(self):
        blocked = self.expected_semantic == ReplySemantic.REPORTS_BLOCKED
        if blocked != (self.expected_block_kind is not None):
            raise ValueError("expected_block_kind is required for REPORTS_BLOCKED and only for it")
        return self


class GroundTruthBundle(StrictModel):
    project_id: ProjectId
    cases: list[GroundTruthCase]
    contributions: list[GroundTruthContribution]
    claim_judgments: list[GroundTruthClaimJudgment]
    stagnations: list[GroundTruthStagnation]
    interactive_scenarios: list[InteractiveScenario] = Field(default_factory=list)
    reply_labels: list[GroundTruthReplyLabel] = Field(default_factory=list)
