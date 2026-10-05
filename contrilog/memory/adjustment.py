"""피드백 → 허용 공백(idle limit) 보정. 무제한 변경을 막는 bounded adjustment.

같은 상황에서 쌓인 피드백으로 '근거 점수(net)'를 계산한다 (사람 점수가 아니라 Agent 판단의 사후 결과 집계):
  FALSE_POSITIVE               +1.0  (확인해 보니 정상 진행 — 불필요한 후보였다)
  TRUE_POSITIVE                -1.0  (실제 막힘 — 완화를 되돌린다)
  UNRESOLVED                    0    (실제 상태를 확인하지 못했으므로 근거로 쓰지 않는다; 기본값)
  ※ weak_unresolved_weight를 0.5로 주면 '답은 없었지만 Task가 스스로 진행된' UNRESOLVED를 약한 근거로 쓴다
    (비교 실험용 변형. P001 재생에서는 질문을 줄이지 못하고 실제 Block 탐지만 12시간 늦췄다).
보정 = clamp(floor(net) × step_hours, 0, max_relax_hours)
- 완화만 한다 (기본값보다 엄격하게 만들지 않는다). TRUE_POSITIVE는 완화를 기본값 쪽으로 되돌린다.
- 마감까지 no_adjust_within_due_hours 이내인 Task에는 보정하지 않는다 (마감 직전 Block 보호).
"""

import math
from dataclasses import dataclass, field

from contrilog.schemas import AgentMemory, FeedbackLabel

WEAK_UNRESOLVED_SIGNALS = ("ACTIVITY_RESUMED_WITHOUT_REPLY", "TASK_COMPLETED_WITHOUT_REPLY")


@dataclass(frozen=True)
class AdjustmentBounds:
    step_hours: float = 12.0  # 1회 조정폭
    min_relax_hours: float = 0.0  # 최소 (기본값보다 엄격하게 만들지 않음)
    max_relax_hours: float = 24.0  # 최대 (허용 공백 상한 72h → 최대 96h)
    false_positive_weight: float = 1.0
    weak_unresolved_weight: float = 0.0
    true_positive_weight: float = -1.0
    no_adjust_within_due_hours: float = 24.0


@dataclass
class MemoryAdjustment:
    hours: float
    net: float
    applied_memory_ids: list[str] = field(default_factory=list)
    explanation: str = ""


def evidence_weight(memory: AgentMemory, bounds: AdjustmentBounds) -> float:
    if memory.feedback_label == FeedbackLabel.FALSE_POSITIVE:
        return bounds.false_positive_weight
    if memory.feedback_label == FeedbackLabel.TRUE_POSITIVE:
        return bounds.true_positive_weight
    if memory.feedback_label == FeedbackLabel.UNRESOLVED and memory.observed_signal in WEAK_UNRESOLVED_SIGNALS:
        return bounds.weak_unresolved_weight
    return 0.0


def compute_adjustment(memories: list[AgentMemory], hours_until_due: float,
                       bounds: AdjustmentBounds | None = None) -> MemoryAdjustment:
    bounds = bounds or AdjustmentBounds()
    used = [m for m in memories if evidence_weight(m, bounds) != 0.0]
    net = sum(evidence_weight(m, bounds) for m in used)
    ids = [m.memory_id for m in used]
    if not used:
        return MemoryAdjustment(0.0, 0.0, [], "관련 Memory 없음 → 기본 정책")
    if hours_until_due <= bounds.no_adjust_within_due_hours:
        return MemoryAdjustment(0.0, net, ids, f"마감 {bounds.no_adjust_within_due_hours:.0f}시간 이내 → 보정 안 함")
    hours = min(bounds.max_relax_hours, max(bounds.min_relax_hours, math.floor(net) * bounds.step_hours))
    labels = ", ".join(f"{m.memory_id}={m.feedback_label.value}" for m in used)
    return MemoryAdjustment(hours, net, ids, f"같은 상황의 과거 피드백 {labels} (net {net:+.1f}) → 허용 공백 +{hours:.0f}h")
