"""프로젝트 전체 맥락 신호 (사람별 정보 없음).

팀 전체 휴지기(TEAM_WIDE_LOW_ACTIVITY): 관찰 가능한 공개 기록(리비전·공유 채널 메시지·회의 발언)이
누구에게서도 team_pause_hours 이상 끊긴 구간. 공휴일을 외부 지식으로 넣지 않고 데이터의 팀 전체 패턴으로만 판단한다.

- 휴지기와 겹친 공백 시간은 '이 Task만의 공백'이 아니므로 공백 계산에서 뺀다 (effective idle).
- 상황 키(MemoryContext)는 마감 구간·공백 비율 구간·Task 상태·팀 맥락으로만 만든다.
"""

from dataclasses import dataclass
from datetime import datetime

from contrilog.schemas import MemoryContext


@dataclass(frozen=True)
class ContextThresholds:
    team_pause_hours: float = 60.0  # 주말(금요일 저녁~월요일 아침, 약 60시간)보다 길게 팀 전체 기록이 끊기면 휴지기


@dataclass
class TeamContext:
    observed_at: datetime
    record_times: list
    pauses: list  # [(start, end)]
    in_pause: bool

    @property
    def label(self) -> str:
        return "TEAM_WIDE_LOW_ACTIVITY" if self.in_pause else "TEAM_ACTIVE"

    def overlap_hours(self, start: datetime, end: datetime) -> float:
        total = 0.0
        for a, b in self.pauses:
            lo, hi = max(a, start), min(b, end)
            if hi > lo:
                total += (hi - lo).total_seconds() / 3600
        return round(total, 1)


def team_context(record_times: list, now: datetime, thresholds: ContextThresholds) -> TeamContext:
    times = sorted(t for t in record_times if t <= now)
    limit = thresholds.team_pause_hours * 3600
    pauses = [(a, b) for a, b in zip(times, times[1:]) if (b - a).total_seconds() >= limit]
    in_pause = bool(times) and (now - times[-1]).total_seconds() >= limit
    if in_pause:
        pauses.append((times[-1], now))
    return TeamContext(now, times, pauses, in_pause)


def deadline_bucket(hours_until_due: float) -> str:
    if hours_until_due < 0:
        return "OVERDUE"
    if hours_until_due <= 48:
        return "DUE_LE_48H"
    if hours_until_due <= 96:
        return "DUE_48_96H"
    if hours_until_due <= 168:
        return "DUE_96_168H"
    return "DUE_GT_168H"


def idle_ratio_bucket(idle_hours: float | None, hours_until_due: float) -> str:
    ratio = (idle_hours or 0.0) / max(hours_until_due, 1.0)
    if ratio < 0.5:
        return "LT_0_5"
    return "0_5_TO_1" if ratio < 1.0 else "GE_1"


def candidate_context(hours_until_due: float, effective_idle: float | None, status: str, team: TeamContext | None):
    return MemoryContext(kind="CANDIDATE", deadline_bucket=deadline_bucket(hours_until_due),
                         idle_ratio_bucket=idle_ratio_bucket(effective_idle, hours_until_due), task_status=status,
                         team_context=team.label if team else None)
