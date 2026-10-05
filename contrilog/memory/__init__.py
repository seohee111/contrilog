"""Agent Memory: Agent 자신의 과거 판단과 그 결과(피드백)를 저장하고, 이후 판단을 제한적으로 보정한다.

- store.py      : 저장소 (append-only, created_at·원천 AgentDecision 추적). InMemory / JSONL 파일
- retrieval.py  : 상황(MemoryContext) 기준 검색. 판단 시각 이전에 만들어진 Memory만 돌려준다
- adjustment.py : 피드백 → 허용 공백 보정 (상한·하한·1회 조정폭이 있는 bounded adjustment)

사람을 학습하지 않는다: Memory에는 사람 식별 필드가 없고, 검색 키는 상황 구간뿐이다.
"""

from .adjustment import AdjustmentBounds, MemoryAdjustment, compute_adjustment
from .retrieval import MemoryRetriever
from .store import InMemoryMemoryStore, JsonlMemoryStore, MemoryStore

__all__ = ["AdjustmentBounds", "InMemoryMemoryStore", "JsonlMemoryStore", "MemoryAdjustment", "MemoryRetriever",
           "MemoryStore", "compute_adjustment"]
