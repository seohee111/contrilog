"""Tool 결과 → Candidate 변환 (원본 source_id를 그대로 유지)."""

from contrilog.schemas import EvidenceSourceType

from .protocols import Candidate
from .text import normalize


def from_result(result) -> list[Candidate]:
    """Tool 결과 객체(ProjectStatusResult / *SearchResult)를 Candidate 목록으로 바꾼다."""
    if hasattr(result, "tasks"):
        return [_task(t) for t in result.tasks]
    out = []
    for item in (result.items if hasattr(result, "items") else []):
        if hasattr(item, "spoken_at"):
            out.append(Candidate(
                source_id=item.source_id, source_type=EvidenceSourceType.MEETING_UTTERANCE,
                actor_ids=(item.speaker_id,), at=item.spoken_at, text=item.text,
                match_text=normalize(item.text), meeting_id=item.meeting_id))
        elif hasattr(item, "edited_at"):
            body = f"{item.change_summary}\n{item.diff_excerpt}"
            out.append(Candidate(
                source_id=item.source_id, source_type=EvidenceSourceType.DOCUMENT_REVISION,
                actor_ids=(item.author_id,), at=item.edited_at, text=item.change_summary,
                match_text=normalize(f"{item.document_title}\n{body}"), document_id=item.document_id,
                document_type=item.document_type.value))
        elif hasattr(item, "sent_at"):
            out.append(Candidate(
                source_id=item.source_id, source_type=EvidenceSourceType.MESSAGE,
                actor_ids=(item.sender_id,), at=item.sent_at, text=item.text,
                match_text=normalize(item.text), reply_to=item.reply_to_message_id))
    return out


def _task(t) -> Candidate:
    return Candidate(
        source_id=t.source_id, source_type=EvidenceSourceType.TASK, actor_ids=tuple(t.assignee_ids),
        at=t.status_since, text=f"{t.title}: {t.description} [{t.status.value}]",
        match_text=normalize(f"{t.title}\n{t.description}"), task_status=t.status.value,
        task_document_ids=tuple(t.related_document_ids))


def from_reply(reply) -> Candidate:
    """InboxTool이 돌려준 확인 응답(InboundReply)을 발화 기록 후보로 바꾼다 (원본 RPL ID 유지)."""
    return Candidate(
        source_id=reply.reply_id, source_type=EvidenceSourceType.INBOUND_REPLY, actor_ids=(reply.responder_id,),
        at=reply.received_at, text=reply.text, match_text=normalize(reply.text))
