"""RuleBasedSearchPlanner — 기여 유형별 검색 정책 표.

정책은 Contribution Type과 atomic claim의 속성(주장자, 대상 용어, 결과 서술 여부)에만 의존한다.
Claim ID, Case 번호, 특정 기록 ID는 사용하지 않는다.
"""

from contrilog.schemas import ContributionType as CT

from .protocols import AtomicClaimSpec, SearchRequest

MAX_LIMIT = 200

# (tool, operation, 파라미터 템플릿, 목적). 템플릿 값 "{claimant}"는 주장자, "{query}"는 대상 용어로 채운다.
SEARCH_POLICY: dict[CT, list[tuple[str, str, dict, str]]] = {
    CT.IDEA: [
        ("MeetingSearchTool", "search", {"query": "{query}"}, "회의에서 처음 제안한 사람 확인"),
        ("MessageSearchTool", "search", {"query": "{query}"}, "채널에서 처음 제안한 사람 확인"),
        ("DocumentHistoryTool", "search", {"query": "{query}", "document_type": "DESIGN_DOC"}, "설계 문서화·반영 확인"),
    ],
    CT.EXECUTION: [
        ("ProjectStatusTool", "get_status", {"member_id": "{claimant}"}, "주장자가 담당한 관련 Task와 완료 상태"),
        ("DocumentHistoryTool", "search", {"author_id": "{claimant}"}, "주장자가 작성한 결과물 리비전"),
        ("MessageSearchTool", "search", {"sender_id": "{claimant}", "query": "{query}"}, "주장자의 진행·완료 보고"),
        ("MeetingSearchTool", "search", {"speaker_id": "{claimant}", "query": "{query}"}, "회의 진행 보고"),
    ],
    CT.REVIEW: [
        ("MessageSearchTool", "search", {"query": "{query}"}, "문제를 처음 지적한 기록"),
        ("MeetingSearchTool", "search", {"query": "{query}"}, "회의에서 문제를 지적한 기록"),
        ("DocumentHistoryTool", "search", {"query": "{query}"}, "검토 기록 및 이후 수정 리비전"),
    ],
    CT.SUPPORT: [
        ("MessageSearchTool", "search", {"query": "{query}"}, "도움이 필요했던 문제 스레드"),
        ("MessageSearchTool", "search", {"sender_id": "{claimant}"}, "주장자의 지원 메시지"),
        ("DocumentHistoryTool", "search", {"author_id": "{claimant}"}, "주장자의 해결 리비전"),
        ("DocumentHistoryTool", "search", {"query": "{query}"}, "도움받은 쪽의 해결 기록 (주장자 언급 여부)"),
    ],
    CT.COORDINATION: [
        ("MessageSearchTool", "search", {"query": "{query}"}, "일정·순서 조정 제안 메시지"),
        ("MeetingSearchTool", "search", {"query": "{query}"}, "회의에서의 조정 합의"),
        ("DocumentHistoryTool", "search", {"document_type": "SCHEDULE"}, "일정표 변경 이력"),
        ("ProjectStatusTool", "get_status", {}, "Task 마감·의존 관계"),
    ],
}

OUTCOME_STEP = ("DocumentHistoryTool", "search", {"query": "{query}"}, "Claim에 서술된 결과(반영·수정) 확인")


def _fill(template: dict, atomic: AtomicClaimSpec) -> dict:
    query = " ".join(sorted({f for g in atomic.topic for f in g.forms}))
    params = {}
    for k, v in template.items():
        if v == "{claimant}":
            params[k] = atomic.claimant_id
        elif v == "{query}":
            if not query:
                continue
            params[k] = query
            params["match"] = "any"
        else:
            params[k] = v
    return params


class RuleBasedSearchPlanner:
    def plan(self, atomic: AtomicClaimSpec) -> list[SearchRequest]:
        steps = list(SEARCH_POLICY[atomic.contribution_type])
        if atomic.expects_outcome and OUTCOME_STEP not in steps:
            steps.append(OUTCOME_STEP)
        out = []
        for tool, op, template, purpose in steps:
            params = _fill(template, atomic)
            if op == "search":
                params["limit"] = MAX_LIMIT
            out.append(SearchRequest(tool, op, params, purpose))
        return out
