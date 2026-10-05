"""RuleBasedInteractivePlanner — PENDING의 이유(GapDiagnosis)를 보고 '누구에게, 어떤 Task 맥락으로,
무엇을 물을지' 정한다. 해결할 수 없는 gap이면 이유와 함께 NoAction을 돌려준다.

확인 대상 선택 (기록 관계만 사용, Claim/Case/팀원 ID에 의존하지 않음):
- COMPLETION_UNCONFIRMED (실행 완료 미확인)
  완료 여부는 그 Task의 담당자가 안다. 근거에 나온 관련 Task 중 주장자가 담당자인 Task를 우선하고,
  없으면 직접 근거(리비전) 작성자 중 담당자를 고른다. 관련 Task가 근거에 없으면 직접 근거 문서를 가진 Task를 찾는다.
- DIRECT_EVIDENCE_MISSING (간접 근거만 있음)
  주장자 본인의 답은 다시 간접 근거(본인 보고)일 뿐이므로 묻지 않는다. 행위의 상대방에게 묻는다:
  1) Claim이 이름으로 지목한 팀원, 2) 간접 근거 기록의 주체(주장자 제외) 순서.
  상대방이 담당한 Task 중 근거 문서를 포함하는 Task, 없으면 Claim 대상과 관련된 Task를 맥락으로 쓴다.
CheckInTool은 Task 담당자에게만 보낼 수 있으므로, 대상이 담당한 관련 Task가 없으면 질문하지 않는다.

질문 의도(question_intent)는 gap에서 정해진다 (INTENT_FOR_GAP). 질문 문장은 의도를 사람에게 전달하는
표현일 뿐이며, 환경·평가는 문장이 아니라 의도를 본다.
- COMPLETION_UNCONFIRMED → COMPLETION_CONFIRMATION
- DIRECT_EVIDENCE_MISSING → COUNTERPART_CONFIRMATION
  단 상대방의 진술로 직접 근거가 되는 유형(judge.COUNTERPART_SUFFICIENT)에서만 묻는다. 아이디어·실행은
  상대방이 확인해도 판정 규칙상 해결되지 않으므로 질문하지 않는다.

질문은 확인할 사실 하나만 묻는다. 문구는 Claim 원문, 주장자 이름(Tool로 조회), Task 제목에서 만든다.
같은 (atomic claim, gap 종류, 대상, Task) 조합은 다시 묻지 않는다.
"""

from contrilog.schemas import EvidenceSourceType as ST
from contrilog.schemas import QuestionIntent
from contrilog.schemas import VerificationGapKind as Gap

from .judge import COUNTERPART_SUFFICIENT, TYPE_LABEL
from .protocols import AtomicClaimSpec, Candidate, EvaluationContext, GapDiagnosis, NoAction, PlannedCheckIn


INTENT_FOR_GAP = {
    Gap.COMPLETION_UNCONFIRMED: QuestionIntent.COMPLETION_CONFIRMATION,
    Gap.DIRECT_EVIDENCE_MISSING: QuestionIntent.COUNTERPART_CONFIRMATION,
}


def task_title(task: Candidate) -> str:
    return task.text.split(":")[0].strip()


def ask_key(atomic: AtomicClaimSpec, gap_kind, member_id: str, task_id: str) -> tuple:
    return (atomic.atomic_claim_id, gap_kind, member_id, task_id)


