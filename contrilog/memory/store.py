"""Memory 저장소 (append-only).

- 이미 저장된 Memory를 고치거나 지우는 API가 없다. 같은 memory_id를 다시 넣으면 거부한다.
- memory_id는 저장 순서대로 부여된다 (MEM-001, MEM-002, ...).
- JsonlMemoryStore는 한 줄에 Memory 하나를 덧붙여 쓰므로 실행 간 유지되고 이력이 보존된다.
"""

import json
from pathlib import Path
from typing import Protocol

from contrilog.schemas import AgentMemory


class MemoryStore(Protocol):
    def next_id(self) -> str: ...
    def append(self, memory: AgentMemory) -> AgentMemory: ...
    def all(self) -> list[AgentMemory]: ...


class InMemoryMemoryStore:
    def __init__(self, memories: list[AgentMemory] | None = None):
        self._items: list[AgentMemory] = []
        for m in memories or []:
            self.append(m)

    def next_id(self) -> str:
        return f"MEM-{len(self._items) + 1:03d}"

    def append(self, memory: AgentMemory) -> AgentMemory:
        if any(m.memory_id == memory.memory_id for m in self._items):
            raise ValueError(f"memory {memory.memory_id} already exists (append-only)")
        self._items.append(memory.model_copy(deep=True))
        return memory

    def all(self) -> list[AgentMemory]:
        return [m.model_copy(deep=True) for m in self._items]


class JsonlMemoryStore(InMemoryMemoryStore):
    """파일에 한 줄씩 덧붙인다. 다시 열면 기존 Memory를 읽어 이어서 쓴다."""

    def __init__(self, path: Path):
        self.path = Path(path)
        super().__init__()
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        super().append(AgentMemory.model_validate(json.loads(line)))

    def append(self, memory: AgentMemory) -> AgentMemory:
        super().append(memory)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(memory.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return memory
