"""Agent가 관찰하는 원본 활동 기록: 회의, 문서 수정 이력, Task Board, 메시지.

모든 시각은 timezone 정보가 있는 datetime(AwareDatetime)이어야 한다.
"""

from datetime import date
from typing import Optional

from pydantic import AwareDatetime, Field, model_validator

from .base import (
    DocumentId,
    MeetingId,
    MemberId,
    MessageId,
    ProjectId,
    RevisionId,
    StrictModel,
    TaskId,
    UtteranceId,
)
from .enums import ChannelType, DocumentType, TaskStatus


class Meeting(StrictModel):
    meeting_id: MeetingId
    project_id: ProjectId
    title: str
    started_at: AwareDatetime
    ended_at: AwareDatetime
    attendee_ids: list[MemberId]
    agenda: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_time(self):
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be after started_at")
        return self


class MeetingUtterance(StrictModel):
    utterance_id: UtteranceId
    meeting_id: MeetingId
    sequence: int = Field(ge=1)
    speaker_id: MemberId
    spoken_at: AwareDatetime
    text: str = Field(min_length=1)


class DocumentHistory(StrictModel):
    """문서(코드·데이터 파일 포함)의 리비전 1건."""

    revision_id: RevisionId
    project_id: ProjectId
    document_id: DocumentId
    document_title: str
    document_type: DocumentType
    author_id: MemberId
    edited_at: AwareDatetime
    change_summary: str  # 편집 요약 또는 커밋 메시지
    diff_excerpt: str  # 변경 내용 일부
    chars_added: int = Field(ge=0)
    chars_deleted: int = Field(ge=0)


class TaskStatusChange(StrictModel):
    changed_at: AwareDatetime
    changed_by: MemberId
    from_status: Optional[TaskStatus]  # 생성 시점은 None
    to_status: TaskStatus
    note: Optional[str] = None


class TaskDueDateChange(StrictModel):
    """마감일 변경 1건. 생성 시 마감일은 첫 변경의 from_due_date (변경이 없으면 due_date)."""

    changed_at: AwareDatetime
    changed_by: MemberId
    from_due_date: date
    to_due_date: date
    note: Optional[str] = None

    @model_validator(mode="after")
    def _check_change(self):
        if self.from_due_date == self.to_due_date:
            raise ValueError("due date change must change the date")
        return self


class Task(StrictModel):
    task_id: TaskId
    project_id: ProjectId
    title: str
    description: str
    created_by: MemberId
    created_at: AwareDatetime
    assignee_ids: list[MemberId] = Field(min_length=1)
    due_date: date  # 데이터 수집 종료 시점의 마감일
    status: TaskStatus  # 데이터 수집 종료 시점의 상태
    status_history: list[TaskStatusChange] = Field(min_length=1)
    related_document_ids: list[DocumentId] = Field(default_factory=list)
    depends_on_task_ids: list[TaskId] = Field(default_factory=list)
    due_date_history: list[TaskDueDateChange] = Field(default_factory=list)  # 비어 있으면 마감일 변경 없음

    @property
    def initial_due_date(self) -> date:
        return self.due_date_history[0].from_due_date if self.due_date_history else self.due_date

    @model_validator(mode="after")
    def _check_due_date_history(self):
        changes = self.due_date_history
        for prev, cur in zip(changes, changes[1:]):
            if cur.changed_at < prev.changed_at:
                raise ValueError("due_date_history must be chronological")
            if cur.from_due_date != prev.to_due_date:
                raise ValueError("due_date_history chain is broken")
        if changes and changes[-1].to_due_date != self.due_date:
            raise ValueError("due_date must equal the last due_date_history entry")
        if changes and changes[0].changed_at < self.created_at:
            raise ValueError("due date cannot change before the task is created")
        return self

    @model_validator(mode="after")
    def _check_history(self):
        hist = self.status_history
        if hist[0].from_status is not None:
            raise ValueError("first status change must have from_status=None")
        for prev, cur in zip(hist, hist[1:]):
            if cur.changed_at < prev.changed_at:
                raise ValueError("status_history must be chronological")
            if cur.from_status != prev.to_status:
                raise ValueError("status_history chain is broken")
        if hist[-1].to_status != self.status:
            raise ValueError("status must equal the last status_history entry")
        return self


class Message(StrictModel):
    message_id: MessageId
    project_id: ProjectId
    channel: str  # 예: "#general", "#dev", "dm"
    channel_type: ChannelType
    sender_id: MemberId
    recipient_ids: list[MemberId] = Field(default_factory=list)  # DM일 때만 사용
    sent_at: AwareDatetime
    text: str = Field(min_length=1)
    reply_to_message_id: Optional[MessageId] = None

    @model_validator(mode="after")
    def _check_dm(self):
        if self.channel_type == ChannelType.DIRECT_MESSAGE and not self.recipient_ids:
            raise ValueError("direct message requires recipient_ids")
        if self.channel_type == ChannelType.CHANNEL and self.recipient_ids:
            raise ValueError("channel message must not have recipient_ids")
        return self