class RuleBasedInteractivePlanner:
    def plan(self, gap: GapDiagnosis, atomic: AtomicClaimSpec, ctx: EvaluationContext,
             already_asked: set[tuple]) -> PlannedCheckIn | NoAction:
        if gap.kind == Gap.COMPLETION_UNCONFIRMED:
            options = self._completion_options(gap, atomic, ctx)
            if not options:
                return NoAction("완료 여부를 물을 관련 Task가 없음 (CheckInTool은 Task 담당자에게만 보낼 수 있음)")
        else:
            counterparts = self._counterparts(gap, atomic)
            if not counterparts:
                return NoAction("간접 근거가 주장자 본인의 기록뿐이라 확인해 줄 상대방을 기록에서 식별할 수 없음")
            if atomic.contribution_type not in COUNTERPART_SUFFICIENT:
                return NoAction(f"{TYPE_LABEL[atomic.contribution_type]}은(는) 상대방의 확인으로 직접 근거가 되지 않아 "
                                "질문해도 판정이 해결되지 않음")
            options = self._counterpart_options(counterparts, gap, atomic, ctx)
            if not options:
                return NoAction("상대방이 담당한 관련 Task가 없어 CheckInTool로 물을 수 없음")
        for member_id, task, reason in options:
            if ask_key(atomic, gap.kind, member_id, task.source_id) in already_asked:
                continue
            return PlannedCheckIn(member_id, task.source_id, self.question_text(gap, atomic, ctx, task), reason,
                                  INTENT_FOR_GAP[gap.kind])
        return NoAction("같은 사람에게 같은 확인을 이미 보냈음 (반복 질문 안 함)")

    # ---------------------------------------------------------------- 대상 선택
    def _completion_options(self, gap, atomic, ctx):
        me = atomic.claimant_id
        basis_ids = [a.candidate.source_id for a in gap.basis]
        tasks = [a.candidate for a in gap.basis if a.candidate.source_type == ST.TASK]
        if not tasks:
            docs = {a.candidate.document_id for a in gap.basis if a.candidate.document_id}
            tasks = [t for t in ctx.tasks.values() if docs & set(t.task_document_ids)]
        work_authors = [a.candidate.actor_ids[0] for a in gap.basis if a.role == "direct"]
        options = []
        for t in sorted(tasks, key=lambda t: t.source_id):
            if me in t.actor_ids:
                options.append((me, t, f"주장자가 '{task_title(t)}' 담당자라 완료 여부를 직접 확인할 수 있음 "
                                       f"(근거: {', '.join(basis_ids)})"))
            for author in dict.fromkeys(work_authors):
                if author != me and author in t.actor_ids:
                    options.append((author, t, f"직접 근거 작성자이자 '{task_title(t)}' 담당자 "
                                               f"(근거: {', '.join(basis_ids)})"))
        return options

    @staticmethod
    def _counterparts(gap, atomic) -> list[tuple[str, str]]:
        me = atomic.claimant_id
        out = [(m, "Claim이 행위의 상대방으로 지목한 팀원") for m in atomic.mentioned_member_ids if m != me]
        for a in gap.basis:
            for actor in a.candidate.actor_ids:
                if actor != me and actor not in [m for m, _ in out]:
                    out.append((actor, f"간접 근거 {a.candidate.source_id}의 주체"))
        return out

    @staticmethod
    def _counterpart_options(counterparts, gap, atomic, ctx):
        basis_docs = {a.candidate.document_id for a in gap.basis if a.candidate.document_id}
        basis_ids = ", ".join(a.candidate.source_id for a in gap.basis)
        options = []
        for member_id, why in counterparts:
            owned = sorted((t for t in ctx.tasks.values() if member_id in t.actor_ids), key=lambda t: t.source_id)
            linked = [t for t in owned if basis_docs & set(t.task_document_ids)]
            topical = [t for t in owned if t not in linked and ctx.stats.is_relevant(list(atomic.topic), t.match_text)]
            for t in linked:
                options.append((member_id, t, f"{why}; 근거 문서가 이 사람이 담당한 '{task_title(t)}'에 속함 (근거: {basis_ids})"))
            for t in topical:
                options.append((member_id, t, f"{why}; 이 사람이 담당한 '{task_title(t)}'가 Claim 대상과 관련됨 (근거: {basis_ids})"))
        return options

    # ---------------------------------------------------------------- 질문
    @staticmethod
    def question_text(gap, atomic, ctx, task) -> str:
        """사람에게 보여 줄 문장. 하위 클래스에서 표현만 바꿀 수 있다 (의도는 바뀌지 않는다)."""
        claimant = ctx.members[atomic.claimant_id].name
        if gap.kind == Gap.COMPLETION_UNCONFIRMED:
            return (f"제출된 기여 내역 \"{atomic.text}\"을 확인하고 있어요. "
                    f"'{task_title(task)}' 작업이 지금 완료된 상태인지 알려 주세요.")
        label = TYPE_LABEL[atomic.contribution_type]
        return (f"{claimant}님이 제출한 기여 내역 \"{atomic.text}\"을 확인하고 있어요. "
                f"'{task_title(task)}' 작업에서 {claimant}님이 실제로 {label}에 참여했는지 알려 주세요.")
