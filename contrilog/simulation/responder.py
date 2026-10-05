"""시뮬레이션 팀원 응답기.

격리 규칙:
- 응답 파일은 Agent가 처음으로 사람에게 행동(check-in / 지원 요청 전송)했을 때 처음 읽는다.
  생성자나 관찰 Tool은 파일을 열지 않는다.
- schedule()은 응답 존재 여부를 반환하지 않는다. 호출자는 응답이 올지 미리 알 수 없다.
- 응답은 행동 시각(sent_at)이 응답의 유효 시간 창 [available_from, available_until) 안이고,
  trigger / 받는 사람 / 대상 담당자 / Task / 질문 의도(question_intent)가 모두 일치할 때만 예약된다.
  질문 문장(자연어)은 응답 선택에 쓰지 않는다. 같은 사람·같은 Task라도 의도가 다르면 다른 응답이 선택되고,
  해당 의도의 응답이 없으면 아무 응답도 오지 않는다.
- 예약된 응답은 sent_at + reply_delay_minutes 이후에만 collect()로 꺼낼 수 있다.
- 같은 시뮬레이션 응답은 한 번만 전달된다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from contrilog.schemas import QuestionIntent, SimulatedReply, SimulatedTrigger

from .loader import load_simulated_replies

DEFAULT_REPLY_DELAY_MINUTES = 60


@dataclass(frozen=True)
class DeliveredReply:
    action_id: str
    responder_id: str
    arrives_at: datetime
    text: str


class SimulatedResponder:
    def __init__(self, project_id: str, data_root: Path | None = None):
        self._project_id = project_id
        self._data_root = data_root
        self.__replies: list[SimulatedReply] | None = None
        self.__used: set[str] = set()
        self.__pending: list[DeliveredReply] = []

    def _replies(self) -> list[SimulatedReply]:
        if self.__replies is None:
            self.__replies = load_simulated_replies(self._project_id, self._data_root)
        return self.__replies

    def schedule(
        self,
        *,
        action_id: str,
        trigger: SimulatedTrigger,
        responder_id: str,
        about_member_id: str,
        task_id: str,
        sent_at: datetime,
        question_intent: QuestionIntent | None = None,
    ) -> None:
        for r in sorted(self._replies(), key=lambda r: r.available_from):
            if (
                r.reply_id not in self.__used
                and r.trigger == trigger
                and r.responder_id == responder_id
                and r.about_member_id == about_member_id
                and r.task_id == task_id
                and r.question_intent == question_intent
                and r.available_from <= sent_at < r.available_until
            ):
                self.__used.add(r.reply_id)
                delay = r.reply_delay_minutes if r.reply_delay_minutes is not None else DEFAULT_REPLY_DELAY_MINUTES
                self.__pending.append(
                    DeliveredReply(action_id, r.responder_id, sent_at + timedelta(minutes=delay), r.reply_text)
                )
                return

    def collect(self, as_of: datetime) -> list[DeliveredReply]:
        """as_of까지 도착한 응답을 꺼낸다 (꺼낸 응답은 pending에서 제거)."""
        due = sorted((p for p in self.__pending if p.arrives_at <= as_of), key=lambda p: p.arrives_at)
        self.__pending = [p for p in self.__pending if p.arrives_at > as_of]
        return due
