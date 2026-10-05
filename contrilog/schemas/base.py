"""공통 base model과 ID 타입.

ID 형식을 정규식으로 고정해서, 잘못된 종류의 ID가 다른 필드에 들어가는 실수를
schema validation 단계에서 잡는다.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class StrictModel(BaseModel):
    """정의되지 않은 필드를 거부하는 base model."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def _id(pattern: str):
    return Annotated[str, StringConstraints(pattern=pattern)]


ProjectId = _id(r"^P\d{3}$")
MemberId = _id(r"^M_[A-Z]$")
MilestoneId = _id(r"^MS\d{2}$")
MeetingId = _id(r"^MT\d{2}$")
UtteranceId = _id(r"^UT-MT\d{2}-\d{2}$")
DocumentId = _id(r"^DOC-[A-Z0-9]+$")
RevisionId = _id(r"^REV-\d{3}$")
TaskId = _id(r"^T\d{2}$")
MessageId = _id(r"^MSG-\d{3}$")
ClaimId = _id(r"^CLM-\d{2}(-\d{2})?$")  # CLM-01: 원본 Claim, CLM-01-02: Agent가 분리한 atomic claim
EvidenceId = _id(r"^EV-\d{3,}$")
DecisionId = _id(r"^DEC-\d{3,}$")
MemoryId = _id(r"^MEM-\d{3,}$")
SimulatedReplyId = _id(r"^SIM-\d{3}$")

# Evidence/Ground Truth가 가리킬 수 있는 원본 기록 ID (발언, 문서 리비전, Task, 메시지)
SourceRecordId = _id(r"^(UT-MT\d{2}-\d{2}|REV-\d{3}|T\d{2}|MSG-\d{3})$")

# Tool layer (2단계)
ActionId = _id(r"^ACT-\d{3,}$")
ReplyId = _id(r"^RPL-\d{3,}$")
ToolCallId = _id(r"^TC-\d{4,}$")

# Agent 판단(ContributionEvidence / AgentDecision)이 근거로 인용할 수 있는 ID:
# 원본 기록 + Agent가 행동한 뒤 받은 응답(RPL-*). 시뮬레이션 내부 ID(SIM-*)는 허용하지 않는다.
# Ground Truth는 실행마다 번호가 달라지는 RPL-*을 쓰지 않으므로 SourceRecordId를 그대로 쓴다.
EvidenceSourceId = _id(r"^(UT-MT\d{2}-\d{2}|REV-\d{3}|T\d{2}|MSG-\d{3}|RPL-\d{3,})$")

# Agent 실행 기록 (3단계~)
ClaimRunId = _id(r"^CVR-\d{3,}$")
StagnationRunId = _id(r"^STR-\d{3,}$")
HumanDecisionId = _id(r"^HDC-\d{3}$")
