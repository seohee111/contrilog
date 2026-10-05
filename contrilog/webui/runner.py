"""웹 시연용 실행기 (환경 계층).

Agent·Tool·LLM 해석기는 scripts/demo.py와 같다. 이 실행기는 시간을 한 단계씩 진행시키고,
지원 요청 제안(PROPOSED)이 생기면 진행을 멈춰 사람(웹 화면의 PM)의 승인·거절을 기다린다.
결정은 HumanApprovalGate(session.human)로만 적용한다 — Agent는 승인할 수 없다.

화면용 부가 정보(받은 답장 본문, LLM 해석 근거)는 Agent가 쓰는 InboxTool·해석기를 감싸 옆에서 기록할 뿐,
Agent의 판단에는 관여하지 않는다.
"""

from datetime import datetime, timedelta, timezone

from contrilog.agent.stagnation import FeedbackSettings, StagnationAgent
from contrilog.agent.stagnation.interpreter import interpret_status_reply, interpret_support_reply
from contrilog.memory import InMemoryMemoryStore
from contrilog.tools import ToolSession

KST = timezone(timedelta(hours=9))

SCENARIOS = {
    "webhook": dict(project="P002", task="T08", start=(2026, 5, 18, 9), until=(2026, 5, 29, 9), approver="M_A",
                    title="배송 상태 웹훅 수신 — 스테이징에서만 서명 검증 401"),
    "p001": dict(project="P001", task="T11", start=(2026, 10, 5, 9), until=(2026, 10, 11, 0), approver="M_A",
                 title="Claim 검증 API — 기간 필터 이후 검색 0건"),
    "map": dict(project="P002", task="T11", start=(2026, 5, 26, 9), until=(2026, 6, 5, 9), approver="M_A",
                title="배송 추적 지도 화면 — 운영에서만 지도가 회색 (지원자 선정 한계 사례)"),
}

KIND_LABEL = {"OBSERVE": "관찰", "DECISION": "판단", "CHECK_IN": "확인 질문", "REPLY": "답장", "SUPPORT_ANALYSIS": "지원 분석",
              "INTERVENTION": "지원 제안", "HUMAN": "사람 결정", "ACTION": "전송", "SUPPORT_RESPONSE": "지원 답장",
              "FOLLOW_UP": "후속 관찰"}


