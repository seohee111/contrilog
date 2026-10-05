"""Time-aware Project Snapshot.

as_of 시각에 Agent가 실제로 알 수 있었던 정보만 남긴다. 공개 규칙:

| 기록 | 보이는 조건 |
|---|---|
| Project / Member | 항상 (프로젝트 시작 시 확정된 정보) |
| Meeting + 발언 | 회의가 끝난 뒤 (ended_at <= as_of). 진행 중인 회의의 발언은 회의록이 공개되기 전이므로 보이지 않는다 |
| DocumentHistory | edited_at <= as_of |
| Message | sent_at <= as_of |
| ContributionClaim | submitted_at <= as_of |
| Task | created_at <= as_of. status / status_history, due_date / due_date_history는 as_of까지의 이력으로 재구성 |

Task의 related_document_ids / depends_on_task_ids 중 as_of에 아직 존재하지 않는
문서(첫 리비전 전)나 Task(생성 전)는 제거한다. 남겨 두면 미래의 문서·Task 존재가 드러난다.

경계는 포함(<=)이다. 정확히 as_of에 생긴 기록은 보인다.
"""

from datetime import datetime
from pathlib import Path

from contrilog.schemas import ProjectInput, ProjectSnapshot, Task

from .input_loader import load_project_input


class SnapshotTimeError(ValueError):
    pass


def require_aware(as_of: datetime) -> datetime:
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise SnapshotTimeError("as_of must be a timezone-aware datetime")
    return as_of


def task_as_of(task: Task, as_of: datetime, visible_documents: set[str], visible_tasks: set[str]) -> Task:
    """as_of까지의 상태 변경만 적용해 그 당시의 Task를 재구성한다."""
    history = [h for h in task.status_history if h.changed_at <= as_of]
    if not history:
        raise SnapshotTimeError(f"{task.task_id} did not exist at {as_of.isoformat()}")
    data = task.model_dump()
    data["status_history"] = [h.model_dump() for h in history]
    data["status"] = history[-1].to_status
    due_changes = [c for c in task.due_date_history if c.changed_at <= as_of]
    data["due_date_history"] = [c.model_dump() for c in due_changes]
    data["due_date"] = due_changes[-1].to_due_date if due_changes else task.initial_due_date
    data["related_document_ids"] = [d for d in task.related_document_ids if d in visible_documents]
    data["depends_on_task_ids"] = [t for t in task.depends_on_task_ids if t in visible_tasks]
    return Task.model_validate(data)


def build_snapshot(full: ProjectInput, as_of: datetime) -> ProjectSnapshot:
    """전체 입력에서 as_of 시점의 snapshot을 만든다. 반환값은 원본과 객체를 공유하지 않는다."""
    require_aware(as_of)
    meetings = [m for m in full.meetings if m.ended_at <= as_of]
    meeting_ids = {m.meeting_id for m in meetings}
    revisions = [r for r in full.document_history if r.edited_at <= as_of]
    documents = {r.document_id for r in revisions}
    created = [t for t in full.tasks if t.created_at <= as_of]
    task_ids = {t.task_id for t in created}

    def dump(items):
        return [i.model_dump() for i in items]

    return ProjectSnapshot.model_validate({
        "as_of": as_of,
        "project": full.project.model_dump(),
        "members": dump(full.members),
        "meetings": dump(meetings),
        "utterances": dump(u for u in full.utterances if u.meeting_id in meeting_ids and u.spoken_at <= as_of),
        "document_history": dump(revisions),
        "tasks": dump(task_as_of(t, as_of, documents, task_ids) for t in created),
        "messages": dump(m for m in full.messages if m.sent_at <= as_of),
        "claims": dump(c for c in full.claims if c.submitted_at <= as_of),
    })


def get_project_snapshot(project_id: str, as_of: datetime, data_root: Path | None = None) -> ProjectSnapshot:
    return build_snapshot(load_project_input(project_id, data_root), as_of)
