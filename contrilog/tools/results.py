"""Tool 반환 모델.

- 모든 항목은 원본 ID(source_id: UT-/REV-/T/MSG-/CLM-)를 그대로 가진다.
- 관찰 사실만 담는다. 정체 상태, Claim 판정, 기여 유형 추론, 점수/순위 필드는 없다.
"""

from datetime import date
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict

from contrilog.schemas import (
    ChannelType,
    ClaimSource,
    ClaimStatus,
    ContributionType,
    DocumentType,
    InboundReply,
    OutboundAction,
    TaskStatus,
    TaskDueDateChange,
    TaskStatusChange,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolResult(_Model):
    tool_name: str
    project_id: str
    as_of: AwareDatetime

    def source_ids(self) -> list[str]:
        return []

    def action_ids(self) -> list[str]:
        return []

    def reply_ids(self) -> list[str]:
        return []

    def result_count(self) -> int:
        return 0


def _unique(ids):
    return list(dict.fromkeys(ids))


# ---------------------------------------------------------------- ProjectStatusTool
class ActivityRef(_Model):
    kind: Literal["DOCUMENT_REVISION", "TASK_STATUS_CHANGE", "MESSAGE", "MEETING_UTTERANCE"]
    source_id: str  # REV-/T(상태 변경)/MSG-/UT-
    at: AwareDatetime
    actor_id: str


class TaskStatusView(_Model):
    source_id: str  # task_id
    title: str
    description: str
    created_by: str
    created_at: AwareDatetime
    assignee_ids: list[str]
    due_date: date  # as_of 시점의 마감일
    due_date_history: list[TaskDueDateChange]  # as_of까지의 마감일 변경
    hours_until_due_end: float  # due_date 23:59:59 KST까지 남은 시간 (음수 = 지남)
    status: TaskStatus  # as_of 시점의 Task Board 상태 (데이터에 수치형 progress는 없음)
    status_since: AwareDatetime
    status_history: list[TaskStatusChange]
    related_document_ids: list[str]
    depends_on_task_ids: list[str]
    last_task_activity: Optional[ActivityRef]  # 관련 문서 리비전·상태 변경 중 가장 최근
    hours_since_last_task_activity: Optional[float]
    activity_window_days: int
    recent_revision_ids: list[str]  # 관련 문서의 최근 activity_window_days 일 리비전


class MemberActivityView(_Model):
    member_id: str
    name: str
    role: str
    last_revision: Optional[ActivityRef]
    last_message: Optional[ActivityRef]
    last_utterance: Optional[ActivityRef]
    last_task_update: Optional[ActivityRef]


class ProjectStatusResult(ToolResult):
    tasks: list[TaskStatusView]
    members: list[MemberActivityView]

    def source_ids(self):
        ids = []
        for t in self.tasks:
            ids.append(t.source_id)
            if t.last_task_activity:
                ids.append(t.last_task_activity.source_id)
            ids += t.recent_revision_ids
        for m in self.members:
            ids += [r.source_id for r in (m.last_revision, m.last_message, m.last_utterance, m.last_task_update) if r]
        return _unique(ids)

    def result_count(self):
        return len(self.tasks)


# ---------------------------------------------------------------- search hits
class UtteranceHit(_Model):
    source_id: str  # utterance_id
    meeting_id: str
    meeting_title: str
    sequence: int
    speaker_id: str
    speaker_name: str
    spoken_at: AwareDatetime
    text: str
    matched_terms: list[str]


class RevisionHit(_Model):
    source_id: str  # revision_id
    document_id: str
    document_title: str
    document_type: DocumentType
    section: Optional[str]  # 입력 데이터에 section 필드가 없어 현재는 항상 None
    author_id: str
    author_name: str
    edited_at: AwareDatetime
    change_summary: str
    diff_excerpt: str
    chars_added: int
    chars_deleted: int
    matched_terms: list[str]


class MessageHit(_Model):
    source_id: str  # message_id
    channel: str
    channel_type: ChannelType
    sender_id: str
    sender_name: str
    recipient_ids: list[str]
    sent_at: AwareDatetime
    text: str
    reply_to_message_id: Optional[str]
    matched_terms: list[str]


class ClaimView(_Model):
    source_id: str  # claim_id
    origin: Literal["SUBMITTED", "AGENT_DERIVED"]  # 팀원이 제출한 원본 / Agent가 분리한 atomic claim
    member_id: str
    submitted_at: AwareDatetime
    source: ClaimSource
    text: str
    parent_claim_id: Optional[str]
    claimed_type: Optional[ContributionType]  # AGENT_DERIVED에서만 값이 있음 (Agent가 지정)
    status: ClaimStatus
    matched_terms: list[str]


class _SearchResult(ToolResult):
    total_matched: int  # limit 적용 전 일치 건수

    def source_ids(self):
        return [i.source_id for i in self.items]

    def result_count(self):
        return len(self.items)


class MeetingSearchResult(_SearchResult):
    items: list[UtteranceHit]


class DocumentHistoryResult(_SearchResult):
    items: list[RevisionHit]


class MessageSearchResult(_SearchResult):
    items: list[MessageHit]


class ClaimListResult(_SearchResult):
    items: list[ClaimView]


# ---------------------------------------------------------------- actions
class ActionResult(ToolResult):
    actions: list[OutboundAction]

    def action_ids(self):
        return [a.action_id for a in self.actions]

    def source_ids(self):
        return _unique(a.task_id for a in self.actions)

    def result_count(self):
        return len(self.actions)


class InboxResult(ToolResult):
    replies: list[InboundReply]

    def reply_ids(self):
        return [r.reply_id for r in self.replies]

    def action_ids(self):
        return _unique(r.action_id for r in self.replies)

    def result_count(self):
        return len(self.replies)
