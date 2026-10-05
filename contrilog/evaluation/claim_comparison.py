"""Claim 검증 결과(ClaimVerificationRun)와 Ground Truth 비교 (평가 계층 전용).

atomic claim은 (원본 claim_id, contribution type)으로 Ground Truth와 짝을 짓는다.
Agent 실행 경로는 이 모듈을 import 하지 않는다.
"""

from dataclasses import dataclass, field
from typing import Optional

from contrilog.schemas import ClaimVerificationRun
from contrilog.schemas.ground_truth import GroundTruthBundle


@dataclass
class AtomicComparison:
    claim_id: str
    contribution_type: str
    expected_status: Optional[str]  # None = Ground Truth에 없는 atomic claim (과분해)
    predicted_status: Optional[str]  # None = Agent가 만들지 않은 atomic claim (미분해)
    supporting_found: list[str] = field(default_factory=list)
    supporting_missing: list[str] = field(default_factory=list)
    contradicting_found: list[str] = field(default_factory=list)
    contradicting_missing: list[str] = field(default_factory=list)
    extra_evidence: list[str] = field(default_factory=list)  # Ground Truth에 없는 사용 근거
    inaccessible_cited: list[str] = field(default_factory=list)  # 접근 불가 기록 인용 (정책 위반)

    @property
    def status_match(self) -> bool:
        return self.expected_status is not None and self.expected_status == self.predicted_status


def compare_claim_run(run: ClaimVerificationRun, gt: GroundTruthBundle) -> list[AtomicComparison]:
    inaccessible = {i for c in gt.contributions for i in c.inaccessible_source_ids} | \
                   {i for s in gt.stagnations for i in s.inaccessible_source_ids}
    expected = {j.claimed_type.value: j for j in gt.claim_judgments if j.claim_id == run.submitted_claim_id}
    predicted = {r.predicted_contribution_type.value: r for r in run.atomic_results}
    out = []
    for ctype in sorted(set(expected) | set(predicted)):
        e, p = expected.get(ctype), predicted.get(ctype)
        sup = set(p.supporting_source_ids) if p else set()
        con = set(p.contradicting_source_ids) if p else set()
        used = sup | con | (set(p.context_source_ids) if p else set())
        exp_sup = set(e.expected_supporting_evidence_ids) if e else set()
        exp_con = set(e.expected_contradicting_evidence_ids) if e else set()
        out.append(AtomicComparison(
            claim_id=run.submitted_claim_id, contribution_type=ctype,
            expected_status=e.expected_status.value if e else None,
            predicted_status=p.predicted_status.value if p else None,
            supporting_found=sorted(exp_sup & sup), supporting_missing=sorted(exp_sup - sup),
            contradicting_found=sorted(exp_con & con), contradicting_missing=sorted(exp_con - con),
            extra_evidence=sorted((sup | con) - exp_sup - exp_con),
            inaccessible_cited=sorted(used & inaccessible)))
    return out


@dataclass
class InteractiveComparison:
    """Ground Truth의 interactive evidence 기대값 하나가 Agent 실행으로 충족되었는지."""

    owner_id: str  # GTC-* / GTS-*
    kind: str
    task_id: str
    responder_id: str
    satisfied: bool
    action_ids: list[str] = field(default_factory=list)
    reply_ids: list[str] = field(default_factory=list)
    note: str = ""


# 이 Agent(Claim 검증)가 수행할 수 있는 행동 종류. SUPPORT_REPLY는 지원 요청(사람 승인 필요)의 응답이라 범위 밖이다.
CLAIM_AGENT_INTERACTIVE_KINDS = {"CHECKIN_REPLY"}


def compare_interactions(runs: list[ClaimVerificationRun], gt: GroundTruthBundle,
                         owner_ids: set[str] | None = None) -> list[InteractiveComparison]:
    """기대값: (kind, task, responder). 충족: 그 사람에게 그 Task로 CheckIn을 보내 응답을 받고,
    그 응답(RPL)을 최종 판정의 근거(지지·반박·맥락)로 평가했다."""
    items = [(c.gt_contribution_id, x) for c in gt.contributions for x in c.expected_interactive_evidence] + \
            [(s.gt_stagnation_id, x) for s in gt.stagnations for x in s.expected_interactive_evidence]
    out = []
    for owner, x in items:
        if owner_ids is not None and owner not in owner_ids:
            continue
        if x.kind.value not in CLAIM_AGENT_INTERACTIVE_KINDS:
            out.append(InteractiveComparison(owner, x.kind.value, x.task_id, x.responder_id, False,
                                             note="Claim 검증 Agent의 행동 범위 밖 (지원 요청 응답)"))
            continue
        actions, replies = [], []
        for run in runs:
            final_sources = {e.source_id for e in run.evidence}
            for i in run.interactions:
                if i.tool_name == "CheckInTool" and i.task_id == x.task_id and i.target_member_id == x.responder_id:
                    used = [r for r in i.reply_ids if r in final_sources]
                    if used:
                        actions.append(i.action_id)
                        replies += used
        out.append(InteractiveComparison(owner, x.kind.value, x.task_id, x.responder_id, bool(replies),
                                         actions, replies))
    return out
