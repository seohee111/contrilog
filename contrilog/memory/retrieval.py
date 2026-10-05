"""상황 기준 Memory 검색.

검색 조건: (1) 같은 상황 키(MemoryContext.key) (2) created_at < 판단 시각 (미래 Memory 사용 불가).
사람·Task ID·이름은 검색에 쓰지 않는다 (MemoryContext에 그런 필드가 없다).
"""

from datetime import datetime

from contrilog.schemas import AgentMemory, MemoryContext


class MemoryRetriever:
    def __init__(self, store):
        self.store = store

    def retrieve(self, context: MemoryContext, as_of: datetime) -> list[AgentMemory]:
        key = context.key()
        return [m for m in self.store.all()
                if m.context is not None and m.context.key() == key and m.created_at < as_of]
