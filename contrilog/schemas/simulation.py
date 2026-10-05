"""시뮬레이션 응답.

응답 선택 조건: trigger, 응답자, 대상 담당자, Task, 유효 시간 창, 그리고 확인 질문(CHECKIN)이면
질문 의도(question_intent)까지 일치해야 한다. 질문 문장은 보지 않는다.

실제 서비스에서는 Agent가 팀원에게 질문(check-in)하거나 지원을 요청하면 사람이 답한다.
synthetic MVP에서는 그 답을 미리 작성해 두고, Agent가 해당 시간 창 안에서 해당 행동을
했을 때만 tool을 통해 돌려준다. 정답 라벨이 아니라 '사람이 했을 법한 자연어 답변'이다.
"""

from typing import Optional

from pydantic import AwareDatetime, model_validator

from .base import HumanDecisionId, MemberId, ProjectId, SimulatedReplyId, StrictModel, TaskId
from .enums import ActionType, HumanDecisionType, QuestionIntent, SimulatedTrigger


class SimulatedReply(StrictModel):
    reply_id: SimulatedReplyId
    project_id: ProjectId
    trigger: SimulatedTrigger
    responder_id: MemberId  # 질문을 받는 사람
    about_member_id: MemberId  # 질문 대상 업무의 담당자
    task_id: TaskId
    available_from: AwareDatetime
    available_until: AwareDatetime
    reply_text: str
    reply_delay_minutes: Optional[int] = None
    question_intent: Optional[QuestionIntent] = None  # CHECKIN 응답이면 필수, 지원 요청 응답이면 None

    @model_validator(mode="after")
    def _check_window(self):
        if self.available_until <= self.available_from:
            raise ValueError("available_until must be after available_from")
        if self.trigger == SimulatedTrigger.CHECKIN and self.question_intent is None:
            raise ValueError("CHECKIN reply requires question_intent")
        if self.trigger == SimulatedTrigger.SUPPORT_REQUEST and self.question_intent is not None:
            raise ValueError("SUPPORT_REQUEST reply has no question_intent")
        return self


class SimulatedHumanDecision(StrictModel):
    """사람(팀원)이 Agent의 개입 제안을 승인·거절하는 사건 (환경 계층 전용).

    runtime이 HumanApprovalGate를 통해 적용한다. 조건(행동 종류·Task·지원받는 담당자)이 맞는 제안이
    시간 창 안에서 만들어지면 delay_minutes 뒤에 결정이 내려진다. 조건이 맞는 결정이 없으면 제안은
    PROPOSED로 남는다 (사람이 결정하지 않은 상태). Agent는 이 데이터를 볼 수 없다.
    """

    decision_id: HumanDecisionId
    project_id: ProjectId
    approver_id: MemberId
    decision: HumanDecisionType
    action_type: ActionType  # 결정 대상 행동 (현재는 SUPPORT_REQUEST만 사람 승인이 필요)
    task_id: TaskId
    about_member_id: MemberId
    available_from: AwareDatetime
    available_until: AwareDatetime
    delay_minutes: int
    note: Optional[str] = None

    @model_validator(mode="after")
    def _check(self):
        if self.available_until <= self.available_from:
            raise ValueError("available_until must be after available_from")
        if self.delay_minutes < 0:
            raise ValueError("delay_minutes must be >= 0")
        if self.action_type != ActionType.SUPPORT_REQUEST:
            raise ValueError("only SUPPORT_REQUEST needs a human decision")
        return self
