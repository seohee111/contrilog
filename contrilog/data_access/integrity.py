"""입력 데이터 내부의 참조 무결성 검사. 문제 목록(문자열)을 반환한다."""

from collections import Counter
from datetime import datetime, time, timedelta, timezone

from contrilog.schemas import ClaimStatus, ProjectInput

KST = timezone(timedelta(hours=9))


def _duplicates(ids) -> list[str]:
    return [i for i, n in Counter(ids).items() if n > 1]


def check_input_integrity(data: ProjectInput) -> list[str]:
    errors: list[str] = []
    pid = data.project.project_id
    members = {m.member_id for m in data.members}
    meetings = {m.meeting_id: m for m in data.meetings}
    messages = {m.message_id: m for m in data.messages}
    tasks = {t.task_id for t in data.tasks}
    documents = {r.document_id for r in data.document_history}
    period_start = datetime.combine(data.project.start_date, time.min, KST)
    period_end = datetime.combine(data.project.end_date, time.max, KST)

    def in_period(label: str, ts: datetime):
        if not (period_start <= ts <= period_end):
            errors.append(f"{label}: timestamp {ts.isoformat()} outside project period")

    def member(label: str, mid: str):
        if mid not in members:
            errors.append(f"{label}: unknown member {mid}")

    # 고유 ID
    for name, ids in [
        ("member", [m.member_id for m in data.members]),
        ("meeting", [m.meeting_id for m in data.meetings]),
        ("utterance", [u.utterance_id for u in data.utterances]),
        ("revision", [r.revision_id for r in data.document_history]),
        ("task", [t.task_id for t in data.tasks]),
        ("message", [m.message_id for m in data.messages]),
        ("claim", [c.claim_id for c in data.claims]),
    ]:
        for dup in _duplicates(ids):
            errors.append(f"duplicate {name} id: {dup}")

    # project_id 일관성
    records = [*data.members, *data.meetings, *data.document_history, *data.tasks, *data.messages, *data.claims]
    for r in records:
        if r.project_id != pid:
            errors.append(f"{type(r).__name__}: project_id {r.project_id} != {pid}")
    if set(data.project.member_ids) != members:
        errors.append("project.member_ids does not match members.json")

    for mt in data.meetings:
        in_period(mt.meeting_id, mt.started_at)
        for a in mt.attendee_ids:
            member(mt.meeting_id, a)

    seqs: dict[str, list[int]] = {}
    for u in data.utterances:
        mt = meetings.get(u.meeting_id)
        if mt is None:
            errors.append(f"{u.utterance_id}: unknown meeting {u.meeting_id}")
            continue
        member(u.utterance_id, u.speaker_id)
        if u.speaker_id not in mt.attendee_ids:
            errors.append(f"{u.utterance_id}: speaker {u.speaker_id} is not an attendee")
        if not (mt.started_at <= u.spoken_at <= mt.ended_at):
            errors.append(f"{u.utterance_id}: spoken_at outside meeting time")
        if not u.utterance_id.startswith(f"UT-{u.meeting_id}-"):
            errors.append(f"{u.utterance_id}: id does not match meeting {u.meeting_id}")
        seqs.setdefault(u.meeting_id, []).append(u.sequence)
    for mid, s in seqs.items():
        if sorted(s) != list(range(1, len(s) + 1)):
            errors.append(f"{mid}: utterance sequence is not 1..N")

    doc_meta: dict[str, tuple] = {}
    for r in data.document_history:
        member(r.revision_id, r.author_id)
        in_period(r.revision_id, r.edited_at)
        meta = (r.document_title, r.document_type)
        if doc_meta.setdefault(r.document_id, meta) != meta:
            errors.append(f"{r.revision_id}: inconsistent title/type for {r.document_id}")

    for t in data.tasks:
        member(t.task_id, t.created_by)
        for a in t.assignee_ids:
            member(t.task_id, a)
        for d in t.related_document_ids:
            if d not in documents:
                errors.append(f"{t.task_id}: unknown document {d}")
        for dep in t.depends_on_task_ids:
            if dep not in tasks or dep == t.task_id:
                errors.append(f"{t.task_id}: invalid dependency {dep}")
        for ch in t.status_history:
            member(t.task_id, ch.changed_by)
            in_period(t.task_id, ch.changed_at)
        for ch in t.due_date_history:
            member(t.task_id, ch.changed_by)
            in_period(t.task_id, ch.changed_at)
        if t.status_history[0].changed_at != t.created_at:
            errors.append(f"{t.task_id}: first status change must be at created_at")

    for m in data.messages:
        member(m.message_id, m.sender_id)
        in_period(m.message_id, m.sent_at)
        for r in m.recipient_ids:
            member(m.message_id, r)
            if r == m.sender_id:
                errors.append(f"{m.message_id}: sender is also a recipient")
        if m.reply_to_message_id is not None:
            parent = messages.get(m.reply_to_message_id)
            if parent is None:
                errors.append(f"{m.message_id}: unknown reply_to {m.reply_to_message_id}")
            elif parent.sent_at >= m.sent_at or parent.channel != m.channel:
                errors.append(f"{m.message_id}: reply must be later and in the same channel")

    for c in data.claims:
        member(c.claim_id, c.member_id)
        in_period(c.claim_id, c.submitted_at)
        if c.source_message_id is not None and c.source_message_id not in messages:
            errors.append(f"{c.claim_id}: unknown source message {c.source_message_id}")
        # 입력 Claim은 원문 그대로여야 한다 (판단 결과가 섞이면 안 됨)
        if c.parent_claim_id is not None or c.claimed_type is not None:
            errors.append(f"{c.claim_id}: input claim must be raw (no parent/claimed_type)")
        if c.status != ClaimStatus.PENDING_VERIFICATION:
            errors.append(f"{c.claim_id}: input claim must be PENDING_VERIFICATION")

    return errors
