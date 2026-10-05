"""Tool 공통: ToolError, operation 데코레이터(호출 로그 자동 기록), Tool base class."""

from functools import wraps
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from .session import ToolSession


class ToolError(ValueError):
    """잘못된 Tool 호출. 메시지는 미래 정보를 드러내지 않아야 한다
    (예: 아직 생성되지 않은 Task와 존재하지 않는 Task는 같은 메시지)."""


def operation(fn):
    """Tool의 공개 동작. keyword 인자만 받고, 성공/실패 모두 호출 로그에 남긴다."""

    @wraps(fn)
    def wrapper(self: "Tool", **params):
        try:
            result = fn(self, **params)
        except ToolError as e:
            self._session._record_call(self.name, fn.__name__, params, None, error=str(e))
            raise
        self._session._record_call(self.name, fn.__name__, params, result)
        return result

    wrapper.is_tool_operation = True
    return wrapper


class Tool:
    name: ClassVar[str]
    description: ClassVar[str]

    def __init__(self, session: "ToolSession"):
        self._session = session

    @property
    def snapshot(self):
        return self._session.snapshot

    @property
    def as_of(self):
        return self._session.as_of

    @property
    def project_id(self) -> str:
        return self._session.project_id

    def operations(self) -> list[str]:
        return [n for n in dir(type(self)) if getattr(getattr(type(self), n), "is_tool_operation", False)]

    # ---- 공통 검증 ----
    def _member(self, member_id: str | None) -> None:
        if member_id is not None and member_id not in {m.member_id for m in self.snapshot.members}:
            raise ToolError(f"member {member_id} not found")

    def _task(self, task_id: str):
        for t in self.snapshot.tasks:
            if t.task_id == task_id:
                return t
        raise ToolError(f"task {task_id} not found")
