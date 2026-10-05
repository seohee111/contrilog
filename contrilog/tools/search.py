"""B. MeetingSearchTool / C. DocumentHistoryTool / D. MessageSearchTool.

모두 session의 as_of snapshot 안에서만 검색한다. end 파라미터가 as_of보다 뒤여도 as_of로 잘린다.
"""

from datetime import datetime

from contrilog.schemas import ChannelType, DocumentType

from .base import Tool, ToolError, operation
from .results import (
    DocumentHistoryResult,
    MeetingSearchResult,
    MessageHit,
    MessageSearchResult,
    RevisionHit,
    UtteranceHit,
)
from .text_match import MatchMode, Order, match_terms, order_and_limit, time_window


def _in_window(ts, start, end) -> bool:
    return (start is None or ts >= start) and ts <= end


class MeetingSearchTool(Tool):
    name = "MeetingSearchTool"
    description = "as_of 이전에 끝난 회의의 발언을 키워드·발언자·회의·기간으로 검색한다."

    @operation
    def search(
        self,
        query: str | None = None,
        speaker_id: str | None = None,
        meeting_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        match: MatchMode = "all",
        order: Order = "asc",
        limit: int = 50,
    ) -> MeetingSearchResult:
        self._member(speaker_id)
        start, end = time_window(self.as_of, start, end)
        snap = self.snapshot
        meetings = {m.meeting_id: m for m in snap.meetings}
        names = {m.member_id: m.name for m in snap.members}
        hits = []
        for u in snap.utterances:
            if speaker_id and u.speaker_id != speaker_id:
                continue
            if meeting_id and u.meeting_id != meeting_id:
                continue
            if not _in_window(u.spoken_at, start, end):
                continue
            terms = match_terms(query, [u.text], match)
            if terms is None:
                continue
            hits.append(UtteranceHit(
                source_id=u.utterance_id, meeting_id=u.meeting_id, meeting_title=meetings[u.meeting_id].title,
                sequence=u.sequence, speaker_id=u.speaker_id, speaker_name=names[u.speaker_id],
                spoken_at=u.spoken_at, text=u.text, matched_terms=terms))
        items = order_and_limit(hits, lambda h: (h.spoken_at, h.source_id), order, limit)
        return MeetingSearchResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, total_matched=len(hits), items=items)


class DocumentHistoryTool(Tool):
    name = "DocumentHistoryTool"
    description = "as_of까지의 문서·코드 리비전을 키워드·작성자·문서·문서 종류·기간으로 검색한다."

    @operation
    def search(
        self,
        query: str | None = None,
        author_id: str | None = None,
        document_id: str | None = None,
        document_type: DocumentType | str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        match: MatchMode = "all",
        order: Order = "asc",
        limit: int = 50,
    ) -> DocumentHistoryResult:
        self._member(author_id)
        if document_type is not None:
            try:
                document_type = DocumentType(document_type)
            except ValueError:
                raise ToolError(f"unknown document_type {document_type}") from None
        start, end = time_window(self.as_of, start, end)
        snap = self.snapshot
        names = {m.member_id: m.name for m in snap.members}
        hits = []
        for r in snap.document_history:
            if author_id and r.author_id != author_id:
                continue
            if document_id and r.document_id != document_id:
                continue
            if document_type and r.document_type != document_type:
                continue
            if not _in_window(r.edited_at, start, end):
                continue
            terms = match_terms(query, [r.document_title, r.change_summary, r.diff_excerpt], match)
            if terms is None:
                continue
            hits.append(RevisionHit(
                source_id=r.revision_id, document_id=r.document_id, document_title=r.document_title,
                document_type=r.document_type, section=None, author_id=r.author_id,
                author_name=names[r.author_id], edited_at=r.edited_at, change_summary=r.change_summary,
                diff_excerpt=r.diff_excerpt, chars_added=r.chars_added, chars_deleted=r.chars_deleted,
                matched_terms=terms))
        items = order_and_limit(hits, lambda h: (h.edited_at, h.source_id), order, limit)
        return DocumentHistoryResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, total_matched=len(hits), items=items)


class MessageSearchTool(Tool):
    """공유 프로젝트 채널 메시지만 검색한다. 개인 DM은 session의 접근 정책으로 이미 제외되어 있어
    어떤 검색어·필터 조합으로도 반환되지 않는다 (channel_type=DIRECT_MESSAGE 필터는 항상 빈 결과)."""

    name = "MessageSearchTool"
    description = "as_of까지 공유 프로젝트 채널에 올라온 메시지를 키워드·발신자·참여자·채널·스레드·기간으로 검색한다. 개인 DM은 포함하지 않는다."

    @operation
    def search(
        self,
        query: str | None = None,
        sender_id: str | None = None,
        participant_id: str | None = None,
        channel: str | None = None,
        channel_type: ChannelType | str | None = None,
        thread_root_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        match: MatchMode = "all",
        order: Order = "asc",
        limit: int = 50,
    ) -> MessageSearchResult:
        self._member(sender_id)
        self._member(participant_id)
        if channel_type is not None:
            try:
                channel_type = ChannelType(channel_type)
            except ValueError:
                raise ToolError(f"unknown channel_type {channel_type}") from None
        start, end = time_window(self.as_of, start, end)
        snap = self.snapshot
        names = {m.member_id: m.name for m in snap.members}
        hits = []
        for m in snap.messages:
            if sender_id and m.sender_id != sender_id:
                continue
            if participant_id and participant_id != m.sender_id and participant_id not in m.recipient_ids:
                continue
            if channel and m.channel != channel:
                continue
            if channel_type and m.channel_type != channel_type:
                continue
            if thread_root_id and thread_root_id not in (m.message_id, m.reply_to_message_id):
                continue
            if not _in_window(m.sent_at, start, end):
                continue
            terms = match_terms(query, [m.text], match)
            if terms is None:
                continue
            hits.append(MessageHit(
                source_id=m.message_id, channel=m.channel, channel_type=m.channel_type, sender_id=m.sender_id,
                sender_name=names[m.sender_id], recipient_ids=m.recipient_ids, sent_at=m.sent_at, text=m.text,
                reply_to_message_id=m.reply_to_message_id, matched_terms=terms))
        items = order_and_limit(hits, lambda h: (h.sent_at, h.source_id), order, limit)
        return MessageSearchResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, total_matched=len(hits), items=items)
