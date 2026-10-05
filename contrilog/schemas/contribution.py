"""ContributionClaim / ContributionEvidence.

- ContributionClaim: 팀원이 스스로 주장한 기여.
  * 입력 데이터의 Claim은 원문 그대로이며(parent_claim_id=None, claimed_type=None),
    상태는 항상 PENDING_VERIFICATION이다.
  * Agent는 원문 Claim을 atomic claim으로 분리할 수 있다.
    atomic claim은 parent_claim_id와 claimed_type을 가진다 (예: CLM-07 -> CLM-07-01, CLM-07-02).
- ContributionEvidence: Agent가 원본 기록(발언/리비전/Task/메시지) 또는 Agent가 받은 응답(RPL-*)을
  Claim 또는 기여 판단에 연결한 결과. 점수·가중치 필드는 두지 않는다.
"""

from typing import Optional

from pydantic import AwareDatetime, Field, model_validator

from .base import (
    ClaimId,
    EvidenceId,
    EvidenceSourceId,
    MemberId,
    MessageId,
    ProjectId,
    StrictModel,
)
from .enums import (
    ClaimSource,
    ClaimStatus,
    ContributionType,
    EvidenceRelation,
    EvidenceSourceType,
)

_SOURCE_PREFIX = {
    EvidenceSourceType.MEETING_UTTERANCE: "UT-",
    EvidenceSourceType.DOCUMENT_REVISION: "REV-",
    EvidenceSourceType.TASK: "T",
    EvidenceSourceType.MESSAGE: "MSG-",
    EvidenceSourceType.INBOUND_REPLY: "RPL-",
}


def source_type_of(source_id: str) -> EvidenceSourceType:
    """원본 기록 ID로부터 기록 종류를 추론한다."""
    for source_type, prefix in _SOURCE_PREFIX.items():
        if source_id.startswith(prefix):
            return source_type
    raise ValueError(f"unknown source record id: {source_id}")


class ContributionClaim(StrictModel):
    claim_id: ClaimId
    project_id: ProjectId
    member_id: MemberId  # Claim을 주장한 사람
    submitted_at: AwareDatetime
    source: ClaimSource
    source_message_id: Optional[MessageId] = None
    text: str = Field(min_length=1)
    parent_claim_id: Optional[ClaimId] = None
    claimed_type: Optional[ContributionType] = None
    status: ClaimStatus = ClaimStatus.PENDING_VERIFICATION

    @model_validator(mode="after")
    def _check_atomic(self):
        if self.parent_claim_id is not None:
            if self.claimed_type is None:
                raise ValueError("atomic claim requires claimed_type")
            if not self.claim_id.startswith(self.parent_claim_id + "-"):
                raise ValueError("atomic claim_id must be '<parent_claim_id>-NN'")
        if self.source == ClaimSource.MESSAGE and self.source_message_id is None:
            raise ValueError("claim from MESSAGE requires source_message_id")
        return self


class ContributionEvidence(StrictModel):
    evidence_id: EvidenceId
    project_id: ProjectId
    member_id: MemberId  # 이 Evidence가 관련된 기여의 주체
    source_type: EvidenceSourceType
    source_id: EvidenceSourceId
    relation: EvidenceRelation
    excerpt: str
    claim_id: Optional[ClaimId] = None
    contribution_type: Optional[ContributionType] = None
    collected_at: AwareDatetime
    note: Optional[str] = None

    @model_validator(mode="after")
    def _check_source(self):
        if source_type_of(self.source_id) != self.source_type:
            raise ValueError(
                f"source_type {self.source_type.value} does not match source_id {self.source_id}"
            )
        return self
