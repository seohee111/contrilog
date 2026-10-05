"""사람의 승인·거절 시뮬레이션 (환경 계층).

Agent가 만든 지원 요청 제안(PROPOSED)을 HumanApprovalGate에서 보고, 조건이 맞는 결정 데이터가 있으면
delay_minutes 뒤에 승인·거절한다. 결정 데이터는 처음 제안이 나타났을 때 읽는다. Agent는 이 데이터를 볼 수 없다.
"""

from datetime import datetime, timedelta
from pathlib import Path

from contrilog.schemas import HumanDecisionType

from .loader import load_human_decisions


class HumanDecisionSimulator:
    def __init__(self, project_id: str, data_root: Path | None = None):
        self._project_id = project_id
        self._data_root = data_root
        self.__decisions = None
        self.__scheduled: dict[str, tuple] = {}  # action_id → (due, decision)
        self.applied: list[tuple] = []  # (at, action_id, decision_id, decision)

    def _load(self):
        if self.__decisions is None:
            self.__decisions = load_human_decisions(self._project_id, self._data_root)
        return self.__decisions

    def process(self, session) -> list[str]:
        """현재 시각에 내려야 할 결정을 적용하고, 적용한 action_id 목록을 돌려준다."""
        pending = session.human.pending()
        for action in pending:
            if action.action_id in self.__scheduled:
                continue
            for d in self._load():
                if (d.action_type == action.action_type and d.task_id == action.task_id
                        and d.about_member_id == action.about_member_id
                        and d.available_from <= action.created_at < d.available_until):
                    self.__scheduled[action.action_id] = (action.created_at + timedelta(minutes=d.delay_minutes), d)
                    break
        done = []
        pending_ids = {a.action_id for a in pending}
        for action_id, (due, d) in list(self.__scheduled.items()):
            if due <= session.as_of and action_id in pending_ids:
                if d.decision == HumanDecisionType.APPROVE:
                    session.human.approve(action_id, d.approver_id, note=d.note)
                else:
                    session.human.reject(action_id, d.approver_id, note=d.note)
                self.applied.append((session.as_of, action_id, d.decision_id, d.decision.value))
                del self.__scheduled[action_id]
                done.append(action_id)
        return done

    def next_due(self) -> datetime | None:
        return min((due for due, _ in self.__scheduled.values()), default=None)
