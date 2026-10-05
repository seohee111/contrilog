"""Stagnation Detection / Verification / Intervention Agent (결정적 구현).

- StagnationThresholds   : 기준값 (Memory 단계에서 보정할 대상)
- StagnationPolicy       : 관찰 신호 조합 → STAGNATION_CANDIDATE
- interpret_*_reply      : 응답 → ReplySemantic
- SupportCandidateSelector: 막힌 Task의 지원 후보 (근거 기록 기반, 점수 없음)
- resolution_evidence    : 후속 관찰 → RESOLVED 근거
- StagnationAgent        : (Task, 담당자) 단위 상태 머신 (Agent-facing Tool만 사용)
- FeedbackSettings       : Memory ON/OFF, 팀 전체 휴지기 맥락 (feedback=None이면 기존 정책 그대로)
"""

from .agent import TOOL_OPERATIONS, StagnationAgent
from .context import ContextThresholds
from .feedback import FeedbackAwarePolicy, FeedbackSettings
from .interpreter import interpret_status_reply, interpret_support_reply
from .policy import StagnationPolicy
from .support import SupportCandidateSelector
from .thresholds import StagnationThresholds

__all__ = [
    "ContextThresholds",
    "FeedbackAwarePolicy",
    "FeedbackSettings",
    "TOOL_OPERATIONS",
    "StagnationAgent",
    "StagnationPolicy",
    "StagnationThresholds",
    "SupportCandidateSelector",
    "interpret_status_reply",
    "interpret_support_reply",
]
