"""ContriLog 시연: 한 Task의 정체 탐지 → 확인 → Block 확정 → 지원 제안 → (사람 승인) → 후속 관찰 → 해결 → Memory.

사용법:
  python scripts/demo.py                         # P002 웹훅 서명 Block, 로컬 LLM 해석기 (실패하면 규칙 해석기로 대체)
  python scripts/demo.py --scenario map          # 단어만 겹치는 지원 후보 함정 (P002 지도 화면)
  python scripts/demo.py --scenario p001         # P001 Claim 검증 API Block
  python scripts/demo.py --interpreter rule      # 규칙 해석기로 실행 (비교용)
  python scripts/demo.py --auto                  # 승인 입력 없이 자동 승인 (녹화 리허설용)
  python scripts/demo.py --speed 0               # 대기 없이 출력

사람의 결정(승인·거절)은 이 터미널에서 직접 입력한다. Agent는 승인 없이 지원 요청을 보낼 수 없다.
시간은 환경(이 스크립트)이 진행시키고, Agent는 Tool로만 관찰·행동한다.
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

from contrilog.agent.stagnation import FeedbackSettings, StagnationAgent
from contrilog.agent.stagnation.interpreter import interpret_status_reply, interpret_support_reply
from contrilog.memory import InMemoryMemoryStore
from contrilog.tools import ToolSession

KST = timezone(timedelta(hours=9))

SCENARIOS = {
    "webhook": dict(project="P002", task="T08", start=(2026, 5, 18, 9), until=(2026, 5, 29, 9), approver="M_A",
                    title="배송 상태 웹훅 수신 — 스테이징에서만 서명 검증 401"),
    "map": dict(project="P002", task="T11", start=(2026, 5, 26, 9), until=(2026, 6, 5, 9), approver="M_A",
                title="배송 추적 지도 화면 — 운영에서만 지도가 회색"),
    "p001": dict(project="P001", task="T11", start=(2026, 10, 5, 9), until=(2026, 10, 11, 0), approver="M_A",
                 title="Claim 검증 API — 기간 필터 이후 검색 0건"),
}

C = dict(dim="\033[2m", b="\033[1m", r="\033[0m", red="\033[31m", grn="\033[32m", yel="\033[33m", blu="\033[34m",
         mag="\033[35m", cyn="\033[36m")
KIND_STYLE = {"OBSERVE": ("관찰", "cyn"), "DECISION": ("판단", "yel"), "CHECK_IN": ("확인 질문", "blu"),
              "REPLY": ("응답", "mag"), "SUPPORT_ANALYSIS": ("지원 분석", "yel"), "INTERVENTION": ("제안", "blu"),
              "HUMAN": ("사람 결정", "grn"), "ACTION": ("실행", "blu"), "SUPPORT_RESPONSE": ("지원 응답", "mag"),
              "FOLLOW_UP": ("후속 관찰", "cyn")}


class Printer:
    def __init__(self, speed: float):
        self.speed = speed

    def line(self, at, label, text, color="r"):
        stamp = at.strftime("%m/%d(%a) %H:%M") if at else " " * 15
        print(f"{C['dim']}{stamp}{C['r']}  {C[color]}{C['b']}{label:<8}{C['r']} {text}", flush=True)
        if self.speed:
            time.sleep(self.speed)

    def note(self, text, color="dim"):
        print(f"{' ' * 17}{C[color]}{text}{C['r']}", flush=True)


class TerminalApprover:
    """사람(PM)의 승인·거절을 터미널 입력으로 받는다. HumanApprovalGate만 사용한다."""

    def __init__(self, approver_id, names, printer, auto=False):
        self.approver_id, self.names, self.p, self.auto = approver_id, names, printer, auto
        self.seen = set()

    def next_due(self):
        return None

    def process(self, session):
        for action in session.human.pending():
            if action.action_id in self.seen:
                continue
            self.seen.add(action.action_id)
            who = self.names.get(action.recipient_id, action.recipient_id)
            print()
            self.p.line(session.as_of, "승인 요청", f"{C['b']}Agent가 지원 요청을 제안했습니다 (아직 전송되지 않음){C['r']}", "grn")
            self.p.note(f"지원자: {who} ({action.recipient_id})   Task: {action.task_id}", "r")
            self.p.note(f"메시지: {action.message}", "r")
            if self.auto:
                answer = "y"
                self.p.note(f"[자동 승인 모드] {self.names.get(self.approver_id)}: y", "grn")
            else:
                answer = input(f"{' ' * 17}{C['grn']}{C['b']}{self.names.get(self.approver_id)}(PM)님, 승인할까요? [y/n] {C['r']}")
            if answer.strip().lower().startswith("y"):
                session.human.approve(action.action_id, self.approver_id, note="시연: PM 승인")
            else:
                session.human.reject(action.action_id, self.approver_id, note="시연: PM 거절")
            print()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), default="webhook")
    ap.add_argument("--interpreter", choices=["llm", "rule"], default="llm")
    ap.add_argument("--provider", choices=["ollama", "anthropic"], default="ollama")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--speed", type=float, default=0.5)
    args = ap.parse_args(argv)
    sc = SCENARIOS[args.scenario]
    p = Printer(args.speed)

    session = ToolSession(sc["project"], datetime(*sc["start"], tzinfo=KST))
    names = {m.member_id: m.name for m in session.snapshot.members}
    reply_text = {}  # RPL-* → 본문 (환경이 Agent의 수신함 조회 결과를 옆에서 기록)
    readings = {}  # 본문 → LLM 해석 기록

    llm = None
    if args.interpreter == "llm":
        from contrilog.llm import LLMReplyInterpreter

        llm = LLMReplyInterpreter(provider=args.provider)

    def show_reading(text):
        p.note(f"받은 답장: \"{text}\"", "r")
        call = readings.get(text)
        if call is None:
            return
        if call.source == "rule_fallback":
            p.note(f"LLM 사용 불가 → 규칙 해석기로 대체 ({(call.error or '')[:80]})", "red")
        else:
            src = "LLM" if call.source == "llm" else "LLM(캐시)"
            p.note(f"{src} 해석: {call.semantic}{' / ' + call.block_kind if call.block_kind else ''}", "mag")
            p.note(f"  근거: \"{call.evidence_phrase}\" — {call.reason}", "mag")

    def status_interpreter(text):
        result = llm.status(text) if llm else interpret_status_reply(text)
        if llm:
            readings[text] = llm.calls[-1]
        return result

    def support_interpreter(text):
        result = llm.support(text) if llm else interpret_support_reply(text)
        if llm:
            readings[text] = llm.calls[-1]
        return result

    class InboxObserver:
        """Agent가 쓰는 InboxTool을 그대로 호출하고, 시연 화면용으로 응답 본문만 옆에서 기록한다."""

        def __init__(self, tool):
            self.tool = tool

        def list_replies(self, **kw):
            result = self.tool.list_replies(**kw)
            for r in result.replies:
                reply_text[r.reply_id] = r.text
            return result

    tools = dict(session.tools)
    tools["InboxTool"] = InboxObserver(session.tools["InboxTool"])

    store = InMemoryMemoryStore()
    agent = StagnationAgent(tools=tools, feedback=FeedbackSettings(store=store),
                            status_interpreter=status_interpreter, support_interpreter=support_interpreter)
    human = TerminalApprover(sc["approver"], names, p, auto=args.auto)
    until = datetime(*sc["until"], tzinfo=KST)

    print(f"\n{C['b']}ContriLog · AI Team Manager 시연{C['r']}  ({sc['project']} {session.snapshot.project.name})")
    print(f"시나리오: {sc['title']}   해석기: {args.interpreter}{(' (' + llm.provider + ' ' + llm.model + ')') if llm else ''}   기간: {session.as_of:%m/%d} ~ {until:%m/%d}")
    print(f"{C['dim']}Agent는 Tool로만 관찰·행동하고, 지원 요청은 사람이 승인해야 전송됩니다. 사람을 평가하지 않습니다.{C['r']}\n")

    printed_events = {}
    printed_calls = 0
    scans = 0

    def flush():
        nonlocal printed_calls, scans
        calls = session.call_log[printed_calls:]
        printed_calls += len(calls)
        for c in calls:
            if c.tool_name == "ProjectStatusTool" and not c.parameters:
                scans += 1
        for ep in agent.episodes:
            if ep.task_id != sc["task"]:
                continue
            seen = printed_events.setdefault(ep.run_id, 0)
            for ev in ep.timeline[seen:]:
                label, color = KIND_STYLE.get(ev.kind, (ev.kind, "r"))
                if ev.kind == "DECISION" and ev.summary.startswith("Memory "):
                    label, color = "Memory", "grn"
                src = f" {C['dim']}[{', '.join(ev.source_ids[:4])}]{C['r']}" if ev.source_ids else ""
                p.line(ev.at, label, ev.summary + src, color)
                if ev.kind in ("REPLY", "SUPPORT_RESPONSE"):
                    for sid in ev.source_ids:
                        if sid in reply_text:
                            show_reading(reply_text[sid])
            printed_events[ep.run_id] = len(ep.timeline)

    agent.step()
    flush()
    last_scan_note = None
    while True:
        wakes = [t for t in (agent.next_wake_time(),) if t is not None]
        human.process(session)
        if not wakes:
            break
        wake = max(min(wakes), session.as_of + timedelta(minutes=1))
        if wake > until:
            break
        session.advance_to(wake)
        human.process(session)
        agent.step()
        before = scans
        flush()
        if scans > before and not any(e.task_id == sc["task"] and not e.closed for e in agent.episodes):
            day = session.as_of.strftime("%m/%d")
            if day != last_scan_note:
                last_scan_note = day
                p.line(session.as_of, "정기 관찰", f"{C['dim']}Task {len(agent.task_views)}개 상태 확인 — '{sc['task']}' 이상 신호 없음{C['r']}", "dim")

    runs = [r for r in agent.runs() if r.task_id == sc["task"]]
    print(f"\n{C['b']}결과{C['r']}")
    for r in runs:
        print(f"  {r.run_id} {r.task_id}·{names[r.assignee_id]}: {' → '.join(s.value for s in r.state_sequence)}")
        if r.intervention:
            hist = " → ".join(h.status.value for h in r.intervention.status_history)
            print(f"  지원 요청 {r.intervention.action_id}: {hist} (지원자 {names.get(r.intervention.recipient_id)})")
    print(f"  Tool 호출 {len(session.call_log)}회 · 이 Task에 보낸 확인 질문 {sum(len(r.check_ins) for r in runs)}회 · "
          f"Agent Memory {len(store.all())}건 (사람 정보 없음)")
    for m in store.all():
        if any(e in (sc["task"],) for e in m.evidence_ids):
            print(f"  {m.memory_id} {m.feedback_label.value}: {m.signal_pattern}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
