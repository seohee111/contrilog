"""RuleBasedEvidenceEvaluator — 후보 기록 중 실제 판단 근거만 골라 관계(SUPPORTS/CONTRADICTS/CONTEXT)를 붙인다.

공통:
- 후보는 Claim 대상 용어와 관련 있어야 근거가 된다 (text.TermStatistics.is_relevant: 주제어 가중치의
  절반 이상 일치, 또는 드문 주제어 2개 이상 일치). Task는 반대로 Task 제목 용어가 Claim 대상에
  들어 있는지(절반 이상)로 판단한다.
- 기록량(리비전 수, 글자 수, 메시지 수)은 근거 선택·판정에 쓰지 않는다. 관련 기록은 모두 같은 자격이다.
- 근거가 보여 주는 '행위의 주체'(attributed_member_id)를 함께 남긴다. 다른 사람의 기여를 보여 주는
  기록은 주장자의 근거가 아니라 반박(CONTRADICTS)이거나 사용하지 않는다.

유형별 규칙:
- IDEA: 주장자의 제안 발언·메시지(direct), 주장자의 설계 문서화(documentation, 간접),
  타인의 '주장자 아이디어' 언급·동의(corroboration), Claim이 서술한 설계 문서 반영 결과(outcome).
  반박: 주장자보다 먼저 같은 대상을 제안한 다른 사람(prior_by_other),
        주장자 본인이 다른 사람의 아이디어라고 말한 기록(attribution_to_other).
  아이디어의 '처음 제안'은 한 사람에게 귀속되는 성격이라 반박 규칙이 있다.
- REVIEW: 주장자의 문제 지적 기록(direct), 지적에 대한 타인의 확인(corroboration),
  주장자를 언급한 이후 수정(outcome). 반박: 주장자보다 먼저 같은 문제를 지적한 다른 사람.
- EXECUTION: 주장자가 담당한 관련 Task의 문서에 주장자가 남긴 리비전(direct),
  Task 완료 상태·주장자의 완료 보고(completion). 관련 Task가 있으면 Task 상태가 완료의 공유 기록이므로,
  Task가 모두 미완료일 때의 '완료' 발화는 진행 보고로 본다 (그 Task의 완료 여부를 물은 질문의 답은 예외).
  공동 작업이 가능하므로 다른 사람의 작업은 반박이 아니다.
- SUPPORT: 다른 사람이 올린 문제 스레드에 주장자가 단 답장(direct), 같은 시기 주장자의 해결 리비전(direct),
  도움받은 사람의 확인·감사(corroboration).
- COORDINATION: 일정·순서 조정 단서가 있는 주장자의 기록(direct), 그 제안에 대한 동의 답장(corroboration).
"""

from datetime import timedelta

from contrilog.schemas import ContributionType as CT
from contrilog.schemas import EvidenceRelation as R
from contrilog.schemas import EvidenceSourceType as ST
from contrilog.schemas import ReplySemantic
from contrilog.schemas import VerificationGapKind as Gap

from . import text as T
from .protocols import AtomicClaimSpec, Candidate, EvaluationContext, EvidenceAssessment

TASK_TITLE_COVERAGE_MIN = 0.5
SUPPORT_WINDOW = timedelta(hours=48)


def _is_speech(c: Candidate) -> bool:
    return c.source_type in (ST.MEETING_UTTERANCE, ST.MESSAGE, ST.INBOUND_REPLY)


COUNTERPART_TYPES = (CT.SUPPORT, CT.REVIEW, CT.COORDINATION)

# 확인 응답에 부여된 근거 역할 → 응답 의미. 응답 해석의 '의미 체계'는 이 표 하나로 정해진다.
# 그 밖의 역할(본인 진행 보고, 언급만 있는 기록 등)은 확인하려던 사실에 답하지 않은 것으로 본다.
REPLY_SEMANTIC_BY_ROLE = {
    "completion": ReplySemantic.CONFIRMS_COMPLETION,
    "incomplete_report": ReplySemantic.REPORTS_INCOMPLETE,
    "counterpart_confirmation": ReplySemantic.CONFIRMS_COUNTERPART,
    "counterpart_denial": ReplySemantic.DENIES_COUNTERPART,
}


