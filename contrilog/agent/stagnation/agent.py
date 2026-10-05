"""StagnationAgent — (Task, 담당자) 단위 정체 탐지 → 확인 → 지원 제안 → 후속 관찰.

    session = ToolSession("P001", as_of=...)
    agent = StagnationAgent(tools=session.tools)
    agent.step()                  # 현재 시각에 할 일을 한다 (Tool만 사용)
    agent.next_wake_time()        # 다음에 깨워 달라는 시각 (시간 진행은 환경이 한다)
    agent.runs()                  # StagnationRun 목록 (에피소드별 trace)

상태 흐름 (사람이 아니라 Task의 상태):
  NORMAL ─(여러 신호 조합: StagnationPolicy)→ STAGNATION_CANDIDATE ─ STATUS_CHECK
     ├─ REPORTS_ON_TRACK / CONFIRMS_COMPLETION → NORMAL
     ├─ REPORTS_BLOCKED → CONFIRMED_BLOCK ─ 지원 후보 분석 → (있으면) 지원 요청 PROPOSED
     │        └ 사람이 APPROVED → Agent가 SENT → 지원 응답 → 시간 경과 → 후속 관찰 → 실제 근거 → RESOLVED
     ├─ 응답 없음·의미 불명확 → 후보 유지 (Block으로 추측하지 않음)
     └─ 그 사이 Task 기록이 다시 생기면 → NORMAL (관찰된 활동 재개)

접근 경계: 생성자로 받은 Agent-facing Tool만 쓴다. 승인(HumanApprovalGate)과 시간 이동은 할 수 없다.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any

from contrilog.schemas import (
    ActionStatus,
    AgentDecision,
    Confidence,
    DecisionType,
    EvidenceRelation,
    FeedbackLabel,
    FollowUpObservation,
    InteractionRecord,
    InteractionStatus,
    InterventionType,
    MemoryContext,
    PolicyApplication,
    QuestionIntent,
    ReplyInterpretation,
    ReplySemantic,
    SearchStep,
    StagnationRun,
    StagnationState,
    StateTransition,
    SupportAnalysis,
    TaskSignals,
    TaskStatus,
    TraceEvent,
)

from ..claim_verification import text as T
from ..claim_verification.candidates import from_reply, from_result
from .context import team_context
from .feedback import FeedbackAwarePolicy, FeedbackSettings, make_memory  # noqa: F401
from .interpreter import interpret_status_reply, interpret_support_reply
from .policy import StagnationPolicy
from .resolution import resolution_evidence
from .support import SupportCandidateSelector
from .thresholds import StagnationThresholds

S = StagnationState
KST = timezone(timedelta(hours=9))
MAX_LIMIT = 200

# 이 Agent가 쓸 수 있는 Tool operation (명시적 목록). 승인·거절과 시간 이동은 없다.
TOOL_OPERATIONS = {
    ("ProjectStatusTool", "get_status"): lambda t, p: t.get_status(**p),
    ("DocumentHistoryTool", "search"): lambda t, p: t.search(**p),
    ("MessageSearchTool", "search"): lambda t, p: t.search(**p),
    ("MeetingSearchTool", "search"): lambda t, p: t.search(**p),
    ("CheckInTool", "send"): lambda t, p: t.send(**p),
    ("InboxTool", "list_replies"): lambda t, p: t.list_replies(**p),
    ("SupportRequestTool", "propose"): lambda t, p: t.propose(**p),
    ("SupportRequestTool", "send"): lambda t, p: t.send(**p),
    ("SupportRequestTool", "list_requests"): lambda t, p: t.list_requests(**p),
}


@dataclass
class Episode:
    """한 (Task, 담당자)의 후보 발생부터 종료까지."""

    run_id: str
    task_id: str
    assignee_id: str
    title: str
    started_at: datetime
    state: StagnationState = S.NORMAL
    as_of: datetime | None = None
    signals: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    transitions: list = field(default_factory=list)
    check_ins: dict = field(default_factory=dict)  # action_id → InteractionRecord
    confirmed_state: StagnationState | None = None
    confirmed_at: datetime | None = None
    block_kind: str | None = None
    support_analysis: SupportAnalysis | None = None
    intervention: Any = None  # OutboundAction
    support_sent_at: datetime | None = None
    support_interactions: dict = field(default_factory=dict)
    follow_ups: list = field(default_factory=list)
    memory_context: MemoryContext | None = None
    feedback_written: bool = False
    decisions: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    timeline: list = field(default_factory=list)
    closed: bool = False


@dataclass
class UnitMemo:
    """(Task, 담당자)별 현재 에피소드와, 담당자가 '정상 진행'이라고 답한 뒤 다시 묻지 않을 시각."""

    episode: Episode | None = None
    trusted_until: datetime | None = None
    last_asked_at: datetime | None = None


class StagnationAgent:
    def __init__(self, tools: Mapping[str, Any], thresholds: StagnationThresholds | None = None,
                 policy: StagnationPolicy | None = None, selector: SupportCandidateSelector | None = None,
                 status_interpreter=interpret_status_reply, support_interpreter=interpret_support_reply,
                 resolution=resolution_evidence, feedback: FeedbackSettings | None = None):
        """feedback=None이면 Memory OFF (기본 정책 그대로). FeedbackSettings로 팀 맥락·Memory 보정을 켠다."""
        self.tools = tools
        self.feedback = feedback
        self.policy_log: list[PolicyApplication] = []
        self.team = None
        self.status_interpreter = status_interpreter
        self.support_interpreter = support_interpreter
        self.resolution = resolution
        self.thresholds = thresholds or (policy.thresholds if policy else StagnationThresholds())
        self.policy = policy or StagnationPolicy(self.thresholds)
        self.selector = selector or SupportCandidateSelector(self.thresholds.supporter_urgent_due_hours)
        self.feedback_policy = FeedbackAwarePolicy(self.policy, feedback) if feedback else None
        self.units: dict[tuple, UnitMemo] = {}
        self.episodes: list[Episode] = []
        self.action_owner: dict[str, tuple] = {}  # action_id → (episode, "status" | "support")
        self.now: datetime | None = None
        self.next_scan: datetime | None = None
        self.next_poll: datetime | None = None
        self.poll_round = 0
        self.decision_seq = 0
        self.project_id: str | None = None
        self.names: dict[str, str] = {}
        self.member_ids: list[str] = []
        self.task_views: dict = {}
        self.last_scan_step: SearchStep | None = None

    # ================================================================ public
    def step(self) -> None:
        """현재 시각은 Tool 결과(as_of)로만 안다. 이번 단계에서 Tool을 부를 이유가 없었다면,
        환경이 Agent가 요청한 정기 확인 시각에 깨운 것이므로 정기 확인을 한다."""
        observed = False
        if self._awaiting_replies():
            self._poll_inbox()
            observed = True
        if self._open_interventions():
            self._check_interventions()
            observed = True
        if not observed or self.next_scan is None or self.now >= self.next_scan:
            self._scan()

    def next_wake_time(self) -> datetime | None:
        times = [t for t in (self.next_scan, self.next_poll if self._awaiting_replies() else None) if t]
        return min(times) if times else None

    def runs(self) -> list[StagnationRun]:
        return [self._export(e) for e in self.episodes]

    def policy_applications(self) -> list[PolicyApplication]:
        """Memory·팀 맥락 보정이 쓰였거나 판단을 바꾼 정기 확인 기록 (후보가 되지 않은 경우 포함)."""
        return list(self.policy_log)

    # ================================================================ observe
    def _scan(self) -> None:
        status = self._call(None, "ProjectStatusTool", "get_status", {}, "Task 상태 관찰 (정기 확인)",
                            self._active())
        self.now, self.project_id = status.as_of, status.project_id
        self.next_scan = self.now + timedelta(hours=self.thresholds.scan_interval_hours)
        self.names = {m.member_id: m.name for m in status.members}
        self.member_ids = [m.member_id for m in status.members]
        task_status = {t.source_id: t.status for t in status.tasks}
        self.task_views = {t.source_id: t for t in status.tasks}
        if self.feedback is not None and self.feedback.use_team_context:
            self.team = self._team_context()
        for view in status.tasks:
            key = (view.source_id, view.assignee_ids[0])  # 담당자 목록의 첫 사람(주 담당자)에게만 묻는다
            memo = self.units.setdefault(key, UnitMemo())
            signals = self._signals(view, key[1], task_status)
            ep = memo.episode
            if ep is not None:
                ep.signals.append(signals)
                ep.as_of = self.now
                if ep.state == S.STAGNATION_CANDIDATE:
                    self._recheck_candidate(ep, memo, view, signals)
                elif ep.state == S.CONFIRMED_BLOCK:
                    self._follow_up(ep, memo, view)
                continue
            if view.status == TaskStatus.DONE:
                continue
            if self.feedback_policy is None:
                check = self.policy.check(signals, memo.trusted_until, memo.last_asked_at)
            else:
                last_at = view.last_task_activity.at if view.last_task_activity else None
                check = self.feedback_policy.check(signals, memo.trusted_until, memo.last_asked_at, self.team, last_at)
                if check.applied_memory_ids or check.is_candidate != check.base_is_candidate:
                    self._log_policy(view, signals, check)
            if check.is_candidate:
                self._open_episode(memo, view, signals, check)

    def _team_context(self):
        """팀 전체 공개 기록 시각으로 휴지기를 계산한다 (사람별로 나누지 않는다)."""
        times = []
        for tool in ("DocumentHistoryTool", "MessageSearchTool", "MeetingSearchTool"):
            res = self._call(None, tool, "search", {"limit": MAX_LIMIT}, "팀 전체 활동 맥락 (휴지기 판단)")
            times += [c.at for c in from_result(res)]
        return team_context(times, self.now, self.feedback.context_thresholds)

    def _log_policy(self, view, signals, check) -> None:
        self.decision_seq += 1
        state = S.STAGNATION_CANDIDATE if check.is_candidate else S.NORMAL
        decision = AgentDecision(
            decision_id=f"DEC-{self.decision_seq:05d}", project_id=self.project_id,
            decision_type=DecisionType.STAGNATION_ASSESSMENT, as_of=self.now, created_at=self.now,
            subject_member_id=signals.assignee_id, task_id=view.source_id, previous_stagnation_state=S.NORMAL,
            stagnation_state=state, source_ids=[s for s in [signals.last_activity_source_id, view.source_id] if s],
            rationale=(f"기본 정책 {'후보' if check.base_is_candidate else '정상'} → 보정 후 "
                       f"{'후보' if check.is_candidate else '정상'}: 실질 공백 {check.effective_idle_hours}h, "
                       f"허용 {check.base_idle_limit_hours}h + {check.memory_adjustment_hours}h = "
                       f"{check.effective_idle_limit_hours}h; {check.adjustment_explanation}"),
            confidence=Confidence.LOW, applied_memory_ids=check.applied_memory_ids)
        self.policy_log.append(PolicyApplication(task_id=view.source_id, check=check, decision=decision))

    def _signals(self, view, assignee_id, task_status) -> TaskSignals:
        return TaskSignals(
            task_id=view.source_id, assignee_id=assignee_id, observed_at=self.now, status=view.status,
            due_date=view.due_date, hours_until_due_end=view.hours_until_due_end,
            hours_since_last_task_activity=view.hours_since_last_task_activity,
            last_activity_source_id=view.last_task_activity.source_id if view.last_task_activity else None,
            recent_revision_ids=view.recent_revision_ids,
            unfinished_dependency_ids=[d for d in view.depends_on_task_ids if task_status.get(d) != TaskStatus.DONE])

    # ================================================================ candidate
    def _open_episode(self, memo, view, signals, check) -> None:
        ep = Episode(run_id=f"STR-{len(self.episodes) + 1:03d}", task_id=view.source_id,
                     assignee_id=signals.assignee_id, title=view.title, started_at=self.now, as_of=self.now)
        self.episodes.append(ep)
        memo.episode = ep
        ep.signals.append(signals)
        ep.checks.append(check)
        ep.memory_context = check.context
        ep.steps.append(self.last_scan_step)
        sources = [s for s in [signals.last_activity_source_id, view.source_id] if s]
        self._event(ep, "OBSERVE", "; ".join(check.reasons), sources)
        self._transition(ep, S.STAGNATION_CANDIDATE, "여러 관찰 신호 조합으로 Task 상태 확인이 필요함: "
                         + "; ".join(check.reasons), sources, Confidence.LOW, applied=check.applied_memory_ids)
        self._status_check(ep)

    def _status_check(self, ep) -> None:
        question = (f"'{ep.title}' 작업 상황을 확인하고 있어요. 지금 계획대로 진행되고 있는지, "
                    "혹시 막혀서 도움이 필요한 부분이 있는지 알려 주세요.")
        result = self._call(ep, "CheckInTool", "send",
                            {"task_id": ep.task_id, "member_id": ep.assignee_id, "question": question,
                             "question_intent": QuestionIntent.STATUS_CHECK.value},
                            "후보 Task 담당자에게 상태 확인 (STATUS_CHECK)")
        action = result.actions[0]
        ep.check_ins[action.action_id] = InteractionRecord(
            action_id=action.action_id, question_intent=QuestionIntent.STATUS_CHECK, tool_name="CheckInTool",
            operation="send", target_member_id=ep.assignee_id, task_id=ep.task_id, question=question,
            target_reason="후보가 된 Task의 담당자", sent_at=result.as_of, status=InteractionStatus.AWAITING_REPLY)
        self.action_owner[action.action_id] = (ep, "status")
        self.units[(ep.task_id, ep.assignee_id)].last_asked_at = result.as_of
        self._decision(ep, DecisionType.CHECKIN_REQUEST, ep.assignee_id, f"STATUS_CHECK ({action.action_id})",
                       [ep.task_id], Confidence.MEDIUM)
        self._event(ep, "CHECK_IN", f"{ep.assignee_id}에게 STATUS_CHECK ({action.action_id})", [ep.task_id])
        self._schedule_poll(reset=True)

    def _recheck_candidate(self, ep, memo, view, signals) -> None:
        if view.status == TaskStatus.DONE:
            self._remember_unresolved(ep, "TASK_COMPLETED_WITHOUT_REPLY", [view.source_id])
            self._close(ep, memo, S.NORMAL, "Task가 완료 상태로 관찰됨", [view.source_id], Confidence.HIGH)
            return
        last = view.last_task_activity
        if last is not None and last.at > ep.started_at:
            self._remember_unresolved(ep, "ACTIVITY_RESUMED_WITHOUT_REPLY", [last.source_id])
            self._close(ep, memo, S.NORMAL, f"후보가 된 뒤 Task 기록이 다시 생김 ({last.source_id})",
                        [last.source_id], Confidence.MEDIUM)
            return
        for record in ep.check_ins.values():
            if record.status == InteractionStatus.AWAITING_REPLY and \
                    self.now >= record.sent_at + timedelta(hours=self.thresholds.reply_timeout_hours):
                ep.check_ins[record.action_id] = record.model_copy(update={"status": InteractionStatus.NO_REPLY})
                self._event(ep, "REPLY", f"{record.action_id} 응답 없음 → 후보 유지 (Block으로 추측하지 않음)", [])

    # ================================================================ replies
    def _awaiting_replies(self) -> bool:
        for ep in self.episodes:
            if ep.closed:
                continue
            if any(r.status == InteractionStatus.AWAITING_REPLY for r in ep.check_ins.values()):
                return True
            if any(r.status == InteractionStatus.AWAITING_REPLY for r in ep.support_interactions.values()):
                return True
        return False

    def _schedule_poll(self, reset=False) -> None:
        backoff = self.thresholds.poll_backoff_minutes
        self.poll_round = 0 if reset else self.poll_round + 1
        base = self.now
        self.next_poll = base + timedelta(minutes=backoff[min(self.poll_round, len(backoff) - 1)])

    def _poll_inbox(self) -> None:
        waiting = [ep for ep in self.episodes if not ep.closed and self._ep_awaiting(ep)]
        result = self._call(None, "InboxTool", "list_replies", {}, "보낸 질문·지원 요청의 응답 확인", waiting)
        self.now = result.as_of
        got = False
        for reply in result.replies:
            owner = self.action_owner.get(reply.action_id)
            if owner is None:
                continue
            ep, kind = owner
            table = ep.check_ins if kind == "status" else ep.support_interactions
            record = table[reply.action_id]
            if reply.reply_id in record.reply_ids or ep.closed:
                continue
            got = True
            if kind == "status":
                self._on_status_reply(ep, record, reply)
            else:
                self._on_support_reply(ep, record, reply)
        if self._awaiting_replies():
            self._schedule_poll(reset=got)

    @staticmethod
    def _ep_awaiting(ep) -> bool:
        return any(r.status == InteractionStatus.AWAITING_REPLY
                   for r in list(ep.check_ins.values()) + list(ep.support_interactions.values()))

    def _on_status_reply(self, ep, record, reply) -> None:
        semantic, block_kind = self.status_interpreter(reply.text)
        ep.check_ins[record.action_id] = record.model_copy(update={
            "status": InteractionStatus.ANSWERED, "reply_ids": record.reply_ids + [reply.reply_id],
            "reply_interpretations": [ReplyInterpretation(
                reply_id=reply.reply_id, round=1, role="status_reply", relation=EvidenceRelation.CONTEXT,
                semantic=semantic)]})
        self._event(ep, "REPLY", f"{reply.reply_id} → {semantic.value}", [reply.reply_id])
        memo = self.units[(ep.task_id, ep.assignee_id)]
        if ep.state != S.STAGNATION_CANDIDATE:
            return
        if semantic == ReplySemantic.REPORTS_BLOCKED:
            ep.block_kind = block_kind
            ep.confirmed_state, ep.confirmed_at = S.CONFIRMED_BLOCK, self.now
            self._transition(ep, S.CONFIRMED_BLOCK, f"담당자가 막혀 있다고 응답 ({block_kind})", [reply.reply_id],
                             Confidence.MEDIUM)
            self._remember(ep, FeedbackLabel.TRUE_POSITIVE, semantic.value, [reply.reply_id])
            self._analyze_support(ep, reply)
        elif semantic in (ReplySemantic.REPORTS_ON_TRACK, ReplySemantic.CONFIRMS_COMPLETION):
            ep.confirmed_state = S.NORMAL
            view = self.task_views.get(ep.task_id)
            if view is not None:
                due_end = datetime.combine(view.due_date, time(23, 59, 59), KST)
                memo.trusted_until = due_end - timedelta(hours=self.thresholds.recheck_before_due_hours)
            self._remember(ep, FeedbackLabel.FALSE_POSITIVE, semantic.value, [reply.reply_id])
            self._close(ep, memo, S.NORMAL, f"담당자가 정상 진행이라고 응답 ({semantic.value}) → 마감 임박 전까지 다시 묻지 않음",
                        [reply.reply_id], Confidence.MEDIUM)
        else:
            self._event(ep, "DECISION", "응답 의미가 불명확함 → 후보 유지 (Block으로 추측하지 않음)", [reply.reply_id])

    def _on_support_reply(self, ep, record, reply) -> None:
        semantic = self.support_interpreter(reply.text)
        ep.support_interactions[record.action_id] = record.model_copy(update={
            "status": InteractionStatus.ANSWERED, "reply_ids": record.reply_ids + [reply.reply_id],
            "reply_interpretations": [ReplyInterpretation(
                reply_id=reply.reply_id, round=1, role="support_reply", relation=EvidenceRelation.CONTEXT,
                semantic=semantic)]})
        self._event(ep, "SUPPORT_RESPONSE", f"{reply.reply_id} → {semantic.value} (해결 여부는 후속 관찰로 판단)",
                    [reply.reply_id])

    # ================================================================ support
    def _analyze_support(self, ep, reply) -> None:
        view = self.task_views[ep.task_id]
        docs = set(view.related_document_ids)
        records = []
        for tool in ("DocumentHistoryTool", "MessageSearchTool", "MeetingSearchTool"):
            records += from_result(self._call(ep, tool, "search", {"limit": MAX_LIMIT}, "지원 후보 분석용 기록 조회"))
        status = self._call(ep, "ProjectStatusTool", "get_status", {}, "팀원별 현재 업무 상태 확인")
        tasks = from_result(status)
        own_on_task = sorted((r for r in records if r.document_id in docs and ep.assignee_id in r.actor_ids),
                             key=lambda r: r.at, reverse=True)[:2]
        reply_candidate = from_reply(reply)
        context = [reply_candidate] + own_on_task
        stats = T.TermStatistics([r.match_text for r in records + tasks])
        analysis = self.selector.select(
            at=self.now, block_kind=ep.block_kind or "INTERNAL_ISSUE", assignee_id=ep.assignee_id,
            task_document_ids=docs, context=context, records=records, tasks=tasks,
            hours_until_due={t.source_id: t.hours_until_due_end for t in status.tasks},
            member_ids=self.member_ids, stats=stats)
        ep.support_analysis = analysis
        chosen = next((a for a in analysis.candidates if a.member_id == analysis.selected_member_id), None)
        self._event(ep, "SUPPORT_ANALYSIS", analysis.reason,
                    (chosen.related_source_ids[:3] + chosen.prior_help_source_ids + chosen.open_task_ids)
                    if chosen else analysis.context_source_ids)
        if analysis.selected_member_id is None:
            return
        supporter = analysis.selected_member_id
        message = (f"{self.names.get(ep.assignee_id, ep.assignee_id)}님의 '{ep.title}' 작업이 막혀 있다는 응답을 받았습니다. "
                   f"관련 기록({chosen.best_related_source_id})이 있는 {self.names.get(supporter, supporter)}님께 "
                   "문제 확인을 함께해 주실 수 있는지 요청드리는 방안을 제안합니다.")
        result = self._call(ep, "SupportRequestTool", "propose",
                            {"task_id": ep.task_id, "about_member_id": ep.assignee_id, "supporter_id": supporter,
                             "message": message, "intervention_type": InterventionType.SUPPORT.value},
                            "지원 요청 제안 (사람의 승인 전에는 전달되지 않음)")
        ep.intervention = result.actions[0]
        self.action_owner[ep.intervention.action_id] = (ep, "support")
        self._decision(ep, DecisionType.INTERVENTION_PROPOSAL, ep.assignee_id,
                       f"{analysis.reason} ({ep.intervention.action_id})",
                       [s for s in [chosen.best_related_source_id, ep.task_id] + chosen.prior_help_source_ids if s],
                       Confidence.MEDIUM, intervention_type=InterventionType.SUPPORT, supporter=supporter)
        self._event(ep, "INTERVENTION", f"{supporter}에게 지원 요청 PROPOSED ({ep.intervention.action_id})",
                    [chosen.best_related_source_id])

    def _open_interventions(self) -> list:
        return [ep for ep in self.episodes if not ep.closed and ep.intervention is not None
                and ep.intervention.status in (ActionStatus.PROPOSED, ActionStatus.APPROVED)]

    def _check_interventions(self) -> None:
        pending = self._open_interventions()
        result = self._call(None, "SupportRequestTool", "list_requests", {}, "지원 요청 제안의 사람 결정 확인", pending)
        self.now = result.as_of
        latest = {a.action_id: a for a in result.actions}
        for ep in pending:
            action = latest.get(ep.intervention.action_id)
            if action is None or action.status == ep.intervention.status:
                continue
            decision = action.status_history[-1]
            ep.intervention = action
            if action.status == ActionStatus.APPROVED:
                self._event(ep, "HUMAN", f"{decision.changed_by}가 지원 요청을 APPROVED ({decision.note or ''})", [])
                self._send_support(ep)
            elif action.status == ActionStatus.REJECTED:
                self._event(ep, "HUMAN", f"{decision.changed_by}가 지원 요청을 REJECTED → 전송하지 않음", [])

    def _send_support(self, ep) -> None:
        result = self._call(ep, "SupportRequestTool", "send", {"action_id": ep.intervention.action_id},
                            "사람이 승인한 지원 요청 전달")
        ep.intervention = result.actions[0]
        ep.support_sent_at = result.as_of
        supporter = ep.intervention.recipient_id
        ep.support_interactions[ep.intervention.action_id] = InteractionRecord(
            action_id=ep.intervention.action_id, tool_name="SupportRequestTool", operation="send",
            target_member_id=supporter, task_id=ep.task_id, question=ep.intervention.message,
            target_reason=ep.support_analysis.reason, sent_at=result.as_of, status=InteractionStatus.AWAITING_REPLY)
        self._event(ep, "ACTION", f"{supporter}에게 지원 요청 SENT ({ep.intervention.action_id})", [ep.task_id])
        self._schedule_poll(reset=True)

    # ================================================================ follow-up
    def _follow_up(self, ep, memo, view) -> None:
        reference = ep.support_sent_at or ep.confirmed_at
        revisions = []
        for doc in sorted(view.related_document_ids):
            res = self._call(ep, "DocumentHistoryTool", "search", {"document_id": doc, "start": reference.isoformat(),
                                                                    "limit": MAX_LIMIT}, "후속 관찰: Task 문서 변경")
            revisions += [c for c in from_result(res) if c.at > reference]
        changes = [(view.source_id, h.to_status.value) for h in view.status_history if h.changed_at > reference]
        new, fixes = self.resolution(revisions, changes)
        resolved = bool(fixes)
        note = ("후속 근거로 해결 확인" if resolved else
                ("새 기록은 있으나 해결을 나타내지 않음" if new else "기준 시각 이후 새 기록 없음"))
        ep.follow_ups.append(FollowUpObservation(at=self.now, reference_at=reference, new_source_ids=new,
                                                 resolution_source_ids=fixes, resolved=resolved, note=note))
        if new or resolved:
            self._event(ep, "FOLLOW_UP", f"{note} (기준 {reference.strftime('%m-%d %H:%M')} 이후)", new)
            self._decision(ep, DecisionType.FOLLOW_UP, ep.assignee_id, note, new, Confidence.MEDIUM)
        if resolved:
            confidence = Confidence.HIGH if any(s == view.source_id for s in fixes) and len(fixes) > 1 \
                else Confidence.MEDIUM
            self._close(ep, memo, S.RESOLVED, f"후속 근거 {', '.join(fixes)} 관찰", fixes, confidence)
            if ep.support_sent_at is not None:
                self._remember_intervention(ep, fixes)

    # ================================================================ memory (Agent 자신의 판단 결과)
    def _memory_on(self) -> bool:
        return self.feedback is not None and self.feedback.use_memory and self.feedback.store is not None

    def _remember(self, ep, label, observed_signal, evidence) -> None:
        if not self._memory_on() or ep.feedback_written or ep.memory_context is None:
            return
        ep.feedback_written = True
        memory = make_memory(
            self.feedback.store, project_id=self.project_id, created_at=self.now, label=label,
            context=ep.memory_context, decision_ids=[d.decision_id for d in ep.decisions],
            observed_signal=observed_signal, judgment="STAGNATION_CANDIDATE로 판단하고 STATUS_CHECK를 보냄",
            evidence_ids=[ep.task_id] + list(evidence))
        self._event(ep, "DECISION", f"Memory {memory.memory_id} 기록: {label.value} ({observed_signal})", [])

    def _remember_unresolved(self, ep, observed_signal, evidence) -> None:
        answered = [r for r in ep.check_ins.values() if r.reply_interpretations]
        signal = "NOT_INFORMATIVE_REPLY" if answered else observed_signal
        self._remember(ep, FeedbackLabel.UNRESOLVED, signal, evidence)

    def _remember_intervention(self, ep, fixes) -> None:
        if not self._memory_on() or ep.support_analysis is None:
            return
        chosen = next((c for c in ep.support_analysis.candidates
                       if c.member_id == ep.support_analysis.selected_member_id), None)
        basis = [b for b, ok in [("RELATED_RECORD", chosen and chosen.related_source_ids),
                                 ("PRIOR_HELP", chosen and chosen.prior_help_source_ids),
                                 ("NO_URGENT_OWN_TASK", chosen and chosen.available)] if ok]
        context = MemoryContext(kind="INTERVENTION", block_kind=ep.support_analysis.block_kind, selection_basis=basis)
        evidence = [ep.task_id] + ([chosen.best_related_source_id] + chosen.prior_help_source_ids if chosen else []) \
            + list(fixes)
        memory = make_memory(
            self.feedback.store, project_id=self.project_id, created_at=self.now,
            label=FeedbackLabel.RESOLUTION_SUCCESS, context=context, decision_ids=[d.decision_id for d in ep.decisions],
            observed_signal="RESOLUTION_EVIDENCE_OBSERVED",
            judgment="관련 기록·이전 지원 기록을 근거로 지원 후보를 골라 지원 요청을 제안함",
            evidence_ids=evidence, decision_type=DecisionType.INTERVENTION_PROPOSAL,
            previous=S.CONFIRMED_BLOCK)
        self._event(ep, "DECISION", f"Memory {memory.memory_id} 기록: RESOLUTION_SUCCESS (선정 근거 {'+'.join(basis)})", [])

    # ================================================================ records
    def _transition(self, ep, to_state, reason, sources, confidence, applied=()) -> None:
        did = self._decision(ep, DecisionType.STAGNATION_ASSESSMENT, ep.assignee_id, reason, sources, confidence,
                             previous=ep.state, state=to_state, applied=applied)
        ep.transitions.append(StateTransition(at=self.now, from_state=ep.state, to_state=to_state, reason=reason,
                                              source_ids=sources, decision_id=did))
        self._event(ep, "DECISION", f"{ep.state.value} → {to_state.value}: {reason}", sources)
        ep.state = to_state

    def _close(self, ep, memo, to_state, reason, sources, confidence) -> None:
        self._transition(ep, to_state, reason, sources, confidence)
        for record in list(ep.check_ins.values()):
            if record.status == InteractionStatus.AWAITING_REPLY:  # 응답을 받기 전에 다른 관찰로 종료됨
                ep.check_ins[record.action_id] = record.model_copy(update={"status": InteractionStatus.NO_REPLY})
                self._event(ep, "REPLY", f"{record.action_id} 응답 전에 종료 (응답 없음으로 기록)", [])
        ep.closed = True
        ep.as_of = self.now
        memo.episode = None

    def _decision(self, ep, dtype, subject, rationale, sources, confidence, *, previous=None, state=None,
                  intervention_type=None, supporter=None, applied=()) -> str:
        self.decision_seq += 1
        did = f"DEC-{self.decision_seq:05d}"
        ep.decisions.append(AgentDecision(
            decision_id=did, project_id=self.project_id, decision_type=dtype, as_of=self.now, created_at=self.now,
            subject_member_id=subject, task_id=ep.task_id, previous_stagnation_state=previous, stagnation_state=state,
            intervention_type=intervention_type, supporter_member_id=supporter,
            source_ids=[s for s in dict.fromkeys(sources) if s], rationale=rationale, confidence=confidence,
            previous_decision_id=ep.decisions[-1].decision_id if ep.decisions else None,
            applied_memory_ids=list(applied)))
        return did

    def _event(self, ep, kind, summary, sources) -> None:
        ep.timeline.append(TraceEvent(at=self.now, kind=kind, summary=summary, source_ids=[s for s in sources if s]))

    def _active(self) -> list:
        return [ep for ep in self.episodes if not ep.closed]

    def _call(self, ep, tool, operation, params, purpose, extra_eps=()):
        dispatch = TOOL_OPERATIONS.get((tool, operation))
        if dispatch is None:
            raise ValueError(f"{tool}.{operation} is not available to the stagnation agent")
        call_params = dict(params)
        if "start" in call_params:
            call_params["start"] = datetime.fromisoformat(call_params["start"])
        result = dispatch(self.tools[tool], call_params)
        self.now = result.as_of
        targets = ([ep] if ep is not None else []) + [e for e in extra_eps if e is not ep]
        step = SearchStep(step=1, tool_name=tool, operation=operation,
                          parameters={k: (v if isinstance(v, (str, int, float, bool)) or v is None else str(v))
                                      for k, v in params.items()},
                          purpose=purpose,
                          returned_source_ids=result.source_ids() + result.action_ids() + result.reply_ids(),
                          result_count=result.result_count())
        if tool == "ProjectStatusTool" and ep is None:
            self.last_scan_step = step
        for target in targets:
            target.steps.append(step)
        return result

    def _export(self, ep) -> StagnationRun:
        steps = [s.model_copy(update={"step": i + 1}) for i, s in enumerate(ep.steps)]
        return StagnationRun(
            run_id=ep.run_id, project_id=self.project_id, task_id=ep.task_id, assignee_id=ep.assignee_id,
            started_at=ep.started_at, as_of=ep.as_of or ep.started_at, initial_state=S.NORMAL,
            observed_signals=ep.signals, candidate_checks=ep.checks, transitions=ep.transitions,
            check_ins=list(ep.check_ins.values()), confirmed_state=ep.confirmed_state,
            support_analysis=ep.support_analysis, intervention=ep.intervention,
            support_interactions=list(ep.support_interactions.values()), follow_ups=ep.follow_ups,
            final_state=ep.state, decisions=ep.decisions, tool_trace=steps, timeline=ep.timeline)

