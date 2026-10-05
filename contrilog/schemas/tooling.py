"""Tool layer 기록 모델: 사람에게 나간 행동, 받은 응답, Tool 호출 로그.

- OutboundAction / InboundReply는 Agent가 실제로 수행한 행동과 그 결과로 받은 응답이다.
  시뮬레이션 원본(SimulatedReply)과 달리, Agent가 행동한 뒤에만 생긴다.
- ToolCallLog는 원문을 복제하지 않는다. 파라미터의 자유 텍스트는 길이만 남기고,
  결과는 원본 기록 ID만 남긴다.
"""

from typing import Any, Optional

from pydantic import AwareDatetime, Field, model_validator

from .base import ActionId, MemberId, ProjectId, ReplyId, StrictModel, TaskId, ToolCallId
from .enums import ActionStatus, ActionType, InterventionType, QuestionIntent, ToolCallStatus


class ActionStatusChange(StrictModel):
    status: ActionStatus
    changed_at: AwareDatetime
    changed_by: Optional[MemberId] = None  # None = Agent
    note: Optional[str] = None


class OutboundAction(StrictModel):
    action_id: ActionId
    project_id: ProjectId
    action_type: ActionType
    task_id: TaskId
    recipient_id: MemberId  # 메시지를 받는 사람 (check-in: 담당자, 지원 요청: 지원자)
    about_member_id: MemberId  # 대상 업무의 담당자
    intervention_type: Optional[InterventionType] = None
    question_intent: Optional[QuestionIntent] = None  # CHECKIN이면 필수: 질문이 확인하려는 사실
    message: str = Field(min_length=1)
    created_at: AwareDatetime
    status: ActionStatus
    status_history: list[ActionStatusChange] = Field(min_length=1)

    @property
    def sent_at(self):
        return next((h.changed_at for h in self.status_history if h.status == ActionStatus.SENT), None)

    @model_validator(mode="after")
    def _check(self):
        if self.status_history[-1].status != self.status:
            raise ValueError("status must equal the last status_history entry")
        if self.action_type == ActionType.CHECKIN:
            if self.intervention_type is not None:
                raise ValueError("CHECKIN has no intervention_type")
            if self.recipient_id != self.about_member_id:
                raise ValueError("CHECKIN is sent to the task assignee")
            if self.question_intent is None:
                raise ValueError("CHECKIN requires question_intent")
        else:
            if self.intervention_type is None:
                raise ValueError("SUPPORT_REQUEST requires intervention_type")
            if self.recipient_id == self.about_member_id:
                raise ValueError("support request recipient must differ from the assignee")
            if self.question_intent is not None:
                raise ValueError("SUPPORT_REQUEST has no question_intent")
            seq = [h.status for h in self.status_history]
            if seq[0] != ActionStatus.PROPOSED:
                raise ValueError("SUPPORT_REQUEST must start as PROPOSED")
            if ActionStatus.SENT in seq and ActionStatus.APPROVED not in seq[: seq.index(ActionStatus.SENT)]:
                raise ValueError("SUPPORT_REQUEST cannot be SENT without APPROVED")
        return self


class InboundReply(StrictModel):
    reply_id: ReplyId
    project_id: ProjectId
    action_id: ActionId
    responder_id: MemberId
    received_at: AwareDatetime
    text: str


class ToolCallLog(StrictModel):
    call_id: ToolCallId
    sequence: int = Field(ge=1)
    tool_name: str
    operation: str
    project_id: ProjectId
    as_of: AwareDatetime  # 시뮬레이션 시각 (Agent가 관찰한 시점)
    logged_at: AwareDatetime  # 실제 기록 시각 (clock 주입 가능)
    parameters: dict[str, Any]
    returned_source_ids: list[str] = Field(default_factory=list)  # UT-/REV-/T/MSG-/CLM-
    returned_action_ids: list[ActionId] = Field(default_factory=list)
    returned_reply_ids: list[ReplyId] = Field(default_factory=list)
    result_count: int = Field(default=0, ge=0)
    status: ToolCallStatus
    error: Optional[str] = None
