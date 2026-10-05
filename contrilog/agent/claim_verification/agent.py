"""ClaimVerificationAgent — 제출된 Contribution Claim 하나를 검증한다.

    session = ToolSession("P001", as_of=...)
    agent = ClaimVerificationAgent(tools=session.tools)
    run = agent.verify_claim(claim_id="CLM-06")          # 최초 라운드 (필요하면 확인 질문을 보낸다)
    # ... 환경(session)의 시간이 흐른다 (Agent는 시간을 옮기지 않는다)
    run = agent.continue_verification(run)              # 응답이 왔으면 근거로 평가해 재판정
    run = agent.finalize(run)                           # 환경이 대기를 끝내면 남은 질문을 '응답 없음'으로 닫는다

접근 경계:
- Agent는 생성자로 받은 Agent-facing Tool(mapping)만 사용한다. session·snapshot·입력 파일·
  시뮬레이션·Ground Truth에는 접근하지 않는다 (tests/test_claim_agent_boundary.py가 정적·실행 검사).
- 모든 조회·행동은 Tool 호출이므로 session의 ToolCallLog에 자동으로 남는다.
- 시각(as_of)은 환경(session)이 정한다. 사람의 응답은 시간이 지나야 오므로, 응답 관찰은
  환경이 시간을 옮긴 뒤 continue_verification으로 이어진다 (contrilog.runtime.interactive 참고).
- 이 Agent가 하는 사람 대상 행동은 CheckInTool.send(확인 질문)뿐이다. 지원 요청·승인·재배정은 하지 않는다.

라운드 = Observe → Reason → Plan/Act
  Observe : 검색 계획대로 공개 기록을 조회하고, 보낸 질문의 응답(RPL-*)을 InboxTool로 받는다
  Reason  : 같은 EvidenceEvaluator로 근거를 평가하고 같은 ClaimJudge로 판정한다. PENDING이면 이유(gap)를 얻는다
  Plan/Act: InteractiveVerificationPlanner가 gap별로 대상·질문을 정하면 CheckInTool로 묻는다
최초 라운드 이후 응답이 도착할 때마다 같은 라운드를 다시 수행한다 (재판정).
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from contrilog.schemas import (
    AgentDecision,
    AtomicClaimResult,
    AtomicRoundState,
    ClaimStatus,
    ClaimVerificationRun,
    Confidence,
    ContributionClaim,
    ContributionEvidence,
    DecisionType,
    EvidenceRelation,
    InteractionRecord,
    InteractionStatus,
    ReplyInterpretation,
    RoundEvidence,
    SearchStep,
    VerificationGap,
    VerificationRound,
)

from .candidates import from_reply, from_result
from .decomposer import DeterministicClaimDecomposer
from .evaluator import RuleBasedEvidenceEvaluator, reply_semantic
from .interactive import RuleBasedInteractivePlanner, ask_key
from .judge import RuleBasedClaimJudge
from .planner import MAX_LIMIT, RuleBasedSearchPlanner
from .protocols import (
    AnswerContext,
    AtomicClaimSpec,
    Candidate,
    ClaimDecomposer,
    ClaimJudge,
    EvaluationContext,
    EvidenceAssessment,
    EvidenceEvaluator,
    EvidenceSearchPlanner,
    InteractiveVerificationPlanner,
    Judgment,
    MemberRef,
    PlannedCheckIn,
    SubmittedClaim,
)
from .text import TermStatistics, term_groups

# Agent가 쓸 수 있는 Tool operation (명시적 목록). 사람 대상 행동은 확인 질문(CheckInTool.send)과
# 그 응답 조회(InboxTool.list_replies)뿐이다. 지원 요청·승인·시간 이동은 이 Agent에 없다.
TOOL_OPERATIONS = {
    ("ClaimTool", "list_claims"): lambda t, p: t.list_claims(**p),
    ("ClaimTool", "register_atomic_claim"): lambda t, p: t.register_atomic_claim(**p),
    ("ProjectStatusTool", "get_status"): lambda t, p: t.get_status(**p),
    ("MeetingSearchTool", "search"): lambda t, p: t.search(**p),
    ("DocumentHistoryTool", "search"): lambda t, p: t.search(**p),
    ("MessageSearchTool", "search"): lambda t, p: t.search(**p),
    ("CheckInTool", "send"): lambda t, p: t.send(**p),
    ("InboxTool", "list_replies"): lambda t, p: t.list_replies(**p),
}

# atomic claim 하나에 보낼 수 있는 확인 질문 수.
# Judge가 PENDING을 내는 이유(gap 종류)가 두 가지이고 gap 하나는 사실 하나만 확인하므로,
# '종류별 한 번'이 상한이다 (예: 상대방 확인으로 직접 근거가 생긴 뒤 완료 여부가 남는 경우).
MAX_CHECKINS_PER_ATOMIC = 2

# 여러 atomic 결과를 하나로 요약할 때의 우선순위 (사람의 확인이 더 필요한 상태가 앞)
_OVERALL_ORDER = [ClaimStatus.CONFLICTING_EVIDENCE, ClaimStatus.PENDING_VERIFICATION,
                  ClaimStatus.INSUFFICIENT_EVIDENCE, ClaimStatus.VERIFIED]
_CONFIDENCE_ORDER = [Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH]
EXCERPT_CHARS = 120


class ClaimNotFoundError(LookupError):
    """as_of 시점에 제출되어 있지 않거나 존재하지 않는 Claim."""


@dataclass
class _Evaluation:
    """한 라운드에서 atomic claim 하나에 대한 평가 결과."""

    as_of: datetime
    assessments: list[EvidenceAssessment]
    judgment: Judgment


@dataclass
class _RunState:
    run_no: int
    run_id: str
    project_id: str
    claim: SubmittedClaim
    claim_source: Any
    specs: list[AtomicClaimSpec]
    steps: list[SearchStep]
    as_of: datetime
    members: dict[str, MemberRef] = field(default_factory=dict)
    rounds: list[VerificationRound] = field(default_factory=list)
    evaluations: list[dict[str, _Evaluation]] = field(default_factory=list)  # 라운드별
    interactions: dict[str, InteractionRecord] = field(default_factory=dict)
    answers: dict[str, AnswerContext] = field(default_factory=dict)
    reply_candidates: dict[str, Candidate] = field(default_factory=dict)
    checkin_decisions: list[tuple] = field(default_factory=list)
    checkins_per_atomic: Counter = field(default_factory=Counter)


class ClaimVerificationAgent:
    def __init__(
        self,
        tools: Mapping[str, Any],
        decomposer: ClaimDecomposer | None = None,
        planner: EvidenceSearchPlanner | None = None,
        evaluator: EvidenceEvaluator | None = None,
        judge: ClaimJudge | None = None,
        interactive_planner: InteractiveVerificationPlanner | None = None,
        interactive: bool = True,
    ):
        self.tools = tools
        self.decomposer = decomposer or DeterministicClaimDecomposer()
        self.planner = planner or RuleBasedSearchPlanner()
        self.evaluator = evaluator or RuleBasedEvidenceEvaluator()
        self.judge = judge or RuleBasedClaimJudge()
        self.interactive_planner = interactive_planner or RuleBasedInteractivePlanner()
        self.interactive = interactive
        self._runs = 0
        self._states: dict[str, _RunState] = {}
        self._asked: dict[tuple, str] = {}  # ask_key → action_id (이 Agent가 보낸 모든 확인 질문)

    # ------------------------------------------------------------------ public
    def verify_claim(self, claim_id: str, as_of: datetime | None = None) -> ClaimVerificationRun:
        steps: list[SearchStep] = []
        claims = self._call(steps, None, "ClaimTool", "list_claims", {}, "제출된 Claim 조회")
        current = claims.as_of
        if as_of is not None and as_of != current:
            raise ValueError(f"as_of {as_of.isoformat()} differs from the tool environment ({current.isoformat()})")
        submitted = next((c for c in claims.items if c.source_id == claim_id and c.origin == "SUBMITTED"), None)
        if submitted is None:
            raise ClaimNotFoundError(f"claim {claim_id} is not available at {current.isoformat()}")
        claim = SubmittedClaim(submitted.source_id, submitted.member_id, submitted.submitted_at, submitted.text)

        status = self._call(steps, None, "ProjectStatusTool", "get_status", {}, "팀원 목록 및 Task 현황")
        members = {m.member_id: MemberRef(m.member_id, m.name) for m in status.members}
        self._runs += 1
        state = _RunState(
            run_no=self._runs, run_id=f"CVR-{self._runs:03d}", project_id=claims.project_id, claim=claim,
            claim_source=submitted.source, specs=[], steps=steps, as_of=current, members=members)
        stats = self._term_statistics(steps, status)
        state.specs = self._register_atomics(steps, claim, members, claims.items)
        self._states[state.run_id] = state
        self._attach_previous_questions(state)
        self._round(state, "INITIAL", "최초 검증", status=status, stats=stats)
        return self._build_run(state)

    def continue_verification(self, run: ClaimVerificationRun) -> ClaimVerificationRun:
        """환경의 시간이 흐른 뒤 호출한다. 응답이 도착했으면 근거로 평가해 재판정한다."""
        state = self._state_of(run)
        new_replies = self._poll(state)
        if new_replies:
            self._round(state, "REEVALUATION", f"확인 응답 수신 ({', '.join(new_replies)})", new_replies=new_replies)
        return self._build_run(state)

    def finalize(self, run: ClaimVerificationRun) -> ClaimVerificationRun:
        """환경이 대기를 끝냈을 때 호출한다. 남은 질문을 '응답 없음'으로 닫는다 (판정은 바꾸지 않는다)."""
        state = self._state_of(run)
        new_replies = self._poll(state)
        if new_replies:
            self._round(state, "REEVALUATION", f"확인 응답 수신 ({', '.join(new_replies)})", new_replies=new_replies,
                        allow_actions=False)
        closed = [i for i in state.interactions.values() if i.status == InteractionStatus.AWAITING_REPLY]
        for i in closed:
            state.interactions[i.action_id] = i.model_copy(update={"status": InteractionStatus.NO_REPLY})
        if closed:
            last = state.rounds[-1]
            gaps = [g.model_copy(update={"unresolvable_reason": "확인 질문에 대한 응답이 대기 시간 안에 오지 않음"})
                    if g.action_id in {i.action_id for i in closed} else g for g in last.gaps]
            state.rounds.append(VerificationRound(
                round=len(state.rounds) + 1, phase="FINAL", as_of=state.as_of,
                trigger=f"응답 대기 종료 ({', '.join(i.action_id for i in closed)} 응답 없음)",
                atomic_states=last.atomic_states, gaps=gaps))
        return self._build_run(state)

    # ------------------------------------------------------------------ round
    def _round(self, state: _RunState, phase: str, trigger: str, *, status=None, stats=None,
               new_replies=(), allow_actions=True) -> None:
        steps = state.steps
        # ---- Observe: 공개 기록 + 받은 응답
        if status is None:
            status = self._call(steps, None, "ProjectStatusTool", "get_status", {}, "재판정 시점의 팀원·Task 현황")
            stats = self._term_statistics(steps, status)
        tasks = {c.source_id: c for c in from_result(status)}
        evaluations: dict[str, _Evaluation] = {}
        planned: list[tuple[AtomicClaimSpec, Judgment, EvaluationContext]] = []
        for spec in state.specs:
            pool = self._collect(steps, spec)
            for reply_id, cand in state.reply_candidates.items():
                if state.answers[reply_id].atomic_claim_id == spec.atomic_claim_id:
                    pool[reply_id] = cand
            ctx = EvaluationContext(stats, state.members, pool, tasks, dict(state.answers))
            # ---- Reason: 같은 Evaluator, 같은 Judge
            assessments = self.evaluator.assess(spec, ctx)
            judgment = self.judge.judge(spec, assessments, state.members)
            evaluations[spec.atomic_claim_id] = _Evaluation(state.as_of, assessments, judgment)
            planned.append((spec, judgment, ctx))
        state.evaluations.append(evaluations)
        self._record_interpretations(state, evaluations, round_no=len(state.rounds) + 1)

        # ---- Plan/Act: gap별 확인 행동
        gaps: list[VerificationGap] = []
        action_ids: list[str] = []
        for spec, judgment, ctx in planned:
            for gap in judgment.gaps:
                record = self._act_on_gap(state, spec, gap, ctx, allow_actions)
                gaps.append(record)
                if record.action_id and record.action_id not in action_ids and \
                        state.interactions[record.action_id].sent_at == state.as_of:
                    action_ids.append(record.action_id)

        state.rounds.append(VerificationRound(
            round=len(state.rounds) + 1, phase=phase, as_of=state.as_of, trigger=trigger,
            new_reply_ids=list(new_replies),
            atomic_states=[AtomicRoundState(
                atomic_claim_id=sid, status=ev.judgment.status, confidence=ev.judgment.confidence,
                evidence=[RoundEvidence(source_id=a.candidate.source_id, relation=a.relation, role=a.role,
                                        attributed_member_id=a.attributed_member_id) for a in ev.assessments],
                gap_kinds=[g.kind for g in ev.judgment.gaps]) for sid, ev in evaluations.items()],
            gaps=gaps, action_ids=action_ids))

    def _act_on_gap(self, state, spec, gap, ctx, allow_actions) -> VerificationGap:
        basis = [a.candidate.source_id for a in gap.basis]
        base = dict(atomic_claim_id=spec.atomic_claim_id, kind=gap.kind, description=gap.fact_to_confirm,
                    basis_source_ids=basis)
        # 이미 이 gap을 확인하려고 보낸 질문이 응답 대기 중이면 기다린다
        pending = [i for i in state.interactions.values() if i.atomic_claim_id == spec.atomic_claim_id
                   and i.gap_kind == gap.kind and i.status == InteractionStatus.AWAITING_REPLY]
        if pending:
            return VerificationGap(**base, resolvable=True, action_id=pending[0].action_id)
        if not self.interactive or not allow_actions:
            return VerificationGap(**base, resolvable=False, unresolvable_reason="이 실행에서는 확인 행동을 하지 않음")
        if state.checkins_per_atomic[spec.atomic_claim_id] >= MAX_CHECKINS_PER_ATOMIC:
            return VerificationGap(**base, resolvable=False,
                                   unresolvable_reason=f"atomic claim당 확인 질문 상한({MAX_CHECKINS_PER_ATOMIC}) 도달")
        plan = self.interactive_planner.plan(gap, spec, ctx, set(self._asked))
        if not isinstance(plan, PlannedCheckIn):
            answered = [i.action_id for i in state.interactions.values()
                        if i.atomic_claim_id == spec.atomic_claim_id and i.gap_kind == gap.kind]
            reason = plan.reason + (f" — 이미 받은 응답({', '.join(answered)})으로도 해결되지 않음" if answered else "")
            return VerificationGap(**base, resolvable=False, unresolvable_reason=reason)
        action_id = self._send_checkin(state, spec, gap, plan)
        return VerificationGap(**base, resolvable=True, action_id=action_id)

    # ------------------------------------------------------------------ act / observe replies
    def _send_checkin(self, state, spec, gap, plan: PlannedCheckIn) -> str:
        result = self._call(state.steps, spec.atomic_claim_id, "CheckInTool", "send",
                            {"task_id": plan.task_id, "member_id": plan.target_member_id, "question": plan.question,
                             "question_intent": plan.question_intent.value},
                            f"확인 질문({plan.question_intent.value}): {gap.fact_to_confirm}")
        action = result.actions[0]
        state.interactions[action.action_id] = InteractionRecord(
            action_id=action.action_id, atomic_claim_id=spec.atomic_claim_id, gap_kind=gap.kind,
            question_intent=plan.question_intent,
            tool_name="CheckInTool", operation="send", target_member_id=plan.target_member_id,
            task_id=plan.task_id, question=plan.question, target_reason=plan.target_reason,
            sent_at=result.as_of, status=InteractionStatus.AWAITING_REPLY)
        state.checkins_per_atomic[spec.atomic_claim_id] += 1
        state.checkin_decisions.append((result.as_of, spec, gap, plan, action.action_id))
        self._asked[ask_key(spec, gap.kind, plan.target_member_id, plan.task_id)] = action.action_id
        return action.action_id

    @staticmethod
    def _record_interpretations(state, evaluations, round_no) -> None:
        """받은 응답 각각을 이번 라운드의 근거 평가에서 어떻게 해석했는지 interaction에 남긴다."""
        for reply_id, answer in state.answers.items():
            ev = evaluations.get(answer.atomic_claim_id)
            a = next((x for x in ev.assessments if x.candidate.source_id == reply_id), None) if ev else None
            if a is None:
                continue
            record = state.interactions[answer.action_id]
            others = [r for r in record.reply_interpretations if r.reply_id != reply_id]
            state.interactions[answer.action_id] = record.model_copy(update={"reply_interpretations": others + [
                ReplyInterpretation(reply_id=reply_id, round=round_no, role=a.role, relation=a.relation,
                                    semantic=reply_semantic(a.role))]})

    def _attach_previous_questions(self, state) -> None:
        """같은 Claim을 다시 검증할 때, 이 Agent가 이전 실행에서 보낸 질문을 이어받는다 (다시 묻지 않는다)."""
        for prev in self._states.values():
            if prev is state or prev.claim.claim_id != state.claim.claim_id:
                continue
            for i in prev.interactions.values():
                if i.atomic_claim_id in {s.atomic_claim_id for s in state.specs}:
                    state.interactions.setdefault(i.action_id, i.model_copy(update={
                        "status": InteractionStatus.AWAITING_REPLY, "reply_ids": [], "reply_interpretations": []}))
                    state.checkins_per_atomic[i.atomic_claim_id] += 1
        if state.interactions:
            self._poll(state)

    def _poll(self, state) -> list[str]:
        """보낸 질문의 응답을 InboxTool로 확인한다. 새로 도착한 reply_id 목록을 돌려준다."""
        if not state.interactions:
            return []
        result = self._call(state.steps, None, "InboxTool", "list_replies", {}, "보낸 확인 질문의 응답 확인")
        state.as_of = result.as_of
        new = []
        for reply in result.replies:
            record = state.interactions.get(reply.action_id)
            if record is None or reply.reply_id in state.answers:
                continue
            state.answers[reply.reply_id] = AnswerContext(
                reply.reply_id, reply.action_id, record.atomic_claim_id, record.gap_kind, record.target_member_id,
                record.task_id)
            state.reply_candidates[reply.reply_id] = from_reply(reply)
            state.interactions[reply.action_id] = record.model_copy(update={
                "status": InteractionStatus.ANSWERED, "reply_ids": record.reply_ids + [reply.reply_id]})
            new.append(reply.reply_id)
        for aid, record in state.interactions.items():
            state.interactions[aid] = record.model_copy(update={"last_checked_at": result.as_of})
        return new

    # ------------------------------------------------------------------ build
    def _build_run(self, state: _RunState) -> ClaimVerificationRun:
        final = state.evaluations[-1]
        evidence: list[ContributionEvidence] = []
        results: list[AtomicClaimResult] = []
        decisions: list[AgentDecision] = []
        previous: dict[str, str] = {}
        seq = 0

        def next_decision_id():
            nonlocal seq
            seq += 1
            return f"DEC-{state.run_no:03d}{seq:03d}"

        checkins = sorted(state.checkin_decisions, key=lambda x: x[0])
        for k, evaluations in enumerate(state.evaluations):
            is_final = k == len(state.evaluations) - 1
            for spec in state.specs:
                ev = evaluations[spec.atomic_claim_id]
                ev_objs = [self._evidence(state, spec, a, ev.as_of, len(evidence) + n + 1)
                           for n, a in enumerate(ev.assessments)] if is_final else []
                evidence += ev_objs
                did = next_decision_id()
                decisions.append(AgentDecision(
                    decision_id=did, project_id=state.project_id, decision_type=DecisionType.CLAIM_VERIFICATION,
                    as_of=ev.as_of, created_at=ev.as_of, subject_member_id=spec.claimant_id,
                    claim_id=spec.atomic_claim_id, contribution_type=spec.contribution_type,
                    claim_status=ev.judgment.status, evidence_ids=[e.evidence_id for e in ev_objs],
                    source_ids=list(dict.fromkeys(a.candidate.source_id for a in ev.assessments)),
                    rationale=ev.judgment.rationale, confidence=ev.judgment.confidence,
                    previous_decision_id=previous.get(spec.atomic_claim_id)))
                previous[spec.atomic_claim_id] = did
                for at, cspec, gap, plan, action_id in checkins:
                    if cspec.atomic_claim_id == spec.atomic_claim_id and at == ev.as_of:
                        decisions.append(AgentDecision(
                            decision_id=next_decision_id(), project_id=state.project_id,
                            decision_type=DecisionType.CHECKIN_REQUEST, as_of=at, created_at=at,
                            subject_member_id=plan.target_member_id, task_id=plan.task_id,
                            claim_id=spec.atomic_claim_id,
                            source_ids=list(dict.fromkeys(a.candidate.source_id for a in gap.basis)),
                            rationale=(f"{gap.kind.value} → {plan.question_intent.value}: {gap.fact_to_confirm} — "
                                       f"{plan.target_reason} ({action_id})"),
                            confidence=Confidence.MEDIUM, previous_decision_id=did))
                if is_final:
                    by_rel = {r: [e.source_id for e in ev_objs if e.relation == r] for r in EvidenceRelation}
                    questions = list(ev.judgment.unresolved_questions) + [
                        g.unresolvable_reason for g in state.rounds[-1].gaps
                        if g.atomic_claim_id == spec.atomic_claim_id and g.unresolvable_reason]
                    results.append(AtomicClaimResult(
                        atomic_claim_id=spec.atomic_claim_id, parent_claim_id=state.claim.claim_id,
                        claimant_id=spec.claimant_id, text=spec.text,
                        predicted_contribution_type=spec.contribution_type, predicted_status=ev.judgment.status,
                        supporting_source_ids=by_rel[EvidenceRelation.SUPPORTS],
                        contradicting_source_ids=by_rel[EvidenceRelation.CONTRADICTS],
                        context_source_ids=by_rel[EvidenceRelation.CONTEXT],
                        used_evidence_ids=[e.evidence_id for e in ev_objs], confidence=ev.judgment.confidence,
                        rationale=ev.judgment.rationale, unresolved_questions=questions))

        overall, confidence, rationale, questions = self._summarize(results)
        atomic_claims = [ContributionClaim(
            claim_id=s.atomic_claim_id, project_id=state.project_id, member_id=s.claimant_id,
            submitted_at=s.submitted_at, source=state.claim_source, text=s.text,
            parent_claim_id=state.claim.claim_id, claimed_type=s.contribution_type,
            status=final[s.atomic_claim_id].judgment.status) for s in state.specs]
        return ClaimVerificationRun(
            run_id=state.run_id, project_id=state.project_id, submitted_claim_id=state.claim.claim_id,
            claimant_id=state.claim.member_id, as_of=state.as_of, atomic_claims=atomic_claims,
            search_steps=list(state.steps), evidence=evidence, decisions=decisions, atomic_results=results,
            overall_status=overall, rationale=rationale, confidence=confidence, unresolved_questions=questions,
            rounds=list(state.rounds), interactions=list(state.interactions.values()))

    # ------------------------------------------------------------------ steps
    def _state_of(self, run: ClaimVerificationRun) -> _RunState:
        state = self._states.get(run.run_id)
        if state is None or state.claim.claim_id != run.submitted_claim_id:
            raise ValueError(f"run {run.run_id} was not started by this agent")
        return state

    def _call(self, steps, atomic_id, tool, operation, params, purpose):
        dispatch = TOOL_OPERATIONS.get((tool, operation))
        if dispatch is None:
            raise ValueError(f"{tool}.{operation} is not available to the claim verification agent")
        result = dispatch(self.tools[tool], params)
        logged = {k: (v if isinstance(v, (str, int, float, bool)) or v is None else str(v)) for k, v in params.items()}
        steps.append(SearchStep(
            step=len(steps) + 1, atomic_claim_id=atomic_id, tool_name=tool, operation=operation,
            parameters=logged, purpose=purpose,
            returned_source_ids=result.source_ids() + result.action_ids() + result.reply_ids(),
            result_count=result.result_count()))
        return result

    def _term_statistics(self, steps, status) -> TermStatistics:
        texts = [c.match_text for c in from_result(status)]
        for tool in ("MeetingSearchTool", "DocumentHistoryTool", "MessageSearchTool"):
            result = self._call(steps, None, tool, "search", {"limit": MAX_LIMIT}, "용어 빈도 계산용 전체 기록 조회")
            texts += [c.match_text for c in from_result(result)]
        return TermStatistics(texts)

    def _register_atomics(self, steps, claim, members, existing) -> list[AtomicClaimSpec]:
        drafts = self.decomposer.decompose(claim, members)
        specs = []
        for d in drafts:
            prior = next((c for c in existing if c.parent_claim_id == claim.claim_id
                          and c.claimed_type == d.contribution_type and c.text == d.text), None)
            if prior is None:
                registered = self._call(steps, None, "ClaimTool", "register_atomic_claim",
                                        {"parent_claim_id": claim.claim_id,
                                         "claimed_type": d.contribution_type.value, "text": d.text},
                                        "atomic claim 등록").items[0]
            else:
                registered = prior
            specs.append(AtomicClaimSpec(
                atomic_claim_id=registered.source_id, parent_claim_id=claim.claim_id, claimant_id=claim.member_id,
                contribution_type=d.contribution_type, text=d.text, topic=tuple(term_groups(d.topic_terms)),
                mentioned_member_ids=d.mentioned_member_ids, expects_outcome=d.expects_outcome,
                submitted_at=claim.submitted_at))
        return specs

    def _collect(self, steps, spec: AtomicClaimSpec) -> dict[str, Candidate]:
        pool: dict[str, Candidate] = {}
        for req in self.planner.plan(spec):
            result = self._call(steps, spec.atomic_claim_id, req.tool_name, req.operation, req.params, req.purpose)
            for c in from_result(result):
                pool.setdefault(c.source_id, c)
        # 메시지 스레드 확장: 후보 메시지가 속한 스레드 전체를 가져온다 (답장·확인을 근거로 쓰기 위해)
        roots = sorted({c.reply_to or c.source_id for c in pool.values() if c.source_type.value == "MESSAGE"})
        for root in roots:
            result = self._call(steps, spec.atomic_claim_id, "MessageSearchTool", "search",
                                {"thread_root_id": root, "limit": MAX_LIMIT}, "메시지 스레드 확장")
            for c in from_result(result):
                pool.setdefault(c.source_id, c)
        return pool

    @staticmethod
    def _evidence(state, spec, a, collected_at, n) -> ContributionEvidence:
        c = a.candidate
        return ContributionEvidence(
            evidence_id=f"EV-{state.run_no:03d}{n:03d}", project_id=state.project_id,
            member_id=a.attributed_member_id, source_type=c.source_type, source_id=c.source_id,
            relation=a.relation, excerpt=c.text[:EXCERPT_CHARS], claim_id=spec.atomic_claim_id,
            contribution_type=a.contribution_type, collected_at=collected_at, note=f"{a.role}: {a.reason}")

    @staticmethod
    def _summarize(results: list[AtomicClaimResult]):
        if not results:
            return (ClaimStatus.PENDING_VERIFICATION, Confidence.LOW,
                    "Claim 문장에서 검증할 수 있는 기여 행위를 찾지 못했다.",
                    ["Claim이 어떤 기여(제안·실행·검토·조정·지원)를 말하는지 제출자에게 확인 필요"])
        overall = min((r.predicted_status for r in results), key=_OVERALL_ORDER.index)
        confidence = min((r.confidence for r in results), key=_CONFIDENCE_ORDER.index)
        rationale = " / ".join(f"[{r.atomic_claim_id} {r.predicted_contribution_type.value}: "
                               f"{r.predicted_status.value}] {r.rationale}" for r in results)
        questions = [q for r in results for q in r.unresolved_questions]
        return overall, confidence, rationale, questions
