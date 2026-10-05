"""ToolSession — 특정 시각의 ContriLog가 Tool로만 세상을 관찰·행동하는 재현 가능한 환경.

    session = ToolSession("P001", as_of=datetime(2026, 9, 18, 10, tzinfo=KST))
    session.tools["MeetingSearchTool"].search(query="403")
    session.tools["CheckInTool"].send(task_id="T03", member_id="M_C", question="...")
    session.advance_to(datetime(2026, 9, 18, 12, tzinfo=KST))   # 시간은 앞으로만 간다
    session.tools["InboxTool"].list_replies()

- 관찰은 as_of snapshot(contrilog.data_access.snapshot)에 접근 정책(access_policy: 개인 DM 제외)을
  적용한 Agent용 snapshot만 사용한다.
- 시뮬레이션 응답은 Agent가 행동했을 때만 SimulatedResponder를 통해 예약되고,
  도착 시각이 지나야 InboxTool에 나타난다.
- 모든 Tool 호출은 ToolCallLog로 기록된다. 로그에는 원문 대신 원본 ID와 파라미터만 남고,
  자유 텍스트 파라미터(question/message/note)는 글자 수만 남긴다.
"""

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from contrilog.data_access.access_policy import apply_access_policy
from contrilog.data_access.input_loader import load_project_input
from contrilog.data_access.snapshot import SnapshotTimeError, build_snapshot, require_aware
from contrilog.schemas import (
    ActionStatus,
    ActionStatusChange,
    ActionType,
    ContributionClaim,
    ContributionType,
    InboundReply,
    OutboundAction,
    ProjectSnapshot,
    SimulatedTrigger,
    ToolCallLog,
    ToolCallStatus,
)
from contrilog.simulation.responder import SimulatedResponder

from .actions import CheckInTool, HumanApprovalGate, InboxTool, SupportRequestTool
from .base import ToolError
from .claims import ClaimTool
from .project_status import ProjectStatusTool
from .results import ToolResult
from .search import DocumentHistoryTool, MeetingSearchTool, MessageSearchTool

FREE_TEXT_PARAMS = {"question", "message", "note", "text"}
MAX_LOGGED_STR = 120


def _log_value(key: str, value: Any) -> Any:
    if key in FREE_TEXT_PARAMS and isinstance(value, str):
        return {"redacted_chars": len(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str):
        return value[:MAX_LOGGED_STR]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_LOGGED_STR]


