"""ResolutionObserver — 지원 요청(또는 Block 확정) 이후 실제로 상태가 나아졌는지 Tool 관찰 결과로만 판단한다.

RESOLVED 조건: 기준 시각 이후의 관찰 가능한 후속 근거가 1건 이상 있어야 한다.
  - Task 문서에 남은 리비전 중 수정·해결을 나타내는 리비전, 또는
  - Task 상태가 IN_REVIEW / DONE으로 바뀐 기록
지원 요청을 보낸 사실, 지원 수락 응답만으로는 RESOLVED가 아니다.
"""

from ..claim_verification import text as T

FIX_CUES = ("수정", "해결", "고침", "고쳤", "fix", "복구")


def resolution_evidence(revisions_after, status_changes_after) -> tuple[list[str], list[str]]:
    """(후속 기록 전체, 해결 근거)."""
    new = [r.source_id for r in revisions_after] + [sid for sid, _ in status_changes_after]
    fixes = [r.source_id for r in revisions_after if T.has_any(r.text.casefold(), FIX_CUES)]
    advanced = [sid for sid, to_status in status_changes_after if to_status in ("IN_REVIEW", "DONE")]
    return new, list(dict.fromkeys(fixes + advanced))
