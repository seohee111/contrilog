"""결정적(deterministic) 키워드 매칭. 의미 검색·유사도 점수는 쓰지 않는다."""

from datetime import datetime
from typing import Literal

from .base import ToolError

MatchMode = Literal["all", "any"]
Order = Literal["asc", "desc"]
MAX_LIMIT = 200


def match_terms(query: str | None, fields: list[str], mode: MatchMode = "all") -> list[str] | None:
    """query의 공백 구분 단어를 대소문자 무시 부분 문자열로 찾는다.

    일치하면 찾은 단어 목록(query가 비면 [])을, 일치하지 않으면 None을 반환한다.
    """
    if mode not in ("all", "any"):
        raise ToolError("match must be 'all' or 'any'")
    if not query or not query.strip():
        return []
    terms = query.split()
    hay = "\n".join(fields).casefold()
    found = [t for t in terms if t.casefold() in hay]
    if mode == "all":
        return found if len(found) == len(terms) else None
    return found or None


def time_window(as_of: datetime, start: datetime | None, end: datetime | None) -> tuple[datetime | None, datetime]:
    """검색 구간. end는 항상 as_of 이하로 잘린다."""
    for t in (start, end):
        if t is not None and (t.tzinfo is None or t.utcoffset() is None):
            raise ToolError("start/end must be timezone-aware")
    end = as_of if end is None or end > as_of else end
    return start, end


def order_and_limit(items: list, key, order: Order, limit: int) -> list:
    if order not in ("asc", "desc"):
        raise ToolError("order must be 'asc' or 'desc'")
    if not 1 <= limit <= MAX_LIMIT:
        raise ToolError(f"limit must be between 1 and {MAX_LIMIT}")
    items = sorted(items, key=key, reverse=(order == "desc"))
    return items[:limit]
