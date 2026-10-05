"""A. ProjectStatusTool — as_of 시점 Task 상태와 최근 활동 사실."""

from datetime import datetime, time, timedelta, timezone

from .base import Tool, ToolError, operation
from .results import ActivityRef, MemberActivityView, ProjectStatusResult, TaskStatusView

KST = timezone(timedelta(hours=9))


def _hours(delta: timedelta) -> float:
    return round(delta.total_seconds() / 3600, 1)


def _latest(refs):
    refs = [r for r in refs if r is not None]
    return max(refs, key=lambda r: r.at) if refs else None


class ProjectStatusTool(Tool):
    name = "ProjectStatusTool"
    description = (
        "as_of 시점의 Task 상태(Task Board), 마감, 담당자, 상태 변경 이력, 관련 문서의 최근 리비전, "
        "팀원별 마지막 기록 시각을 반환한다. 정체 여부 같은 판단은 반환하지 않는다."
    )

    @operation
    def get_status(
        self,
        task_id: str | None = None,
        member_id: str | None = None,
        include_done: bool = True,
        activity_window_days: int = 7,
    ) -> ProjectStatusResult:
        if not 1 <= activity_window_days <= 60:
            raise ToolError("activity_window_days must be between 1 and 60")
        self._member(member_id)
        snap, as_of = self.snapshot, self.as_of
        tasks = [self._task(task_id)] if task_id else list(snap.tasks)
        if member_id:
            tasks = [t for t in tasks if member_id in t.assignee_ids]
        if not include_done:
            tasks = [t for t in tasks if t.status.value != "DONE"]

        window_start = as_of - timedelta(days=activity_window_days)
        views = []
        for t in tasks:
            revs = [r for r in snap.document_history if r.document_id in t.related_document_ids]
            rev_refs = [ActivityRef(kind="DOCUMENT_REVISION", source_id=r.revision_id, at=r.edited_at,
                                    actor_id=r.author_id) for r in revs]
            status_refs = [ActivityRef(kind="TASK_STATUS_CHANGE", source_id=t.task_id, at=h.changed_at,
                                       actor_id=h.changed_by) for h in t.status_history]
            last = _latest(rev_refs + status_refs)
            due_end = datetime.combine(t.due_date, time(23, 59, 59), KST)
            views.append(TaskStatusView(
                source_id=t.task_id, title=t.title, description=t.description, created_by=t.created_by,
                created_at=t.created_at, assignee_ids=t.assignee_ids, due_date=t.due_date,
                due_date_history=t.due_date_history,
                hours_until_due_end=_hours(due_end - as_of), status=t.status,
                status_since=t.status_history[-1].changed_at, status_history=t.status_history,
                related_document_ids=t.related_document_ids, depends_on_task_ids=t.depends_on_task_ids,
                last_task_activity=last, hours_since_last_task_activity=_hours(as_of - last.at) if last else None,
                activity_window_days=activity_window_days,
                recent_revision_ids=[r.revision_id for r in revs if r.edited_at > window_start],
            ))

        members = [m for m in snap.members if member_id is None or m.member_id == member_id]
        member_views = []
        for m in members:
            mid = m.member_id
            member_views.append(MemberActivityView(
                member_id=mid, name=m.name, role=m.role,
                last_revision=_latest(ActivityRef(kind="DOCUMENT_REVISION", source_id=r.revision_id,
                                                  at=r.edited_at, actor_id=mid)
                                      for r in snap.document_history if r.author_id == mid),
                last_message=_latest(ActivityRef(kind="MESSAGE", source_id=x.message_id, at=x.sent_at, actor_id=mid)
                                     for x in snap.messages if x.sender_id == mid),
                last_utterance=_latest(ActivityRef(kind="MEETING_UTTERANCE", source_id=u.utterance_id,
                                                   at=u.spoken_at, actor_id=mid)
                                       for u in snap.utterances if u.speaker_id == mid),
                last_task_update=_latest(ActivityRef(kind="TASK_STATUS_CHANGE", source_id=t.task_id,
                                                     at=h.changed_at, actor_id=mid)
                                         for t in snap.tasks for h in t.status_history if h.changed_by == mid),
            ))
        return ProjectStatusResult(tool_name=self.name, project_id=self.project_id, as_of=as_of, tasks=views, members=member_views)
