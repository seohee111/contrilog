"""Claim 검증 Agent의 교체 가능한 계층 (Protocol).

각 계층은 결정적 구현(Deterministic*/RuleBased*)으로 시작하며, 나중에 일부만 LLM 구현으로 바꿀 수 있다.
계층 간 데이터는 아래 dataclass로만 주고받는다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol

from contrilog.schemas import (
    ClaimStatus,
    Confidence,
    ContributionType,
    EvidenceRelation,
    EvidenceSourceType,
    QuestionIntent,
    VerificationGapKind,
)

from .text import TermGroup, TermStatistics


@dataclass(frozen=True)
class MemberRef:
    member_id: str
    name: str

    @property
    def given_name(self) -> str:
        return self.name[1:] if len(self.name) >= 3 else self.name


@dataclass(frozen=True)
class SubmittedClaim:
    claim_id: str
    member_id: str
    submitted_at: datetime
    text: str


@dataclass(frozen=True)
class AtomicDraft:
    """분해 결과 (아직 ID 없음)."""

    contribution_type: ContributionType
    text: str
    topic_terms: tuple[str, ...]
    mentioned_member_ids: tuple[str, ...] = ()
    expects_outcome: bool = False  # Claim에 '반영되었다/수정되었다' 같은 결과 서술이 함께 있음


@dataclass(frozen=True)
class AtomicClaimSpec:
    atomic_claim_id: str
    parent_claim_id: str
    claimant_id: str
    contribution_type: ContributionType
    text: str
    topic: tuple[TermGroup, ...]
    mentioned_member_ids: tuple[str, ...]
    expects_outcome: bool
    submitted_at: datetime


@dataclass(frozen=True)
class SearchRequest:
    tool_name: str
    operation: str
    params: dict[str, Any]
    purpose: str


@dataclass(frozen=True)
class Candidate:
    """Tool 결과 한 건을 Tool 종류와 무관하게 다루기 위한 형태. 원본 ID를 그대로 가진다."""

    source_id: str
    source_type: EvidenceSourceType
    actor_ids: tuple[str, ...]  # 발언자/작성자/발신자, Task는 담당자들
    at: datetime
    text: str  # 사람이 읽는 원문 (excerpt용)
    match_text: str  # 정규화된 매칭용 텍스트 (제목 포함)
    meeting_id: Optional[str] = None
    document_id: Optional[str] = None
    document_type: Optional[str] = None
    reply_to: Optional[str] = None
    task_status: Optional[str] = None
    task_document_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnswerContext:
    """Agent가 보낸 확인 질문과 그 응답의 관계. 응답(RPL)을 해석할 때 대화 맥락으로 쓴다."""

    reply_id: str
    action_id: str
    atomic_claim_id: str
    gap_kind: VerificationGapKind
    asked_member_id: str
    task_id: str


@dataclass
class EvaluationContext:
    stats: TermStatistics
    members: dict[str, MemberRef]
    candidates: dict[str, Candidate]  # 계획된 검색 + 스레드 확장 + (받은 경우) 확인 응답
    tasks: dict[str, Candidate] = field(default_factory=dict)  # as_of 시점에 보이는 전체 Task
    answers: dict[str, AnswerContext] = field(default_factory=dict)  # reply_id → 질문 맥락

    def member_by_given_name(self, name: str) -> Optional[str]:
        for m in self.members.values():
            if name in (m.given_name, m.name):
                return m.member_id
        return None


@dataclass(frozen=True)
class EvidenceAssessment:
    candidate: Candidate
    relation: EvidenceRelation
    attributed_member_id: str  # 이 기록이 보여 주는 행위의 주체
    contribution_type: ContributionType  # 이 기록이 보여 주는 행위의 유형
    role: str  # direct / documentation / corroboration / outcome / completion / prior_by_other / attribution_to_other / context
    reason: str


@dataclass(frozen=True)
class GapDiagnosis:
    """Judge가 PENDING을 낸 이유. 다음 행동(확인 질문)을 정하는 입력이 된다."""

    kind: VerificationGapKind
    fact_to_confirm: str
    basis: tuple[EvidenceAssessment, ...]


@dataclass(frozen=True)
class Judgment:
    status: ClaimStatus
    confidence: Confidence
    rationale: str
    unresolved_questions: tuple[str, ...] = field(default_factory=tuple)
    gaps: tuple[GapDiagnosis, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PlannedCheckIn:
    """확인 행동 계획: 누구에게, 어떤 Task 맥락으로, 무엇을 확인할지(question_intent), 어떻게 물을지(question)."""

    target_member_id: str
    task_id: str
    question: str
    target_reason: str
    question_intent: QuestionIntent


@dataclass(frozen=True)
class NoAction:
    reason: str


class ClaimDecomposer(Protocol):
    def decompose(self, claim: SubmittedClaim, members: dict[str, MemberRef]) -> list[AtomicDraft]: ...


class EvidenceSearchPlanner(Protocol):
    def plan(self, atomic: AtomicClaimSpec) -> list[SearchRequest]: ...


class EvidenceEvaluator(Protocol):
    def assess(self, atomic: AtomicClaimSpec, ctx: EvaluationContext) -> list[EvidenceAssessment]: ...


class InteractiveVerificationPlanner(Protocol):
    def plan(self, gap: GapDiagnosis, atomic: AtomicClaimSpec, ctx: EvaluationContext,
             already_asked: set[tuple]) -> "PlannedCheckIn | NoAction": ...


class ClaimJudge(Protocol):
    def judge(self, atomic: AtomicClaimSpec, assessments: list[EvidenceAssessment],
              members: dict[str, MemberRef]) -> Judgment: ...
