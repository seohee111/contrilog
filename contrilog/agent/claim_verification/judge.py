"""RuleBasedClaimJudge — 근거 관계로 atomic claim 상태를 정한다.

| 근거 상황 | 상태 |
|---|---|
| 반박 + (직접 또는 간접 지지) | CONFLICTING_EVIDENCE |
| 반박만 있고 주장자를 행위와 연결하는 지지 근거 없음 | INSUFFICIENT_EVIDENCE |
| 직접 지지 + 유형별 충분 조건 충족, 반박 없음 | VERIFIED |
| 지지 근거는 있으나 충분 조건 미충족 (간접 근거만, 또는 실행 완료 미확인) | PENDING_VERIFICATION |
| 관련 지지 근거 없음 | INSUFFICIENT_EVIDENCE |

유형별 충분 조건: EXECUTION은 직접 근거 + 완료 근거(Task 완료 또는 완료 보고)가 함께 필요하다.
SUPPORT·REVIEW·COORDINATION은 상대방의 직접 진술(counterpart_confirmation)도 직접 근거로 인정한다
(행위가 다른 사람을 향하므로 그 사람의 증언이 행위를 직접 보여 준다). IDEA·EXECUTION은 인정하지 않는다.

PENDING_VERIFICATION일 때는 이유를 GapDiagnosis로 함께 돌려준다 (판정 규칙의 두 분기와 1:1 대응):
- COMPLETION_UNCONFIRMED: EXECUTION 직접 근거는 있으나 완료 근거 없음
- DIRECT_EVIDENCE_MISSING: 간접 근거만 있음
INSUFFICIENT_EVIDENCE는 '기여하지 않았다'가 아니라 '현재 접근 가능한 기록으로는 지지되지 않는다'는 뜻이다.
근거의 개수·분량은 상태와 확신도에 쓰지 않는다 (확신도는 근거 '종류'의 다양성만 본다).
"""

from contrilog.schemas import ClaimStatus as CS
from contrilog.schemas import Confidence
from contrilog.schemas import ContributionType as CT
from contrilog.schemas import EvidenceRelation as R
from contrilog.schemas import VerificationGapKind as Gap

from .protocols import AtomicClaimSpec, EvidenceAssessment, GapDiagnosis, Judgment, MemberRef

TYPE_LABEL = {CT.IDEA: "아이디어 제안", CT.EXECUTION: "실행", CT.REVIEW: "검토·문제 지적",
              CT.SUPPORT: "지원", CT.COORDINATION: "일정·작업 조정"}
COUNTERPART_SUFFICIENT = (CT.SUPPORT, CT.REVIEW, CT.COORDINATION)


def _ids(items):
    return ", ".join(a.candidate.source_id for a in items) or "없음"


class RuleBasedClaimJudge:
    def judge(self, atomic: AtomicClaimSpec, assessments: list[EvidenceAssessment],
              members: dict[str, MemberRef]) -> Judgment:
        supports = [a for a in assessments if a.relation == R.SUPPORTS]
        direct_roles = {"direct", "counterpart_confirmation"} \
            if atomic.contribution_type in COUNTERPART_SUFFICIENT else {"direct"}
        direct = [a for a in supports if a.role in direct_roles]
        indirect = [a for a in supports if a.role not in direct_roles]
        incomplete = [a for a in assessments if a.role == "incomplete_report"]
        contra = [a for a in assessments if a.relation == R.CONTRADICTS]
        completion = [a for a in supports if a.role == "completion"]
        label = TYPE_LABEL[atomic.contribution_type]
        name = members[atomic.claimant_id].name

        if contra and supports:
            others = sorted({members[a.attributed_member_id].name for a in contra})
            return Judgment(
                CS.CONFLICTING_EVIDENCE, Confidence.MEDIUM,
                f"주장을 지지하는 기록({_ids(supports)})과 반박하는 기록({_ids(contra)})이 함께 있다. "
                f"반박 기록은 이 {label}을 {', '.join(others)}의 행위로 보여 준다.",
                (f"이 대상의 {label}을 처음 한 사람이 누구인지 당사자들에게 확인 필요 "
                 f"(지지: {_ids(supports)} / 반박: {_ids(contra)})",))
        if contra:
            others = sorted({members[a.attributed_member_id].name for a in contra})
            return Judgment(
                CS.INSUFFICIENT_EVIDENCE, Confidence.MEDIUM,
                f"접근 가능한 기록에서 {name}을(를) 이 {label}과 연결하는 지지 기록을 찾지 못했다. "
                f"관련 기록({_ids(contra)})은 {', '.join(others)}의 {label}을 보여 준다. "
                "이는 기여가 없었다는 뜻이 아니라 공유된 기록으로 확인되지 않는다는 뜻이다.",
                (f"{name}의 {label}이 공유되지 않은 경로(구두·개인 대화 등)에서 있었는지 확인 필요",))
        sufficient = bool(direct) and (atomic.contribution_type != CT.EXECUTION or bool(completion))
        if sufficient:
            kinds = {a.candidate.source_type for a in supports}
            confidence = Confidence.HIGH if len(kinds) >= 2 and indirect else Confidence.MEDIUM
            return Judgment(
                CS.VERIFIED, confidence,
                f"{name}의 {label}을 직접 보여 주는 기록({_ids(direct)})이 있고"
                + (f", 보강 기록({_ids(indirect)})이 있다." if indirect else " 반박 기록은 없다."))
        if supports:
            if atomic.contribution_type == CT.EXECUTION and direct:
                note = f" 담당자 보고({_ids(incomplete)})에 따르면 아직 끝나지 않았다." if incomplete else ""
                question = "관련 작업이 완료되었는지 확인 필요 (완료 Task·완료 보고 없음)" + note
                gap = GapDiagnosis(Gap.COMPLETION_UNCONFIRMED, "주장한 작업이 완료된 상태인지",
                                   tuple(direct + [a for a in assessments if a.role == "context"] + incomplete))
            else:
                question = f"간접 기록({_ids(indirect)})만 있어 {name}이(가) 직접 {label}했는지 확인 필요"
                gap = GapDiagnosis(Gap.DIRECT_EVIDENCE_MISSING, f"{name}이(가) 이 {label}을 직접 했는지",
                                   tuple(indirect))
            return Judgment(
                CS.PENDING_VERIFICATION, Confidence.LOW,
                f"지지 기록({_ids(supports)})은 있으나 {label}을 확정하기에 충분하지 않다.", (question,), (gap,))
        return Judgment(
            CS.INSUFFICIENT_EVIDENCE, Confidence.LOW,
            f"접근 가능한 기록에서 이 {label} 주장과 관련된 지지 기록을 찾지 못했다. "
            "기여가 없었다는 뜻이 아니라 공유된 기록으로 확인되지 않는다는 뜻이다.",
            (f"{name}에게 이 {label}의 결과물이나 기록 위치를 확인 필요",))