def reply_semantic(role: str) -> ReplySemantic:
    return REPLY_SEMANTIC_BY_ROLE.get(role, ReplySemantic.NOT_INFORMATIVE)


def _is_coordination_act(c: Candidate) -> bool:
    return sum(1 for g in T.COORDINATION_CUE_GROUPS if T.has_any(c.text + "\n" + c.match_text, g)) >= 2


class RuleBasedEvidenceEvaluator:
    # ---------------------------------------------------------------- 공통 도구
    def _relevant(self, atomic: AtomicClaimSpec, ctx: EvaluationContext, groups=None) -> list[Candidate]:
        groups = list(groups or atomic.topic)
        return sorted(
            (c for c in ctx.candidates.values()
             if c.source_type != ST.TASK and (ctx.stats.is_relevant(groups, c.match_text)
                                              or self._answers_this_claim(c, atomic, ctx))),
            key=lambda c: (c.at, c.source_id))

    @staticmethod
    def _answers_this_claim(c: Candidate, atomic: AtomicClaimSpec, ctx: EvaluationContext) -> bool:
        answer = ctx.answers.get(c.source_id)
        return answer is not None and answer.atomic_claim_id == atomic.atomic_claim_id

    def _related_tasks(self, atomic: AtomicClaimSpec, ctx: EvaluationContext) -> list[Candidate]:
        """주장자가 담당하고, 제목 용어가 Claim 대상에 들어 있는 Task."""
        names = {m.given_name for m in ctx.members.values()} | {m.name for m in ctx.members.values()}
        topic_text = T.normalize(" ".join(f for g in atomic.topic for f in g.forms))
        out = []
        for c in ctx.candidates.values():
            if c.source_type != ST.TASK or atomic.claimant_id not in c.actor_ids:
                continue
            title_groups = T.term_groups(T.content_terms(c.text.split(":")[0], names))
            if title_groups and ctx.stats.coverage(title_groups, topic_text) >= TASK_TITLE_COVERAGE_MIN:
                out.append(c)
        return sorted(out, key=lambda c: c.source_id)

    @staticmethod
    def _mentions(c: Candidate, ctx: EvaluationContext, member_id: str) -> bool:
        m = ctx.members[member_id]
        return any(n in (m.given_name, m.name) for n in T.MENTION_PATTERN.findall(f"{c.text}\n{c.match_text}"))

    @staticmethod
    def _a(c, relation, member, ctype, role, reason):
        return EvidenceAssessment(c, relation, member, ctype, role, reason)

    def assess(self, atomic: AtomicClaimSpec, ctx: EvaluationContext) -> list[EvidenceAssessment]:
        handler = {
            CT.IDEA: self._idea, CT.REVIEW: self._review, CT.EXECUTION: self._execution,
            CT.SUPPORT: self._support, CT.COORDINATION: self._coordination,
        }[atomic.contribution_type]
        found = self._counterpart(atomic, ctx) if atomic.contribution_type in COUNTERPART_TYPES else []
        found += handler(atomic, ctx)
        unanswered = [c for c in ctx.candidates.values()
                      if self._answers_this_claim(c, atomic, ctx) and c.source_id not in {a.candidate.source_id for a in found}]
        for c in unanswered:  # 확인 응답이 어떤 규칙에도 해당하지 않으면 '판단에 쓰지 않은 맥락'으로 남긴다
            found.append(self._a(c, R.CONTEXT, c.actor_ids[0], atomic.contribution_type, "unresolved_reply",
                                 "확인 응답이 이 주장을 지지하거나 반박하지 않음"))
        out, seen = [], set()
        for a in found:  # 같은 기록은 처음 부여된 역할 하나만
            if a.candidate.source_id not in seen:
                seen.add(a.candidate.source_id)
                out.append(a)
        return out

    # ---------------------------------------------------------------- 상대방 확인
    def _counterpart(self, atomic, ctx):
        me = atomic.claimant_id
        helped = set(atomic.mentioned_member_ids)
        out = []
        for c in self._relevant(atomic, ctx):
            if not _is_speech(c) or me in c.actor_ids or (helped and c.actor_ids[0] not in helped):
                continue
            if not self._mentions(c, ctx, me):
                continue
            if T.has_any(c.text, T.DENIAL_CUES):
                out.append(self._a(c, R.CONTRADICTS, c.actor_ids[0], atomic.contribution_type, "counterpart_denial",
                                   "상대방이 주장자의 관여를 부인"))
            elif T.has_any(c.text, T.COLLABORATION_CUES):
                out.append(self._a(c, R.SUPPORTS, me, atomic.contribution_type, "counterpart_confirmation",
                                   "상대방이 주장자의 관여를 직접 진술"))
        return out

    # ---------------------------------------------------------------- IDEA
    def _idea(self, atomic, ctx):
        me, ctype = atomic.claimant_id, CT.IDEA
        rel = self._relevant(atomic, ctx)
        out = []
        proposals = [c for c in rel if _is_speech(c) and T.has_any(c.text, T.PROPOSAL_CUES)
                     and not _is_coordination_act(c)]  # 일정·순서 조정 제안은 아이디어 제안이 아니다
        own_proposals = [c for c in proposals if me in c.actor_ids]
        own_docs = [c for c in rel if me in c.actor_ids and c not in own_proposals and (
            c.document_type == "DESIGN_DOC"
            or (c.source_type == ST.MESSAGE and "설계" in c.text and T.has_any(c.text, ("추가", "작성"))))]
        attributions = []
        for c in rel:
            if me in c.actor_ids:
                for name in T.ATTRIBUTION_PATTERN.findall(c.text):
                    other = ctx.member_by_given_name(name)
                    if other and other != me:
                        attributions.append((c, other))
        earliest = min((c.at for c in own_proposals + own_docs), default=None)

        for c in own_proposals:
            out.append(self._a(c, R.SUPPORTS, me, ctype, "direct", "주장자가 이 대상을 제안한 발언·메시지"))
        for c in rel:
            if me not in c.actor_ids and _is_speech(c) and self._mentions(c, ctx, me) and \
                    T.has_any(c.text, ("아이디어", "제안", "의견")):
                out.append(self._a(c, R.SUPPORTS, me, ctype, "corroboration", "다른 팀원이 주장자의 아이디어로 언급"))
        for p in own_proposals:  # 같은 회의에서 제안 직후 다른 팀원의 동의
            for c in rel:
                if c.meeting_id and c.meeting_id == p.meeting_id and c.at > p.at and me not in c.actor_ids \
                        and T.has_any(c.text, T.AGREEMENT_CUES):
                    out.append(self._a(c, R.SUPPORTS, me, ctype, "corroboration", "제안 직후 다른 팀원의 동의"))
        for c in own_docs:
            out.append(self._a(c, R.SUPPORTS, me, ctype, "documentation",
                               "주장자가 이 대상을 설계 문서에 정리한 기록 (제안 시점·제안자를 직접 보여 주지는 않음)"))
        if atomic.expects_outcome and own_proposals:
            first = min(c.at for c in own_proposals)
            for c in rel:  # 아이디어 채택은 설계 문서 반영으로 본다
                if c.document_type == "DESIGN_DOC" and me not in c.actor_ids and c.at > first:
                    out.append(self._a(c, R.SUPPORTS, c.actor_ids[0], ctype, "outcome",
                                       "Claim이 서술한 대로 제안 이후 설계 문서에 반영된 기록"))
        for c, other in attributions:
            out.append(self._a(c, R.CONTRADICTS, other, ctype, "attribution_to_other",
                               "주장자 본인이 이 아이디어를 다른 팀원의 것으로 언급"))
        for c in proposals:
            if me not in c.actor_ids and (earliest is None or c.at < earliest):
                out.append(self._a(c, R.CONTRADICTS, c.actor_ids[0], ctype, "prior_by_other",
                                   "주장자의 기록보다 먼저 다른 팀원이 같은 대상을 제안"))
        return out

    # ---------------------------------------------------------------- REVIEW
    def _review(self, atomic, ctx):
        me, ctype = atomic.claimant_id, CT.REVIEW
        rel = self._relevant(atomic, ctx)
        findings = [c for c in rel if me in c.actor_ids and T.has_any(c.text + c.match_text, T.PROBLEM_CUES)]
        out = [self._a(c, R.SUPPORTS, me, ctype, "direct", "주장자가 문제를 지적한 기록") for c in findings]
        if not findings:
            return out
        first = min(c.at for c in findings)
        finding_ids = {c.source_id for c in findings}
        for c in ctx.candidates.values():
            if c.reply_to in finding_ids and me not in c.actor_ids and T.has_any(c.text, T.AGREEMENT_CUES):
                out.append(self._a(c, R.SUPPORTS, me, ctype, "corroboration", "지적에 대한 다른 팀원의 확인"))
        for c in rel:
            if c.source_type == ST.DOCUMENT_REVISION and me not in c.actor_ids and c.at > first \
                    and self._mentions(c, ctx, me):
                out.append(self._a(c, R.SUPPORTS, c.actor_ids[0], ctype, "outcome",
                                   "지적 이후 주장자를 언급하며 수정한 리비전"))
        for c in rel:
            if me not in c.actor_ids and c.at < first and T.has_any(c.text, T.PROBLEM_CUES) and _is_speech(c):
                out.append(self._a(c, R.CONTRADICTS, c.actor_ids[0], ctype, "prior_by_other",
                                   "주장자보다 먼저 다른 팀원이 같은 문제를 지적"))
        return out

    # ---------------------------------------------------------------- EXECUTION
    def _execution(self, atomic, ctx):
        me, ctype = atomic.claimant_id, CT.EXECUTION
        tasks = self._related_tasks(atomic, ctx)
        out = []
        task_docs = {d for t in tasks for d in t.task_document_ids}
        if task_docs:
            work = [c for c in ctx.candidates.values()
                    if c.source_type == ST.DOCUMENT_REVISION and me in c.actor_ids and c.document_id in task_docs]
        else:
            work = [c for c in self._relevant(atomic, ctx)
                    if c.source_type == ST.DOCUMENT_REVISION and me in c.actor_ids]
        for c in sorted(work, key=lambda c: (c.at, c.source_id)):
            out.append(self._a(c, R.SUPPORTS, me, ctype, "direct", "주장자가 관련 결과물에 남긴 리비전"))
        for t in tasks:
            if t.task_status == "DONE":
                out.append(self._a(t, R.SUPPORTS, me, ctype, "completion", "주장자가 담당한 관련 Task가 완료 상태"))
            else:
                out.append(self._a(t, R.CONTEXT, me, ctype, "context", f"관련 Task가 아직 {t.task_status} 상태"))
        # 관련 Task가 있으면 완료 여부의 공유 기록은 Task 상태다. 관련 Task가 모두 미완료인데 나온 '완료' 발화는
        # 부분 진행 보고로 본다. 단, 그 Task의 완료 여부를 묻는 질문에 대한 답은 완료 진술로 본다 (질문 맥락).
        open_tasks_only = bool(tasks) and not any(t.task_status == "DONE" for t in tasks)
        for c in self._relevant(atomic, ctx):
            if _is_speech(c) and me in c.actor_ids:
                state = T.completion_state(c.text)
                answer = ctx.answers.get(c.source_id)
                if state is None and answer is not None and not ctx.stats.is_relevant(list(atomic.topic), c.match_text):
                    continue  # 질문 맥락 외에 주장과 이어지는 내용이 없는 응답은 근거로 쓰지 않는다
                answers_completion = answer is not None and answer.gap_kind == Gap.COMPLETION_UNCONFIRMED \
                    and answer.task_id in {t.source_id for t in tasks}
                if state == "complete" and open_tasks_only and not answers_completion:
                    out.append(self._a(c, R.SUPPORTS, me, ctype, "self_report",
                                       "주장자의 진행 보고 (관련 Task가 아직 완료 상태가 아니어서 완료 근거로 보지 않음)"))
                elif state == "complete":
                    out.append(self._a(c, R.SUPPORTS, me, ctype, "completion", "주장자의 완료·동작 보고"))
                elif state == "incomplete":
                    out.append(self._a(c, R.CONTEXT, me, ctype, "incomplete_report",
                                       "주장자가 아직 끝나지 않았다고 보고 (완료 근거 아님)"))
                else:
                    out.append(self._a(c, R.SUPPORTS, me, ctype, "self_report", "주장자의 진행 보고 (간접 근거)"))
        return out

    # ---------------------------------------------------------------- SUPPORT
    def _support(self, atomic, ctx):
        me, ctype = atomic.claimant_id, CT.SUPPORT
        helped = set(atomic.mentioned_member_ids)
        out = []
        roots = [c for c in self._relevant(atomic, ctx)
                 if c.source_type == ST.MESSAGE and me not in c.actor_ids
                 and (not helped or c.actor_ids[0] in helped) and T.has_any(c.text, T.PROBLEM_REPORT_CUES)]
        for root in roots:
            thread = sorted((c for c in ctx.candidates.values() if c.reply_to == root.source_id),
                            key=lambda c: (c.at, c.source_id))
            replies = [c for c in thread if me in c.actor_ids]
            if not replies:
                continue
            out.append(self._a(root, R.CONTEXT, root.actor_ids[0], ctype, "context", "지원 대상이 된 문제 보고"))
            for c in replies:
                out.append(self._a(c, R.SUPPORTS, me, ctype, "direct", "다른 팀원의 문제 스레드에 단 주장자의 진단·해결 답장"))
            reply_groups = T.term_groups(T.tokenize(" ".join(c.text for c in replies)))
            groups = list(atomic.topic) + reply_groups
            for c in self._relevant(atomic, ctx, groups):
                if c.source_type == ST.DOCUMENT_REVISION and me in c.actor_ids \
                        and root.at <= c.at <= root.at + SUPPORT_WINDOW:
                    out.append(self._a(c, R.SUPPORTS, me, ctype, "direct", "문제 보고 직후 주장자의 해결 리비전"))
            for c in thread:
                if c.actor_ids[0] == root.actor_ids[0] and c.at > replies[0].at and \
                        (self._mentions(c, ctx, me) or T.has_any(c.text, T.AGREEMENT_CUES)):
                    out.append(self._a(c, R.SUPPORTS, me, ctype, "corroboration", "도움받은 팀원의 해결 확인"))
        for c in self._relevant(atomic, ctx):  # 다른 팀원의 기록이 주장자를 언급 (예: 커밋 메시지의 리뷰어 표기)
            if me not in c.actor_ids and (not helped or c.actor_ids[0] in helped) and self._mentions(c, ctx, me):
                out.append(self._a(c, R.SUPPORTS, me, ctype, "corroboration",
                                   "도움받은 팀원의 기록이 주장자를 언급 (지원 내용을 직접 진술하지는 않음)"))
        return out

    # ---------------------------------------------------------------- COORDINATION
    def _coordination(self, atomic, ctx):
        me, ctype = atomic.claimant_id, CT.COORDINATION
        out = []
        direct = []
        for c in self._relevant(atomic, ctx):
            if me in c.actor_ids and _is_coordination_act(c):
                direct.append(c)
                out.append(self._a(c, R.SUPPORTS, me, ctype, "direct", "주장자가 일정·순서를 조정한 기록"))
        ids = {c.source_id for c in direct}
        for c in ctx.candidates.values():
            if c.reply_to in ids and me not in c.actor_ids and T.has_any(c.text, T.AGREEMENT_CUES):
                out.append(self._a(c, R.SUPPORTS, me, ctype, "corroboration", "조정안에 대한 다른 팀원의 동의"))
        return out
