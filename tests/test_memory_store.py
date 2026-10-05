"""Memory 저장소(append-only, 영속), 상황 기준 검색, bounded adjustment 단위 테스트."""

from dataclasses import replace

import pytest

from contrilog.memory import AdjustmentBounds, InMemoryMemoryStore, JsonlMemoryStore, MemoryRetriever, compute_adjustment
from contrilog.schemas import AgentMemory, DecisionOutcome, DecisionType, FeedbackLabel, MemoryContext
from tests.timeline_helpers import kst

CTX = MemoryContext(kind="CANDIDATE", deadline_bucket="DUE_96_168H", idle_ratio_bucket="0_5_TO_1",
                    task_status="IN_PROGRESS", team_context="TEAM_ACTIVE")
OTHER = CTX.model_copy(update={"deadline_bucket": "DUE_LE_48H"})


def mem(store, label, at, context=CTX, signal="REPORTS_ON_TRACK", evidence=("T90",)):
    return store.append(AgentMemory(
        memory_id=store.next_id(), project_id="P001", created_at=at, source_decision_ids=["DEC-00001"],
        decision_type=DecisionType.STAGNATION_ASSESSMENT, signal_pattern="x", agent_judgment="x",
        observed_outcome=DecisionOutcome.UNKNOWN, lesson="x", feedback_label=label, context=context,
        observed_signal=signal, evidence_ids=list(evidence)))


def test_store_is_append_only():
    store = InMemoryMemoryStore()
    m = mem(store, FeedbackLabel.FALSE_POSITIVE, kst(9, 20))
    with pytest.raises(ValueError):
        store.append(m)
    assert not [n for n in dir(store) if n in ("update", "delete", "remove", "replace", "clear")]
    copy = store.all()[0]
    copy.lesson = "changed"
    assert store.all()[0].lesson == "x"  # 꺼낸 사본을 바꿔도 원본은 그대로


def test_jsonl_store_persists_history(tmp_path):
    path = tmp_path / "memory.jsonl"
    first = JsonlMemoryStore(path)
    mem(first, FeedbackLabel.FALSE_POSITIVE, kst(9, 20))
    mem(first, FeedbackLabel.TRUE_POSITIVE, kst(9, 21))
    lines = path.read_text(encoding="utf-8").splitlines()
    second = JsonlMemoryStore(path)  # 다시 열면 이어서
    assert [m.memory_id for m in second.all()] == ["MEM-001", "MEM-002"] and second.next_id() == "MEM-003"
    mem(second, FeedbackLabel.UNRESOLVED, kst(9, 22))
    after = path.read_text(encoding="utf-8").splitlines()
    assert after[:2] == lines and len(after) == 3  # 기존 줄은 바뀌지 않는다


def test_retrieval_by_context_and_strictly_past():
    store = InMemoryMemoryStore()
    a = mem(store, FeedbackLabel.FALSE_POSITIVE, kst(9, 20))
    mem(store, FeedbackLabel.FALSE_POSITIVE, kst(9, 20), context=OTHER)
    r = MemoryRetriever(store)
    assert r.retrieve(CTX, kst(9, 20)) == []  # 같은 시각에 만들어진 Memory도 쓰지 않는다
    assert [m.memory_id for m in r.retrieve(CTX, kst(9, 21))] == [a.memory_id]


def test_context_has_no_identity_and_evidence_is_not_a_key():
    assert not [f for f in MemoryContext.model_fields if any(w in f for w in ("member", "task_id", "name", "person"))]
    store = InMemoryMemoryStore()
    mem(store, FeedbackLabel.FALSE_POSITIVE, kst(9, 20), evidence=("T01",))
    mem(store, FeedbackLabel.FALSE_POSITIVE, kst(9, 20), evidence=("T99",))
    assert len(MemoryRetriever(store).retrieve(CTX, kst(9, 21))) == 2


def _adj(labels, due=100.0, bounds=None, signal="ACTIVITY_RESUMED_WITHOUT_REPLY"):
    store = InMemoryMemoryStore()
    for label in labels:
        mem(store, label, kst(9, 20), signal=signal if label == FeedbackLabel.UNRESOLVED else "x")
    return compute_adjustment(store.all(), due, bounds)


FP, TP, UN = FeedbackLabel.FALSE_POSITIVE, FeedbackLabel.TRUE_POSITIVE, FeedbackLabel.UNRESOLVED


@pytest.mark.parametrize("labels,hours", [
    ([], 0), ([FP], 12), ([FP, FP], 24), ([FP, FP, FP, FP], 24),  # 1회 12h, 최대 24h
    ([FP, TP], 0), ([FP, FP, TP], 12), ([TP], 0), ([TP, TP], 0),  # TP는 되돌리지만 기본값보다 엄격하게는 안 함
    ([UN, UN, UN, UN], 0),  # UNRESOLVED는 기본적으로 근거가 아니다
])
def test_bounded_adjustment(labels, hours):
    assert _adj(labels).hours == hours


def test_weak_unresolved_variant_and_deadline_guard():
    weak = replace(AdjustmentBounds(), weak_unresolved_weight=0.5)
    assert _adj([UN, UN], bounds=weak).hours == 12
    assert _adj([UN, UN], bounds=weak, signal="NO_REPLY").hours == 0
    assert _adj([FP, FP], due=20.0).hours == 0  # 마감 24시간 이내는 보정 안 함
