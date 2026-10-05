"""응답 해석 (결정적 단서 규칙). 결과는 공용 ReplySemantic으로 낸다.

STATUS_CHECK 응답:
  '막힌 건 없어요' 같은 명시적 부정 → REPORTS_ON_TRACK (가장 우선: '막힌'이라는 말이 있어도 막힘이 아니다)
  막힘 단서 → REPORTS_BLOCKED (+ 외부 승인·외부 의존 단서가 있으면 EXTERNAL_DEPENDENCY)
  완료·해결 단서 → CONFIRMS_COMPLETION
  진행·예정 단서 → REPORTS_ON_TRACK
  그 밖 → NOT_INFORMATIVE (Block으로 추측하지 않는다)
지원 요청 응답: 거절 단서 → DECLINES_SUPPORT, 수락 단서 → ACCEPTS_SUPPORT, 그 밖 → NOT_INFORMATIVE
"""

from contrilog.schemas import ReplySemantic

from ..claim_verification import text as T

NO_BLOCK_CUES = ("막힌 건 없", "막힌 것 없", "막힌 부분은 없", "문제 없", "문제없", "계획대로")
BLOCKED_CUES = ("막혀", "막혔", "진행할 수가 없", "진행하지 못", "못 찾", "0건", "안 나와", "오류 때문", "에러 때문",
                "403", "답이 없")
EXTERNAL_CUES = ("승인", "관리자", "조교", "외부 업체", "기다리는", "답이 없")
ON_TRACK_CUES = ("진행 중", "중이에요", "중입니다", "예정", "올릴게요", "할게요", "올려요")
ACCEPT_CUES = ("볼게요", "도울게요", "도와드릴게요", "가능해요", "할게요", "같이 볼")
DECLINE_CUES = ("어려워요", "어렵습니다", "못 할", "안 될", "불가", "시간이 없")


def interpret_status_reply(text: str) -> tuple[ReplySemantic, str | None]:
    """(의미, Block 종류). Block 종류는 막힘일 때만 INTERNAL_ISSUE / EXTERNAL_DEPENDENCY."""
    if T.has_any(text, NO_BLOCK_CUES):
        return ReplySemantic.REPORTS_ON_TRACK, None
    if T.has_any(text, BLOCKED_CUES):
        kind = "EXTERNAL_DEPENDENCY" if T.has_any(text, EXTERNAL_CUES) else "INTERNAL_ISSUE"
        return ReplySemantic.REPORTS_BLOCKED, kind
    if T.completion_state(text) == "complete":
        return ReplySemantic.CONFIRMS_COMPLETION, None
    if T.has_any(text, ON_TRACK_CUES):
        return ReplySemantic.REPORTS_ON_TRACK, None
    return ReplySemantic.NOT_INFORMATIVE, None


def interpret_support_reply(text: str) -> ReplySemantic:
    if T.has_any(text, DECLINE_CUES):
        return ReplySemantic.DECLINES_SUPPORT
    if T.has_any(text, ACCEPT_CUES) or text.strip().startswith("네"):
        return ReplySemantic.ACCEPTS_SUPPORT
    return ReplySemantic.NOT_INFORMATIVE
