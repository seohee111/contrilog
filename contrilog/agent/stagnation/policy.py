"""StagnationPolicy — 관찰 신호를 조합해 STAGNATION_CANDIDATE 여부를 정한다 (결정적 규칙).

후보 조건 (모두 충족해야 한다. '최근 활동 없음' 하나만으로는 후보가 되지 않는다):
1. started_and_open : Task가 시작되었고(IN_PROGRESS/IN_REVIEW) 아직 완료되지 않았다
2. due_soon         : 마감까지 due_window_hours 이내 (지난 마감 포함)
3. idle_beyond_limit: 마지막 Task 기록 이후 경과 시간 ≥ 남은 시간에 비례한 허용 공백
4. not_waiting_on_dependency: 미완료 선행 Task를 기다리는 중이 아니다 (기다림은 공백의 정상적인 이유)
5. not_recently_confirmed_on_track: 담당자가 최근 '정상 진행'이라고 답한 Task가 아니다 (마감 임박 전까지)
6. not_recently_asked: 최근 checkin_cooldown_hours 안에 이 Task 담당자에게 확인 질문을 보내지 않았다

후보는 '이 사람이 문제다'가 아니라 'Task 상태를 확인할 필요가 있다'는 Agent 상태다.
"""

from datetime import datetime

from contrilog.schemas import CandidateCheck, TaskSignals, TaskStatus

from .thresholds import StagnationThresholds


class StagnationPolicy:
    def __init__(self, thresholds: StagnationThresholds | None = None):
        self.thresholds = thresholds or StagnationThresholds()

    def check(self, signals: TaskSignals, trusted_until: datetime | None = None,
              last_asked_at: datetime | None = None) -> CandidateCheck:
        th = self.thresholds
        limit = th.idle_limit_hours(signals.hours_until_due_end)
        idle = signals.hours_since_last_task_activity
        conditions = {
            "started_and_open": signals.status in (TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW),
            "due_soon": signals.hours_until_due_end <= th.due_window_hours,
            "idle_beyond_limit": idle is not None and idle >= limit,
            "not_waiting_on_dependency": not signals.unfinished_dependency_ids,
            "not_recently_confirmed_on_track": trusted_until is None or signals.observed_at >= trusted_until,
            "not_recently_asked": last_asked_at is None or (
                signals.observed_at - last_asked_at).total_seconds() >= th.checkin_cooldown_hours * 3600,
        }
        reasons = []
        if conditions["due_soon"]:
            reasons.append(f"마감까지 {signals.hours_until_due_end:.1f}시간 (기준 {th.due_window_hours:.0f}시간 이내)")
        if idle is not None:
            reasons.append(f"마지막 Task 기록({signals.last_activity_source_id}) 이후 {idle:.1f}시간 "
                           f"(허용 {limit:.1f}시간)")
        if signals.unfinished_dependency_ids:
            reasons.append(f"미완료 선행 Task {', '.join(signals.unfinished_dependency_ids)} 대기 중")
        return CandidateCheck(
            observed_at=signals.observed_at, is_candidate=all(conditions.values()), conditions=conditions,
            thresholds={**th.as_dict(), "idle_limit_hours": limit}, reasons=reasons)
