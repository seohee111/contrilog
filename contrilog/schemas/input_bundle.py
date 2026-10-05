"""Agent 입력 데이터 묶음 (data/input/<project_id>/ 의 전체 내용)."""

from .activity import DocumentHistory, Meeting, MeetingUtterance, Message, Task
from .base import StrictModel
from .contribution import ContributionClaim
from .project import Member, Project


class ProjectInput(StrictModel):
    project: Project
    members: list[Member]
    meetings: list[Meeting]
    utterances: list[MeetingUtterance]
    document_history: list[DocumentHistory]
    tasks: list[Task]
    messages: list[Message]
    claims: list[ContributionClaim]

    def source_record_ids(self) -> set[str]:
        """Evidence가 가리킬 수 있는 모든 원본 기록 ID."""
        return (
            {u.utterance_id for u in self.utterances}
            | {r.revision_id for r in self.document_history}
            | {t.task_id for t in self.tasks}
            | {m.message_id for m in self.messages}
        )