class ToolSession:
    def __init__(
        self,
        project_id: str,
        as_of: datetime,
        *,
        data_root: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.project_id = project_id
        self.__full = load_project_input(project_id, data_root)
        self.__as_of = require_aware(as_of)
        self.__snapshot = self._agent_view(self.__as_of)
        self.__responder = SimulatedResponder(project_id, data_root)
        self.__actions: dict[str, OutboundAction] = {}
        self.__replies: list[InboundReply] = []
        self.__atomic: dict[str, ContributionClaim] = {}
        self.__log: list[ToolCallLog] = []
        self._clock = clock or (lambda: datetime.now(timezone.utc))

        tools = [
            ProjectStatusTool(self), MeetingSearchTool(self), DocumentHistoryTool(self), MessageSearchTool(self),
            ClaimTool(self), CheckInTool(self), SupportRequestTool(self), InboxTool(self),
        ]
        self.tools = {t.name: t for t in tools}  # Agent에게 노출되는 Tool
        self.human = HumanApprovalGate(self)  # 사람 전용 (Agent tool 아님)

    # ------------------------------------------------------------ time
    @property
    def as_of(self) -> datetime:
        return self.__as_of

    @property
    def snapshot(self) -> ProjectSnapshot:
        return self.__snapshot

    def advance_to(self, as_of: datetime) -> None:
        """시뮬레이션 시각을 앞으로 옮긴다. 과거로 되돌리는 것은 허용하지 않는다
        (미래를 본 뒤 되돌아가 판단하는 것을 막기 위함)."""
        require_aware(as_of)
        if as_of < self.__as_of:
            raise SnapshotTimeError("ToolSession time can only move forward")
        self.__as_of = as_of
        self.__snapshot = self._agent_view(as_of)
        self._collect_replies()

    def _agent_view(self, as_of: datetime) -> ProjectSnapshot:
        return apply_access_policy(build_snapshot(self.__full, as_of))

    # ------------------------------------------------------------ actions (Tool 내부용)
    def _new_action(self, *, action_type, task_id, recipient_id, about_member_id, intervention_type, message,
                    initial_status, question_intent=None) -> OutboundAction:
        action_id = f"ACT-{len(self.__actions) + 1:03d}"
        action = OutboundAction(
            action_id=action_id, project_id=self.project_id, action_type=action_type, task_id=task_id,
            recipient_id=recipient_id, about_member_id=about_member_id, intervention_type=intervention_type,
            question_intent=question_intent, message=message, created_at=self.__as_of, status=initial_status,
            status_history=[ActionStatusChange(status=initial_status, changed_at=self.__as_of)])
        self.__actions[action_id] = action
        return action.model_copy(deep=True)

    def _get_action(self, action_id: str, action_type: ActionType) -> OutboundAction:
        action = self.__actions.get(action_id)
        if action is None or action.action_type != action_type:
            raise ToolError(f"action {action_id} not found")
        return action.model_copy(deep=True)

    def _transition(self, action: OutboundAction, status: ActionStatus, by: str | None, note: str | None = None):
        data = self.__actions[action.action_id].model_dump()
        data["status"] = status
        data["status_history"].append({"status": status, "changed_at": self.__as_of, "changed_by": by, "note": note})
        updated = OutboundAction.model_validate(data)
        self.__actions[action.action_id] = updated
        return updated.model_copy(deep=True)

    def _actions_of(self, action_type: ActionType) -> list[OutboundAction]:
        return [a.model_copy(deep=True) for a in self.__actions.values() if a.action_type == action_type]

    def _dispatch(self, action: OutboundAction) -> None:
        """SENT 된 행동을 (시뮬레이션) 사람에게 전달한다. 응답 여부는 반환하지 않는다."""
        self.__responder.schedule(
            action_id=action.action_id, trigger=SimulatedTrigger(action.action_type.value),
            responder_id=action.recipient_id, about_member_id=action.about_member_id,
            task_id=action.task_id, sent_at=self.__as_of, question_intent=action.question_intent)
        self._collect_replies()

    def _collect_replies(self) -> None:
        for d in self.__responder.collect(self.__as_of):
            self.__replies.append(InboundReply(
                reply_id=f"RPL-{len(self.__replies) + 1:03d}", project_id=self.project_id,
                action_id=d.action_id, responder_id=d.responder_id, received_at=d.arrives_at, text=d.text))

    def _delivered_replies(self) -> list[InboundReply]:
        return [r.model_copy(deep=True) for r in self.__replies if r.received_at <= self.__as_of]

    # ------------------------------------------------------------ atomic claims (Tool 내부용)
    def _add_atomic_claim(self, parent: ContributionClaim, claimed_type: ContributionType, text: str):
        n = sum(1 for c in self.__atomic.values() if c.parent_claim_id == parent.claim_id) + 1
        claim = ContributionClaim(
            claim_id=f"{parent.claim_id}-{n:02d}", project_id=parent.project_id, member_id=parent.member_id,
            submitted_at=parent.submitted_at, source=parent.source, source_message_id=parent.source_message_id,
            text=text, parent_claim_id=parent.claim_id, claimed_type=claimed_type)
        self.__atomic[claim.claim_id] = claim
        return claim.model_copy(deep=True)

    def _atomic_claims_visible(self) -> list[ContributionClaim]:
        return [c.model_copy(deep=True) for c in self.__atomic.values()]

    # ------------------------------------------------------------ logging
    def _record_call(self, tool_name: str, operation: str, params: dict, result: ToolResult | None,
                     error: str | None = None) -> None:
        seq = len(self.__log) + 1
        self.__log.append(ToolCallLog(
            call_id=f"TC-{seq:04d}", sequence=seq, tool_name=tool_name, operation=operation,
            project_id=self.project_id, as_of=self.__as_of, logged_at=self._clock(),
            parameters={k: _log_value(k, v) for k, v in params.items()},
            returned_source_ids=result.source_ids() if result else [],
            returned_action_ids=result.action_ids() if result else [],
            returned_reply_ids=result.reply_ids() if result else [],
            result_count=result.result_count() if result else 0,
            status=ToolCallStatus.OK if error is None else ToolCallStatus.ERROR, error=error))

    @property
    def call_log(self) -> list[ToolCallLog]:
        return [c.model_copy(deep=True) for c in self.__log]

    def export_call_log(self, path: Path) -> Path:
        """호출 로그를 JSON Lines로 저장한다."""
        path = Path(path)
        with open(path, "w", encoding="utf-8") as f:
            for c in self.__log:
                f.write(json.dumps(c.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return path
