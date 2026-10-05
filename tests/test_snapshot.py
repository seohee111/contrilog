"""ProjectSnapshot: as_of 이후 기록이 하나도 포함되지 않는지, 이전 기록은 빠짐없이 포함되는지."""

import json
import re

import pytest

from contrilog.data_access import get_project_snapshot, load_project_input
from contrilog.data_access.snapshot import SnapshotTimeError, build_snapshot
from tests.timeline_helpers import GRID, SEC, expected_task_status, expected_visible_ids, kst, raw, ts

FULL = load_project_input("P001")
ISO_DT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)")

ID_FIELD = {"meetings": "meeting_id", "utterances": "utterance_id", "document_history": "revision_id",
            "tasks": "task_id", "messages": "message_id", "claims": "claim_id"}


def _ids(snap, key):
    return {getattr(x, ID_FIELD[key]) for x in getattr(snap, key)}


@pytest.mark.parametrize("as_of", GRID, ids=lambda t: t.strftime("%m%d-%H"))
def test_snapshot_contains_exactly_past_records(as_of):
    snap = build_snapshot(FULL, as_of)
    expected = expected_visible_ids(as_of)
    for key in ID_FIELD:
        assert _ids(snap, key) == expected[key], key


@pytest.mark.parametrize("as_of", GRID, ids=lambda t: t.strftime("%m%d-%H"))
def test_no_datetime_after_as_of_anywhere_in_snapshot(as_of):
    """snapshot 전체를 JSON으로 직렬화해 모든 시각 문자열이 as_of 이하인지 검사
    (Task 상태 이력, 회의 종료 시각 등 중첩 필드 포함)."""
    snap = build_snapshot(FULL, as_of)
    text = json.dumps(snap.model_dump(mode="json"), ensure_ascii=False)
    for s in ISO_DT.findall(text):
        assert ts(s.replace("Z", "+00:00")) <= as_of, s


def _record_times():
    d = raw()
    for m in d["meetings"]:
        yield "meetings", m["meeting_id"], ts(m["ended_at"])
    for r in d["document_history"]:
        yield "document_history", r["revision_id"], ts(r["edited_at"])
    for t in d["tasks"]:
        yield "tasks", t["task_id"], ts(t["created_at"])
    for m in d["messages"]:
        yield "messages", m["message_id"], ts(m["sent_at"])
    for c in d["claims"]:
        yield "claims", c["claim_id"], ts(c["submitted_at"])


@pytest.mark.parametrize("key,record_id,t", list(_record_times()), ids=lambda v: v if isinstance(v, str) else "")
def test_every_record_appears_exactly_at_its_timestamp(key, record_id, t):
    """모든 기록에 대해: 1초 전 snapshot에는 없고, 그 시각 snapshot에는 있다."""
    assert record_id not in _ids(build_snapshot(FULL, t - SEC), key)
    assert record_id in _ids(build_snapshot(FULL, t), key)


def test_example_from_spec_revision_and_message_at_1900_hidden_at_1700():
    """10/03 17:00 snapshot에 10/03 19:00 기록이 보이면 실패 — 일반화: 17:00 이후 기록은 없어야 한다."""
    snap = get_project_snapshot("P001", kst(10, 3, 17))
    assert all(r.edited_at <= kst(10, 3, 17) for r in snap.document_history)
    assert all(m.sent_at <= kst(10, 3, 17) for m in snap.messages)


def test_meeting_utterances_hidden_until_meeting_ends():
    during = build_snapshot(FULL, kst(9, 21, 19, 10))  # MT04 진행 중 (19:00~19:50)
    assert "MT04" not in _ids(during, "meetings")
    assert not [u for u in during.utterances if u.meeting_id == "MT04"]
    after = build_snapshot(FULL, kst(9, 21, 19, 50))
    assert len([u for u in after.utterances if u.meeting_id == "MT04"]) == 7


def test_task_links_to_future_documents_and_tasks_are_removed():
    snap = build_snapshot(FULL, kst(9, 23, 13, 21))  # DOC-DATASET 첫 리비전(13:25) 이전
    t04 = next(t for t in snap.tasks if t.task_id == "T04")
    assert t04.related_document_ids == ["DOC-DATAGEN"]
    snap = build_snapshot(FULL, kst(9, 28, 19, 22))  # T10(19:24), T11(19:25) 생성 이전
    t09 = next(t for t in snap.tasks if t.task_id == "T09")
    assert t09.depends_on_task_ids == []


@pytest.mark.parametrize("bad", ["2026-10-03T17:00:00", None, "now"])
def test_naive_or_invalid_as_of_rejected(bad):
    from datetime import datetime

    value = datetime.fromisoformat(bad) if bad and "T" in bad else bad
    with pytest.raises(SnapshotTimeError):
        build_snapshot(FULL, value)


def test_snapshot_does_not_share_objects_with_source():
    snap = build_snapshot(FULL, kst(10, 3, 17))
    snap.tasks[0].status_history.clear()
    snap.messages[0].text = "changed"
    again = build_snapshot(FULL, kst(10, 3, 17))
    assert again.tasks[0].status_history and again.messages[0].text != "changed"


def test_task_status_matches_raw_history_on_grid():
    for as_of in GRID:
        snap = build_snapshot(FULL, as_of)
        for t in snap.tasks:
            assert t.status.value == expected_task_status(t.task_id, as_of)
            assert all(h.changed_at <= as_of for h in t.status_history)