class DemoRun:
    def __init__(self, scenario: str = "webhook", interpreter: str = "llm", provider: str = "ollama", llm=None):
        sc = SCENARIOS[scenario]
        self.scenario_key, self.sc = scenario, sc
        self.session = ToolSession(sc["project"], datetime(*sc["start"], tzinfo=KST))
        self.until = datetime(*sc["until"], tzinfo=KST)
        self.names = {m.member_id: m.name for m in self.session.snapshot.members}
        self.reply_text, self.readings = {}, {}
        self.llm = llm
        if interpreter == "llm" and self.llm is None:
            from contrilog.llm import LLMReplyInterpreter

            self.llm = LLMReplyInterpreter(provider=provider)
        self.interpreter = interpreter
        self.store = InMemoryMemoryStore()
        tools = dict(self.session.tools)
        tools["InboxTool"] = _InboxObserver(self.session.tools["InboxTool"], self.reply_text)
        self.agent = StagnationAgent(tools=tools, feedback=FeedbackSettings(store=self.store),
                                     status_interpreter=self._status, support_interpreter=self._support)
        self.decisions = []
        self.finished = False
        self.wakes = 0
        self.agent.step()

    # ------------------------------------------------------------ 해석기 (화면용 기록만 덧붙임)
    def _status(self, text):
        if self.interpreter != "llm":
            return interpret_status_reply(text)
        result = self.llm.status(text)
        self.readings[text] = self.llm.calls[-1]
        return result

    def _support(self, text):
        if self.interpreter != "llm":
            return interpret_support_reply(text)
        result = self.llm.support(text)
        self.readings[text] = self.llm.calls[-1]
        return result

    # ------------------------------------------------------------ 진행
    def pending(self):
        return self.session.human.pending()

    def advance(self, max_wakes: int = 1) -> int:
        """Agent를 최대 max_wakes번 깨운다. 사람의 결정이 필요하거나 기간이 끝나면 멈춘다."""
        done = 0
        while done < max_wakes and not self.finished and not self.pending():
            wake = self.agent.next_wake_time()
            if wake is None:
                self.finished = True
                break
            wake = max(wake, self.session.as_of + timedelta(minutes=1))
            if wake > self.until:
                self.finished = True
                break
            self.session.advance_to(wake)
            self.agent.step()
            self.wakes += 1
            done += 1
        return done

    def advance_to_next_event(self, task_only: bool = True, max_wakes: int = 500) -> int:
        """화면에 보일 새 사건(기본: 시나리오 Task의 사건)이 생길 때까지 진행한다."""
        before = self._event_count(task_only)
        done = 0
        while done < max_wakes and self._event_count(task_only) == before:
            step = self.advance(1)
            if step == 0:
                break
            done += step
        return done

    def decide(self, action_id: str, approve: bool, note: str | None = None) -> None:
        """PM의 결정. 승인·거절은 HumanApprovalGate로만 적용하고, Agent가 같은 시각에 결과를 확인하게 깨운다."""
        approver = self.sc["approver"]
        if approve:
            self.session.human.approve(action_id, approver, note=note or "웹 화면에서 PM 승인")
        else:
            self.session.human.reject(action_id, approver, note=note or "웹 화면에서 PM 거절")
        self.decisions.append({"at": self.session.as_of.isoformat(), "action_id": action_id, "approve": approve})
        self.agent.step()

    def _event_count(self, task_only):
        return sum(len(e.timeline) for e in self.agent.episodes if not task_only or e.task_id == self.sc["task"])

    # ------------------------------------------------------------ 화면 상태
    def state(self) -> dict:
        n = self.names
        latest = {}
        for ep in self.agent.episodes:
            latest[ep.task_id] = ep
        tasks = []
        for tid, v in sorted(self.agent.task_views.items()):
            ep = latest.get(tid)
            tasks.append({
                "task_id": tid, "title": v.title, "assignees": [n.get(a, a) for a in v.assignee_ids],
                "status": v.status.value, "due": v.due_date.isoformat(),
                "hours_until_due": v.hours_until_due_end, "idle_hours": v.hours_since_last_task_activity,
                "agent_state": ep.state.value if ep else "NORMAL", "focus": tid == self.sc["task"],
            })
        events = []
        for ep in self.agent.episodes:
            for i, ev in enumerate(ep.timeline):
                label = "Memory" if ev.kind == "DECISION" and ev.summary.startswith("Memory ") else KIND_LABEL.get(ev.kind, ev.kind)
                item = {"id": f"{ep.run_id}-{i}", "at": ev.at.isoformat(), "kind": ev.kind, "label": label,
                        "summary": ev.summary, "sources": ev.source_ids[:6], "task_id": ep.task_id,
                        "task_title": ep.title, "assignee": n.get(ep.assignee_id, ep.assignee_id)}
                if ev.kind in ("REPLY", "SUPPORT_RESPONSE"):
                    text = next((self.reply_text[s] for s in ev.source_ids if s in self.reply_text), None)
                    if text:
                        item["reply_text"] = text
                        call = self.readings.get(text)
                        if call is not None:
                            item["reading"] = {"semantic": call.semantic, "block_kind": call.block_kind,
                                               "evidence": call.evidence_phrase, "reason": call.reason,
                                               "source": call.source, "error": call.error}
                events.append(item)
        events.sort(key=lambda e: (e["at"], e["id"]))
        pending = []
        for a in self.pending():
            ep = next((e for e in self.agent.episodes if e.intervention is not None
                       and e.intervention.action_id == a.action_id), None)
            analysis = ep.support_analysis if ep else None
            chosen = next((c for c in analysis.candidates if c.member_id == a.recipient_id), None) if analysis else None
            pending.append({
                "action_id": a.action_id, "task_id": a.task_id, "task_title": ep.title if ep else a.task_id,
                "about": n.get(a.about_member_id), "supporter": n.get(a.recipient_id), "message": a.message,
                "reason": analysis.reason if analysis else "", "evidence": chosen.related_source_ids[:4] if chosen else [],
                "prior_help": chosen.prior_help_source_ids if chosen else [],
                "others": [n.get(c.member_id) for c in analysis.candidates if c.eligible and c.member_id != a.recipient_id]
                if analysis else [],
            })
        runs = self.agent.runs()
        return {
            "scenario": {"key": self.scenario_key, "title": self.sc["title"], "focus_task": self.sc["task"],
                         "project": self.session.snapshot.project.name, "project_id": self.sc["project"]},
            "interpreter": (f"LLM ({self.llm.provider} {self.llm.model})" if self.interpreter == "llm" else "규칙(키워드)"),
            "members": self.names,
            "as_of": self.session.as_of.isoformat(), "until": self.until.isoformat(), "finished": self.finished,
            "tasks": tasks, "events": events, "pending": pending, "decisions": self.decisions,
            "memories": [{"id": m.memory_id, "label": m.feedback_label.value, "pattern": m.signal_pattern,
                          "at": m.created_at.isoformat()} for m in self.store.all()],
            "stats": {"tool_calls": len(self.session.call_log), "questions": sum(len(r.check_ins) for r in runs),
                      "candidates": len(runs),
                      "blocks": sum(r.confirmed_state is not None and r.confirmed_state.value == "CONFIRMED_BLOCK"
                                    for r in runs),
                      "resolved": sum(r.final_state.value == "RESOLVED" for r in runs), "wakes": self.wakes},
        }


class _InboxObserver:
    """Agent가 쓰는 InboxTool을 그대로 호출하고, 화면용으로 답장 본문만 기록한다."""

    def __init__(self, tool, sink):
        self.tool, self.sink = tool, sink

    def list_replies(self, **kw):
        result = self.tool.list_replies(**kw)
        for r in result.replies:
            self.sink[r.reply_id] = r.text
        return result
