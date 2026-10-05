"""F. CheckInTool / G. SupportRequestTool / H. InboxTool, 그리고 사람 전용 HumanApprovalGate.

- CheckInTool.send: 담당자에게 질문을 보낸다(즉시 SENT). 응답은 바로 반환되지 않는다.
  session 시각이 응답 도착 시각을 지나야 InboxTool로 볼 수 있다.
- SupportRequestTool.propose: 지원/재배분/에스컬레이션 '제안'만 만든다(PROPOSED).
  승인·거절은 사람이 HumanApprovalGate로 한다. Agent tool 목록에는 승인 기능이 없다.
  APPROVED인 제안만 SupportRequestTool.send로 전달(SENT)할 수 있다.
  어떤 경우에도 Task 담당자나 상태를 바꾸지 않는다.
"""

from contrilog.schemas import (
    ActionStatus,
    ActionStatusChange,
    ActionType,
    InterventionType,
    OutboundAction,
    QuestionIntent,
)

from .base import Tool, ToolError, operation
from .results import ActionResult, InboxResult


class CheckInTool(Tool):
    name = "CheckInTool"
    description = (
        "Task 담당자에게 확인 질문을 보낸다. question_intent는 질문이 확인하려는 사실(진행 상황 / 완료 여부 / "
        "상대방 확인)이며, 응답은 시간이 지난 뒤 InboxTool로 확인한다."
    )

    @operation
    def send(self, task_id: str, member_id: str, question: str,
             question_intent: QuestionIntent | str = QuestionIntent.STATUS_CHECK) -> ActionResult:
        self._member(member_id)
        task = self._task(task_id)
        if member_id not in task.assignee_ids:
            raise ToolError(f"{member_id} is not an assignee of {task_id}")
        if not question.strip():
            raise ToolError("question must not be empty")
        try:
            question_intent = QuestionIntent(question_intent)
        except ValueError:
            raise ToolError(f"unknown question_intent {question_intent}") from None
        action = self._session._new_action(
            action_type=ActionType.CHECKIN, task_id=task_id, recipient_id=member_id,
            about_member_id=member_id, intervention_type=None, message=question,
            initial_status=ActionStatus.SENT, question_intent=question_intent)
        self._session._dispatch(action)
        return ActionResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, actions=[action])

    @operation
    def list_sent(self) -> ActionResult:
        actions = self._session._actions_of(ActionType.CHECKIN)
        return ActionResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, actions=actions)


class SupportRequestTool(Tool):
    name = "SupportRequestTool"
    description = (
        "막힌 Task에 대한 지원·재배분·에스컬레이션을 제안(PROPOSED)한다. 사람의 승인(APPROVED) 후에만 "
        "send로 지원자에게 전달(SENT)할 수 있으며, 업무 재배정은 자동 실행하지 않는다."
    )

    @operation
    def propose(
        self,
        task_id: str,
        about_member_id: str,
        supporter_id: str,
        message: str,
        intervention_type: InterventionType | str = InterventionType.SUPPORT,
    ) -> ActionResult:
        self._member(about_member_id)
        self._member(supporter_id)
        task = self._task(task_id)
        if about_member_id not in task.assignee_ids:
            raise ToolError(f"{about_member_id} is not an assignee of {task_id}")
        if supporter_id == about_member_id:
            raise ToolError("supporter must differ from the assignee")
        try:
            intervention_type = InterventionType(intervention_type)
        except ValueError:
            raise ToolError(f"unknown intervention_type {intervention_type}") from None
        if not message.strip():
            raise ToolError("message must not be empty")
        action = self._session._new_action(
            action_type=ActionType.SUPPORT_REQUEST, task_id=task_id, recipient_id=supporter_id,
            about_member_id=about_member_id, intervention_type=intervention_type, message=message,
            initial_status=ActionStatus.PROPOSED)
        return ActionResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, actions=[action])

    @operation
    def send(self, action_id: str) -> ActionResult:
        action = self._session._get_action(action_id, ActionType.SUPPORT_REQUEST)
        if action.status != ActionStatus.APPROVED:
            raise ToolError(f"{action_id} is {action.status.value}; only APPROVED requests can be sent")
        action = self._session._transition(action, ActionStatus.SENT, by=None)
        self._session._dispatch(action)
        return ActionResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, actions=[action])

    @operation
    def list_requests(self, status: ActionStatus | str | None = None) -> ActionResult:
        if status is not None:
            try:
                status = ActionStatus(status)
            except ValueError:
                raise ToolError(f"unknown status {status}") from None
        actions = [a for a in self._session._actions_of(ActionType.SUPPORT_REQUEST)
                   if status is None or a.status == status]
        return ActionResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, actions=actions)


class InboxTool(Tool):
    name = "InboxTool"
    description = "Agent가 보낸 check-in / 지원 요청에 대해 as_of까지 도착한 응답을 조회한다."

    @operation
    def list_replies(self, action_id: str | None = None) -> InboxResult:
        replies = [r for r in self._session._delivered_replies()
                   if action_id is None or r.action_id == action_id]
        return InboxResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, replies=replies)


class HumanApprovalGate:
    """사람(팀원/사용자)이 지원 요청 제안을 승인·거절하는 창구. Agent tool이 아니다."""

    def __init__(self, session):
        self._session = session

    def _decide(self, action_id: str, approver_id: str, status: ActionStatus, note: str | None):
        if approver_id not in {m.member_id for m in self._session.snapshot.members}:
            raise ToolError(f"member {approver_id} not found")
        action = self._session._get_action(action_id, ActionType.SUPPORT_REQUEST)
        if action.status != ActionStatus.PROPOSED:
            raise ToolError(f"{action_id} is {action.status.value}; only PROPOSED requests can be decided")
        return self._session._transition(action, status, by=approver_id, note=note)

    def pending(self) -> list[OutboundAction]:
        """사람에게 보여 줄 결정 대기 중인 지원 요청 제안 목록."""
        return [a for a in self._session._actions_of(ActionType.SUPPORT_REQUEST) if a.status == ActionStatus.PROPOSED]

    def approve(self, action_id: str, approver_id: str, note: str | None = None) -> OutboundAction:
        return self._decide(action_id, approver_id, ActionStatus.APPROVED, note)

    def reject(self, action_id: str, approver_id: str, note: str | None = None) -> OutboundAction:
        return self._decide(action_id, approver_id, ActionStatus.REJECTED, note)


__all__ = ["ActionStatusChange", "CheckInTool", "HumanApprovalGate", "InboxTool", "SupportRequestTool"]
