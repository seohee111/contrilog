"""Interactive Claim 검증 실행기.

    session = ToolSession("P001", as_of=...)
    agent = ClaimVerificationAgent(tools=session.tools)
    run = run_interactive_verification(session, agent, "CLM-08")

1. agent.verify_claim — 최초 라운드 (필요하면 확인 질문을 보낸다)
2. 응답 대기 중인 질문이 있으면 시간을 점점 길게 진행시키며 agent.continue_verification으로 재개
3. 대기 시간(max_wait)이 끝나면 agent.finalize — 응답이 없던 질문을 닫는다
"""

from datetime import timedelta

# 응답 확인 간격 (분). 처음엔 짧게, 점점 길게. 합계 약 15.75시간.
POLL_BACKOFF_MINUTES = (15, 30, 60, 120, 240, 480)


def run_interactive_verification(session, agent, claim_id: str, *, max_wait: timedelta = timedelta(hours=24)):
    run = agent.verify_claim(claim_id=claim_id)
    deadline = session.as_of + max_wait
    polls = 0
    while run.awaiting_action_ids and session.as_of < deadline:
        step = timedelta(minutes=POLL_BACKOFF_MINUTES[min(polls, len(POLL_BACKOFF_MINUTES) - 1)])
        session.advance_to(min(session.as_of + step, deadline))
        polls += 1
        run = agent.continue_verification(run)
    return agent.finalize(run)
