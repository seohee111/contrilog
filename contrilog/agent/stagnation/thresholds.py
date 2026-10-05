"""정체 판단 기준값 (정책과 분리). 이후 Memory 단계에서 보정할 대상이다.

값의 근거 (synthetic 프로젝트의 운영 리듬에서 가져옴, 특정 Case에 맞춘 값이 아님):
- due_window_hours = 168: 팀이 매주 회의로 진행 상황을 공유한다. '다음 회의 전에 마감'인 Task만 본다.
- idle_ratio_of_remaining = 0.5: 남은 시간의 절반 이상 동안 Task 기록이 없으면 확인할 가치가 있다.
- min_idle_hours = 24 / max_idle_hours = 72: 마감 직전이어도 하루 공백은 정상일 수 있고(하한),
  마감이 멀어도 사흘(주간 주기의 절반) 넘게 기록이 없으면 확인한다(상한).
- recheck_before_due_hours = 24: 담당자가 '정상 진행'이라고 답하면 마감 하루 전까지는 다시 묻지 않는다.
- reply_timeout_hours = 24: 하루 안에 답이 없으면 '확인 불가'로 기록한다 (Block으로 추측하지 않는다).
- scan_interval_hours = 12: 하루 두 번(오전·저녁) Task 상태를 본다.
- supporter_urgent_due_hours = 24: 본인 업무 마감이 하루 안에 있는 팀원에게는 지원을 제안하지 않는다.
- checkin_cooldown_hours = 48: 같은 Task 담당자에게 확인 질문을 보낸 뒤 이틀 안에는 다시 후보로 올리지 않는다
  (활동이 잠깐 재개됐다 멈춘 경우의 반복 질문 방지).
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StagnationThresholds:
    due_window_hours: float = 168.0
    idle_ratio_of_remaining: float = 0.5
    min_idle_hours: float = 24.0
    max_idle_hours: float = 72.0
    recheck_before_due_hours: float = 24.0
    reply_timeout_hours: float = 24.0
    scan_interval_hours: float = 12.0
    poll_backoff_minutes: tuple = (15, 30, 60, 120, 240, 480)
    supporter_urgent_due_hours: float = 24.0
    checkin_cooldown_hours: float = 48.0

    def idle_limit_hours(self, hours_until_due: float) -> float:
        """남은 시간이 짧을수록 허용 공백도 짧다 (하한·상한 사이)."""
        scaled = self.idle_ratio_of_remaining * max(hours_until_due, 0.0)
        return min(self.max_idle_hours, max(self.min_idle_hours, scaled))

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if isinstance(v, (int, float))}
