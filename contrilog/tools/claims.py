"""E. ClaimTool — as_of까지 제출된 원본 Claim과 Agent가 등록한 atomic claim 조회.

원본 Claim(origin=SUBMITTED)은 입력 데이터 그대로이며 수정할 수 없다.
Agent가 분리한 atomic claim(origin=AGENT_DERIVED)은 session 안에만 저장되고
parent_claim_id로 원본과 연결된다. 이 Tool은 claimed_type을 추론하지 않는다(호출자가 지정).
"""

from contrilog.schemas import ContributionClaim, ContributionType

from .base import Tool, ToolError, operation
from .results import ClaimListResult, ClaimView
from .text_match import MatchMode, match_terms


def _view(c: ContributionClaim, terms: list[str]) -> ClaimView:
    return ClaimView(
        source_id=c.claim_id, origin="AGENT_DERIVED" if c.parent_claim_id else "SUBMITTED",
        member_id=c.member_id, submitted_at=c.submitted_at, source=c.source, text=c.text,
        parent_claim_id=c.parent_claim_id, claimed_type=c.claimed_type, status=c.status, matched_terms=terms)


class ClaimTool(Tool):
    name = "ClaimTool"
    description = "as_of까지 제출된 기여 Claim(원본)과 Agent가 분리해 등록한 atomic claim을 조회한다."

    @operation
    def list_claims(
        self,
        member_id: str | None = None,
        query: str | None = None,
        include_agent_derived: bool = True,
        match: MatchMode = "all",
    ) -> ClaimListResult:
        self._member(member_id)
        claims = list(self.snapshot.claims)
        if include_agent_derived:
            claims += self._session._atomic_claims_visible()
        items = []
        for c in sorted(claims, key=lambda c: c.claim_id):
            if member_id and c.member_id != member_id:
                continue
            terms = match_terms(query, [c.text], match)
            if terms is not None:
                items.append(_view(c, terms))
        return ClaimListResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, total_matched=len(items), items=items)

    @operation
    def register_atomic_claim(
        self, parent_claim_id: str, claimed_type: ContributionType | str, text: str
    ) -> ClaimListResult:
        parent = next((c for c in self.snapshot.claims if c.claim_id == parent_claim_id), None)
        if parent is None:
            raise ToolError(f"claim {parent_claim_id} not found")
        try:
            claimed_type = ContributionType(claimed_type)
        except ValueError:
            raise ToolError(f"unknown claimed_type {claimed_type}") from None
        atomic = self._session._add_atomic_claim(parent, claimed_type, text)
        return ClaimListResult(tool_name=self.name, project_id=self.project_id, as_of=self.as_of, total_matched=1, items=[_view(atomic, [])])
