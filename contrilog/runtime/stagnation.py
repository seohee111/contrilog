"""정체 모니터링 실행기 (환경 계층).

Agent는 시간을 옮기지 않고 next_wake_time()으로 다음에 깨워 달라는 시각만 알린다.
이 실행기는 그 시각(또는 사람의 결정 시각)으로 시간을 옮기고, 사람의 결정을 적용한 뒤 Agent를 깨운다.
사람의 결정은 주입된 human 객체(process(session), next_due())가 HumanApprovalGate로 적용한다.
"""

from datetime import datetime, timedelta


def run_stagnation_monitoring(session, agent, until: datetime, human=None) -> None:
    agent.step()
    while True:
        wakes = [t for t in (agent.next_wake_time(), human.next_due() if human else None) if t is not None]
        if human:
            human.process(session)  # 방금 Agent가 만든 제안을 결정 일정에 올린다
            wakes += [t for t in [human.next_due()] if t is not None]
        if not wakes:
            break
        wake = max(min(wakes), session.as_of + timedelta(minutes=1))
        if wake > until:
            break
        session.advance_to(wake)
        if human:
            human.process(session)
        agent.step()
