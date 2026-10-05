"""SupportCandidateSelector — 막힌 Task를 도울 수 있는 팀원을 기록 근거로 찾는다.

사람 점수를 만들지 않는다. 각 팀원에 대해 '문제와 관련된 과거 기록', '이 담당자의 문제를 도운 기록',
'현재 본인 업무의 마감 상태'를 근거 ID와 함께 모으고, 다음 규칙으로 고른다.
1. 자격: 문제 맥락과 관련된 공개 기록이 1건 이상 있고, 본인 업무 마감이 임박하지 않았다.
2. 자격자가 여럿이면 '문제와 가장 관련 깊은 기록'이 더 관련 깊은 쪽 → 이 담당자를 도운 기록이 있는 쪽
   → 관련 기록이 더 최근인 쪽 순으로 정한다 (기록에 대한 비교이며 사람에 대한 평가가 아니다).
외부 승인·외부 의존 문제는 팀 내 지원으로 풀리지 않으므로 지원자를 고르지 않는다.
"""

from contrilog.schemas import SupportAnalysis, SupportCandidateAssessment

from ..claim_verification import text as T
from ..claim_verification.protocols import Candidate

PROBLEM_REPORT_CUES = T.PROBLEM_REPORT_CUES

# 문제 맥락에서 제외할 프로그래밍 공통 토큰 (언어 키워드·흔한 식별자). 어느 코드에나 나와서 관련성을 왜곡한다.
CODE_STOPWORDS = {
    "def", "return", "self", "none", "true", "false", "import", "from", "class", "const", "let", "var", "export",
    "function", "async", "await", "if", "else", "for", "in", "is", "not", "and", "or", "new", "int", "str", "bool",
    "dict", "list", "id", "ids", "value", "values", "get", "set", "post", "put", "router", "query", "filter", "map",
    "data", "args", "kwargs", "params", "at", "to", "of", "on", "by", "the", "start", "end", "dt", "ts", "q",
}


class SupportCandidateSelector:
    def __init__(self, urgent_due_hours: float = 24.0):
        self.urgent_due_hours = urgent_due_hours

    def select(self, *, at, block_kind: str, assignee_id: str, task_document_ids: set[str],
               context: list[Candidate], records: list[Candidate], tasks: list[Candidate],
               hours_until_due: dict[str, float], member_ids: list[str],
               stats: T.TermStatistics) -> SupportAnalysis:
        context_ids = [c.source_id for c in context]
        if block_kind == "EXTERNAL_DEPENDENCY":
            return SupportAnalysis(
                at=at, block_kind=block_kind, context_source_ids=context_ids,
                reason="외부 승인·외부 의존으로 막힌 문제라 팀 내 지원으로 해결되지 않음 → 지원 제안 안 함")
        terms = [t for t in T.content_terms(" ".join(c.text + "\n" + c.match_text for c in context), set())
                 if t not in CODE_STOPWORDS]
        groups = T.term_groups(terms)
        assessments = []
        for mid in sorted(member_ids):
            if mid == assignee_id:
                continue
            own = [r for r in records if mid in r.actor_ids and r.source_type.value != "TASK"]
            related = sorted((r for r in own if stats.is_relevant(groups, r.match_text)),
                             key=lambda r: (-stats.coverage(groups, r.match_text), -r.at.timestamp(), r.source_id))
            roots = {r.source_id for r in records if assignee_id in r.actor_ids and r.source_type.value == "MESSAGE"
                     and T.has_any(r.text, PROBLEM_REPORT_CUES)}
            prior_help = [r.source_id for r in own if r.reply_to in roots]
            open_tasks = [t for t in tasks if mid in t.actor_ids and t.task_status != "DONE"]
            urgent = [t.source_id for t in open_tasks if hours_until_due.get(t.source_id, 1e9) <= self.urgent_due_hours]
            notes = []
            if related:
                notes.append(f"문제 맥락과 관련된 기록 {', '.join(r.source_id for r in related)}")
            if prior_help:
                notes.append(f"이 담당자의 문제 스레드를 도운 기록 {', '.join(prior_help)}")
            if urgent:
                notes.append(f"본인 업무 {', '.join(urgent)} 마감 임박")
            assessments.append(SupportCandidateAssessment(
                member_id=mid, related_source_ids=[r.source_id for r in related],
                best_related_source_id=related[0].source_id if related else None, prior_help_source_ids=prior_help,
                open_task_ids=[t.source_id for t in open_tasks], urgent_task_ids=urgent, available=not urgent,
                eligible=bool(related) and not urgent, notes=notes))
        by_id = {r.source_id: r for r in records}
        eligible = [a for a in assessments if a.eligible]
        eligible.sort(key=lambda a: (-stats.coverage(groups, by_id[a.best_related_source_id].match_text),
                                     not a.prior_help_source_ids, -by_id[a.best_related_source_id].at.timestamp(),
                                     a.member_id))
        if not eligible:
            return SupportAnalysis(at=at, block_kind=block_kind, context_source_ids=context_ids,
                                   context_terms=[g.label for g in groups], candidates=assessments,
                                   reason="문제와 관련된 기록이 있고 지금 지원 가능한 팀원을 찾지 못함 → 지원 제안 안 함")
        chosen = eligible[0]
        others = [a.member_id for a in eligible[1:]]
        return SupportAnalysis(
            at=at, block_kind=block_kind, context_source_ids=context_ids, context_terms=[g.label for g in groups],
            candidates=assessments, selected_member_id=chosen.member_id,
            reason=(f"{chosen.member_id}: 문제와 가장 관련 깊은 기록 {chosen.best_related_source_id}"
                    + (f", 담당자를 도운 기록 {', '.join(chosen.prior_help_source_ids)}" if chosen.prior_help_source_ids else "")
                    + f", 마감 임박 업무 없음" + (f" (다른 자격자: {', '.join(others)})" if others else "")))
