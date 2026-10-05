"""ContriLog에서 사용하는 모든 enum.

설계 원칙:
- ContributionType은 5개로 고정한다. 기여 "점수"나 "순위"를 표현하는 enum은 두지 않는다.
- ClaimStatus / StagnationState는 Agent의 판단 결과를 표현한다.
  Agent 입력 데이터(data/input)에는 판단 결과가 들어가지 않는다.
"""

from enum import Enum


class ContributionType(str, Enum):
    IDEA = "IDEA"
    EXECUTION = "EXECUTION"
    REVIEW = "REVIEW"
    COORDINATION = "COORDINATION"
    SUPPORT = "SUPPORT"


class ClaimStatus(str, Enum):
    """Atomic claim 하나에 대한 검증 상태.

    - VERIFIED: 주장을 뒷받침하는 Evidence가 충분하고, 반박하는 Evidence가 없다.
    - INSUFFICIENT_EVIDENCE: 주장자를 해당 행위와 연결하는 Evidence가 없거나 부족하다.
      (다른 사람의 관련 기록이 존재하더라도 주장 자체를 뒷받침하는 기록이 없으면 여기에 해당)
    - CONFLICTING_EVIDENCE: 주장을 뒷받침하는 Evidence와 반박하는 Evidence가 함께 존재한다.
    - PENDING_VERIFICATION: 아직 검증하지 않았다. 입력 데이터의 모든 Claim은 이 상태다.
    """

    VERIFIED = "VERIFIED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"


class StagnationState(str, Enum):
    """(팀원, Task) 단위의 업무 정체 상태.

    NORMAL -> STAGNATION_CANDIDATE -> (확인) -> CONFIRMED_BLOCK -> (지원/재배분) -> RESOLVED
    STAGNATION_CANDIDATE는 확정이 아니다. 확인 결과 정상이면 NORMAL로 돌아간다.
    """

    NORMAL = "NORMAL"
    STAGNATION_CANDIDATE = "STAGNATION_CANDIDATE"
    CONFIRMED_BLOCK = "CONFIRMED_BLOCK"
    RESOLVED = "RESOLVED"


class TaskStatus(str, Enum):
    """Task Board 상의 상태. 'BLOCKED' 같은 판단성 상태는 일부러 두지 않는다."""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"


class DocumentType(str, Enum):
    DESIGN_DOC = "DESIGN_DOC"
    REPORT = "REPORT"
    SLIDES = "SLIDES"
    SCHEDULE = "SCHEDULE"
    CODE = "CODE"
    CONFIG = "CONFIG"
    DATA = "DATA"
    NOTEBOOK = "NOTEBOOK"


class ChannelType(str, Enum):
    CHANNEL = "CHANNEL"
    DIRECT_MESSAGE = "DIRECT_MESSAGE"


class ClaimSource(str, Enum):
    """팀원이 Claim을 남긴 경로."""

    SELF_REPORT_FORM = "SELF_REPORT_FORM"
    MESSAGE = "MESSAGE"
    MEETING = "MEETING"


class EvidenceSourceType(str, Enum):
    """Evidence가 가리키는 원본 기록의 종류."""

    MEETING_UTTERANCE = "MEETING_UTTERANCE"
    DOCUMENT_REVISION = "DOCUMENT_REVISION"
    TASK = "TASK"
    MESSAGE = "MESSAGE"
    INBOUND_REPLY = "INBOUND_REPLY"  # Agent의 check-in / 지원 요청에 대한 응답 (RPL-*)


class EvidenceRelation(str, Enum):
    """Evidence가 Claim/기여 판단에 대해 갖는 관계."""

    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CONTEXT = "CONTEXT"


class DecisionType(str, Enum):
    CLAIM_VERIFICATION = "CLAIM_VERIFICATION"
    CONTRIBUTION_ATTRIBUTION = "CONTRIBUTION_ATTRIBUTION"
    STAGNATION_ASSESSMENT = "STAGNATION_ASSESSMENT"
    CHECKIN_REQUEST = "CHECKIN_REQUEST"
    INTERVENTION_PROPOSAL = "INTERVENTION_PROPOSAL"
    FOLLOW_UP = "FOLLOW_UP"


class InterventionType(str, Enum):
    SUPPORT = "SUPPORT"
    REALLOCATION = "REALLOCATION"
    ESCALATION = "ESCALATION"


class DecisionOutcome(str, Enum):
    """Agent 자신의 과거 판단이 사후에 어땠는지 (사람에 대한 평가가 아님)."""

    CORRECT = "CORRECT"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    FALSE_NEGATIVE = "FALSE_NEGATIVE"
    PARTIALLY_CORRECT = "PARTIALLY_CORRECT"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    """Agent 판단에 대한 Agent 자신의 확신 정도 (사람의 기여 크기와 무관)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SimulatedTrigger(str, Enum):
    """시뮬레이션 응답이 반환되는 Agent 행동."""

    CHECKIN = "CHECKIN"
    SUPPORT_REQUEST = "SUPPORT_REQUEST"


class ActionType(str, Enum):
    """Agent가 사람에게 보내는 행동의 종류 (Tool layer)."""

    CHECKIN = "CHECKIN"
    SUPPORT_REQUEST = "SUPPORT_REQUEST"


class ActionStatus(str, Enum):
    """사람에게 나가는 행동의 상태. Human-in-the-loop:

    - CHECKIN: Agent가 바로 SENT (질문은 업무를 바꾸지 않음)
    - SUPPORT_REQUEST: Agent는 PROPOSED까지만 만들 수 있다.
      사람이 APPROVED/REJECTED를 결정하고, APPROVED인 경우에만 SENT로 전달된다.
    """

    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"


class ToolCallStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"


class VerificationGapKind(str, Enum):
    """Claim이 PENDING_VERIFICATION인 이유 (Judge의 판정 규칙에서 직접 나온다).

    - COMPLETION_UNCONFIRMED: 실행의 직접 근거는 있으나 완료 근거(완료 Task·완료 보고)가 없다.
    - DIRECT_EVIDENCE_MISSING: 간접 근거(문서화·본인 보고·제3자 언급 등)만 있고 행위를 직접 보여 주는 근거가 없다.
    """

    COMPLETION_UNCONFIRMED = "COMPLETION_UNCONFIRMED"
    DIRECT_EVIDENCE_MISSING = "DIRECT_EVIDENCE_MISSING"


class HumanDecisionType(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class InteractionStatus(str, Enum):
    AWAITING_REPLY = "AWAITING_REPLY"
    ANSWERED = "ANSWERED"
    NO_REPLY = "NO_REPLY"  # 환경이 정한 대기 시간 안에 응답이 오지 않음


class QuestionIntent(str, Enum):
    """확인 질문이 확인하려는 사실 (시스템의 의미 표현. 질문 문장은 사람에게 보여 주는 표현일 뿐이다).

    - STATUS_CHECK: 진행 상황 일반 확인 ('어떻게 되어 가고 있나요?')
    - COMPLETION_CONFIRMATION: 특정 작업이 완료된 상태인지 확인
    - COUNTERPART_CONFIRMATION: 행위의 상대방에게, 주장자가 실제로 그 행위에 관여했는지 확인
    """

    STATUS_CHECK = "STATUS_CHECK"
    COMPLETION_CONFIRMATION = "COMPLETION_CONFIRMATION"
    COUNTERPART_CONFIRMATION = "COUNTERPART_CONFIRMATION"


class ReplySemantic(str, Enum):
    """확인 응답의 의미. Agent는 응답을 해석해 이 값을 남기고, Ground Truth는 기대값을 같은 enum으로 표현한다.

    Agent 근거 역할(role)과의 대응은 contrilog.agent.claim_verification.evaluator.REPLY_SEMANTIC_BY_ROLE 한 곳에 둔다.
    """

    CONFIRMS_COMPLETION = "CONFIRMS_COMPLETION"
    REPORTS_INCOMPLETE = "REPORTS_INCOMPLETE"  # (완료 확인 질문) 아직 끝나지 않음
    CONFIRMS_COUNTERPART = "CONFIRMS_COUNTERPART"
    DENIES_COUNTERPART = "DENIES_COUNTERPART"
    REPORTS_BLOCKED = "REPORTS_BLOCKED"  # (상태 확인 질문) 막혀서 진행하지 못함
    REPORTS_ON_TRACK = "REPORTS_ON_TRACK"  # (상태 확인 질문) 기록은 적지만 정상 진행 중
    ACCEPTS_SUPPORT = "ACCEPTS_SUPPORT"  # (지원 요청) 지원하겠다고 응답
    DECLINES_SUPPORT = "DECLINES_SUPPORT"  # (지원 요청) 지원할 수 없다고 응답
    NOT_INFORMATIVE = "NOT_INFORMATIVE"  # 확인하려던 사실에 답하지 않음


class FeedbackLabel(str, Enum):
    """Agent 자신의 과거 판단에 대한 사후 피드백 (Agent가 실제로 관찰한 결과로만 만든다).

    - TRUE_POSITIVE: 후보 → 확인 → 담당자가 막혀 있다고 응답
    - FALSE_POSITIVE: 후보 → 확인 → 담당자가 정상 진행(또는 완료)이라고 응답
    - UNRESOLVED: 후보 → 응답 없음·의미 불명확 → 실제 상태를 확인하지 못한 채 종료
    - RESOLUTION_SUCCESS: 지원 개입 → 이후 실제 해결 근거 관찰
    FALSE_NEGATIVE(관찰하지 않은 실제 Block)는 Ground Truth가 있어야 알 수 있으므로 Agent Memory가 만들지 않는다.
    """

    TRUE_POSITIVE = "TRUE_POSITIVE"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    UNRESOLVED = "UNRESOLVED"
    RESOLUTION_SUCCESS = "RESOLUTION_SUCCESS"
