"""미래 정보 누출 테스트 (2단계 핵심).

번호는 요구사항 7절의 1~10번에 대응한다.
"""

import json
from datetime import timedelta

import pytest

from contrilog.data_access.snapshot import SnapshotTimeError
from contrilog.simulation.loader import load_simulated_replies
from contrilog.tools import ToolError, ToolSession
from tests.timeline_helpers import (
    GRID,
    SEC,
    expected_agent_message_ids,
    expected_task_status,
    expected_visible_ids,
    kst,
    raw,
    ts,
)

REPLIES = {r.reply_id: r for r in load_simulated_replies("P001")}


def observe_everything(session: ToolSession) -> str:
    """Agent가 Tool로 볼 수 있는 모든 것을 한 문자열로 모은다."""
    t = session.tools
    outs = [
        t["ProjectStatusTool"].get_status(),
        t["MeetingSearchTool"].search(limit=200),
        t["DocumentHistoryTool"].search(limit=200),
        t["MessageSearchTool"].search(limit=200),
        t["ClaimTool"].list_claims(),
        t["InboxTool"].list_replies(),
    ]
    return "\n".join(json.dumps(o.model_dump(mode="json"), ensure_ascii=False) for o in outs)


def observed_ids(session: ToolSession) -> set[str]:
    t = session.tools
    ids = set()
    for o in [t["MeetingSearchTool"].search(limit=200), t["DocumentHistoryTool"].search(limit=200),
              t["MessageSearchTool"].search(limit=200), t["ClaimTool"].list_claims()]:
        ids |= set(o.source_ids())
    ids |= {v.source_id for v in t["ProjectStatusTool"].get_status().tasks}
    return ids


# ---------------------------------------------------------------- 1. Case03 확인 이전
def test_01_case03_block_reply_not_visible_before_checkin():
    s = ToolSession("P001", kst(9, 18, 9))
    seen = observe_everything(s)
    reply = REPLIES["SIM-001"].reply_text
    assert reply not in seen
    for fragment in ["관리자 승인", "승인 요청 메일", "보안팀", "403으로 막혀"]:
        assert fragment not in seen, fragment
    ids = observed_ids(s)
    assert {"UT-MT04-02", "MSG-012", "MSG-013"}.isdisjoint(ids)  # 9/21 이후의 공개 확인 기록
    assert "REV-014" in ids  # 과거 기록(9/15 403 로깅 커밋)은 정상적으로 보인다
    assert s.tools["InboxTool"].list_replies().replies == []


# ---------------------------------------------------------------- 2. CheckInTool 호출 후에만 응답
def test_02_reply_only_after_checkin_call_and_delay():
    s = ToolSession("P001", kst(9, 18, 10))
    s.advance_to(kst(9, 21, 18))  # 질문하지 않고 시간만 흘려도
    assert s.tools["InboxTool"].list_replies().replies == []  # 응답은 오지 않는다

    s = ToolSession("P001", kst(9, 18, 10))
    sent = s.tools["CheckInTool"].send(task_id="T03", member_id="M_C", question="GitHub 연동 진행 상황이 궁금해요.")
    assert REPLIES["SIM-001"].reply_text not in json.dumps(sent.model_dump(mode="json"), ensure_ascii=False)
    assert s.tools["InboxTool"].list_replies().replies == []  # 보낸 즉시는 없음
    delay = timedelta(minutes=REPLIES["SIM-001"].reply_delay_minutes)
    s.advance_to(kst(9, 18, 10) + delay - SEC)
    assert s.tools["InboxTool"].list_replies().replies == []  # 도착 1초 전에도 없음
    s.advance_to(kst(9, 18, 10) + delay)
    (reply,) = s.tools["InboxTool"].list_replies().replies
    assert reply.text == REPLIES["SIM-001"].reply_text
    assert reply.action_id == sent.actions[0].action_id and reply.received_at == kst(9, 18, 10) + delay


def test_02b_checkin_outside_reply_window_or_to_wrong_target_gets_nothing():
    s = ToolSession("P001", kst(9, 15, 12))  # SIM-001 유효 구간(9/15 18:00~) 이전
    s.tools["CheckInTool"].send(task_id="T03", member_id="M_C", question="진행 상황 어떠세요?")
    s.advance_to(kst(9, 16, 12))
    assert s.tools["InboxTool"].list_replies().replies == []

    s = ToolSession("P001", kst(9, 18, 10))
    s.tools["CheckInTool"].send(task_id="T05", member_id="M_A", question="타임라인 뷰 진행 상황 어떠세요?")
    s.advance_to(kst(9, 20))
    assert s.tools["InboxTool"].list_replies().replies == []


def test_02c_same_simulated_reply_delivered_once():
    s = ToolSession("P001", kst(9, 18, 10))
    for _ in range(3):
        s.tools["CheckInTool"].send(task_id="T03", member_id="M_C", question="진행 상황 어떠세요?")
    s.advance_to(kst(9, 19))
    assert len(s.tools["InboxTool"].list_replies().replies) == 1


def test_02d_checkin_rejects_non_assignee_and_future_task_without_leaking():
    s = ToolSession("P001", kst(9, 20))
    with pytest.raises(ToolError, match="not an assignee"):
        s.tools["CheckInTool"].send(task_id="T03", member_id="M_D", question="?")
    with pytest.raises(ToolError) as future:  # T11은 9/28 생성
        s.tools["CheckInTool"].send(task_id="T11", member_id="M_C", question="?")
    with pytest.raises(ToolError) as missing:
        s.tools["CheckInTool"].send(task_id="T99", member_id="M_C", question="?")
    assert str(future.value).replace("T11", "X") == str(missing.value).replace("T99", "X")


# ---------------------------------------------------------------- 3. Case04 확인 이전
def test_03_case04_local_work_unknown_before_checkin():
    s = ToolSession("P001", kst(9, 18, 10))
    seen = observe_everything(s)
    assert REPLIES["SIM-003"].reply_text not in seen
    d_texts = [h.text for h in s.tools["MessageSearchTool"].search(sender_id="M_D", limit=200).items]
    d_texts += [h.text for h in s.tools["MeetingSearchTool"].search(speaker_id="M_D", limit=200).items]
    d_texts += [h.change_summary + h.diff_excerpt
                for h in s.tools["DocumentHistoryTool"].search(author_id="M_D", limit=200).items]
    assert not [t for t in d_texts if "로컬" in t]
    assert {"MSG-014", "UT-MT04-05"}.isdisjoint(observed_ids(s))
    # 질문한 뒤에야 알 수 있다
    s.tools["CheckInTool"].send(task_id="T04", member_id="M_D", question="데이터셋 작업 진행 상황 어떠세요?")
    s.advance_to(kst(9, 18, 11))
    (reply,) = s.tools["InboxTool"].list_replies().replies
    assert "로컬" in reply.text


# ---------------------------------------------------------------- 4. Case04 업로드 이전
def test_04_case04_future_revisions_hidden_before_upload():
    s = ToolSession("P001", kst(9, 23, 13, 19))
    doc = s.tools["DocumentHistoryTool"]
    assert {"REV-019", "REV-020"}.isdisjoint(set(doc.search(limit=200).source_ids()))
    assert doc.search(document_id="DOC-DATASET").items == []
    assert doc.search(query="41,280행").items == []
    (t04,) = s.tools["ProjectStatusTool"].get_status(task_id="T04").tasks
    assert t04.status.value == "IN_PROGRESS" and "DOC-DATASET" not in t04.related_document_ids
    assert t04.last_task_activity.source_id == "REV-012"
    s.advance_to(kst(9, 23, 13, 25))
    assert "REV-020" in doc.search(document_id="DOC-DATASET").source_ids()


# ---------------------------------------------------------------- 5. Case10 해결 이전
def test_05_case10_resolution_hidden_before_fix():
    s = ToolSession("P001", kst(10, 9, 22, 39))
    (t11,) = s.tools["ProjectStatusTool"].get_status(task_id="T11").tasks
    assert t11.status.value == "IN_PROGRESS"
    assert [h.to_status.value for h in t11.status_history] == ["TODO", "IN_PROGRESS"]
    ids = observed_ids(s)
    assert {"REV-058", "REV-059", "MSG-040", "MSG-041", "UT-MT07-02"}.isdisjoint(ids)
    assert "MSG-036" in ids  # 과거 공유 채널 메시지는 정상적으로 보인다
    assert {"MSG-038", "MSG-039"}.isdisjoint(ids)  # 이미 존재하지만 개인 DM이라 Agent 접근 불가
    assert s.tools["DocumentHistoryTool"].search(query="ms epoch").items == []
    s.advance_to(kst(10, 10, 11, 14))
    (t11,) = s.tools["ProjectStatusTool"].get_status(task_id="T11").tasks
    assert t11.status.value == "IN_PROGRESS" and "REV-058" in s.tools["DocumentHistoryTool"].search(limit=200).source_ids()
    s.advance_to(kst(10, 10, 11, 15))
    (t11,) = s.tools["ProjectStatusTool"].get_status(task_id="T11").tasks
    assert t11.status.value == "DONE"


# ---------------------------------------------------------------- 6. Task 과거 상태 복원
@pytest.mark.parametrize("as_of,expected", [
    (kst(9, 5), "TODO"),
    (kst(9, 7, 20), "IN_PROGRESS"),
    (kst(9, 20), "DONE"),
    (kst(9, 29, 12), "IN_PROGRESS"),  # 누수 수정으로 다시 열림
    (kst(9, 30, 10, 49), "IN_PROGRESS"),
    (kst(9, 30, 10, 50), "DONE"),
])
def test_06_task_status_restored_at_as_of(as_of, expected):
    s = ToolSession("P001", as_of)
    (t02,) = s.tools["ProjectStatusTool"].get_status(task_id="T02").tasks
    assert t02.status.value == expected == expected_task_status("T02", as_of)
    assert all(h.changed_at <= as_of for h in t02.status_history)
    assert t02.status_since == t02.status_history[-1].changed_at


def test_06b_final_status_not_returned_for_past_as_of():
    final = {t["task_id"]: t["status"] for t in raw()["tasks"]}
    s = ToolSession("P001", kst(10, 3, 17))
    status = {v.source_id: v.status.value for v in s.tools["ProjectStatusTool"].get_status().tasks}
    assert final["T11"] == "DONE" and status["T11"] == "IN_PROGRESS"
    assert final["T09"] == "DONE" and status["T09"] == "IN_PROGRESS"
    assert final["T10"] == "DONE" and status["T10"] == "IN_PROGRESS"


def test_06c_tasks_not_yet_created_are_invisible():
    s = ToolSession("P001", kst(9, 28, 19, 23, 59))  # T10: 19:24, T11: 19:25 생성
    tasks = {v.source_id for v in s.tools["ProjectStatusTool"].get_status().tasks}
    assert "T11" not in tasks and "T10" not in tasks
    s.advance_to(kst(9, 28, 19, 24))
    tasks = {v.source_id for v in s.tools["ProjectStatusTool"].get_status().tasks}
    assert "T10" in tasks and "T11" not in tasks
    s.advance_to(kst(9, 28, 19, 25))
    tasks = {v.source_id for v in s.tools["ProjectStatusTool"].get_status().tasks}
    assert {"T10", "T11"} <= tasks


# ---------------------------------------------------------------- 7~10. 검색 Tool 별 미래 기록 차단
SEARCH_CASES = [
    ("MeetingSearchTool", "search", "utterances", "spoken_at"),
    ("DocumentHistoryTool", "search", "document_history", "edited_at"),
    ("MessageSearchTool", "search", "messages", "sent_at"),
    ("ClaimTool", "list_claims", "claims", "submitted_at"),
]


@pytest.mark.parametrize("tool,op,key,time_field", SEARCH_CASES, ids=[c[0] for c in SEARCH_CASES])
def test_07_to_10_search_tools_never_return_future_records(tool, op, key, time_field):
    """7: MeetingSearchTool, 8: DocumentHistoryTool, 9: MessageSearchTool, 10: ClaimTool."""
    s = ToolSession("P001", GRID[0])
    for as_of in sorted(GRID + [kst(10, 15, 20, 11), kst(10, 16, 23, 59)]):
        s.advance_to(as_of)
        params = {"limit": 200} if op == "search" else {}
        result = getattr(s.tools[tool], op)(**params)
        for item in result.items:
            assert getattr(item, time_field) <= as_of, item.source_id
        # 미래 차단만이 아니라 과거 기록 누락도 없어야 한다 (메시지는 개인 DM 제외 정책 적용)
        expected = expected_agent_message_ids(as_of) if key == "messages" else expected_visible_ids(as_of)[key]
        assert set(result.source_ids()) == expected, as_of


@pytest.mark.parametrize("tool", ["MeetingSearchTool", "DocumentHistoryTool", "MessageSearchTool"])
def test_07_to_09_end_parameter_cannot_reach_future(tool):
    s = ToolSession("P001", kst(10, 1))
    r = s.tools[tool].search(start=kst(9, 28), end=kst(10, 16), limit=200)
    assert r.items and set(r.source_ids()) <= {
        *expected_visible_ids(kst(10, 1))["utterances"], *expected_visible_ids(kst(10, 1))["document_history"],
        *expected_visible_ids(kst(10, 1))["messages"]}


def test_07_meeting_search_hides_meeting_in_progress():
    s = ToolSession("P001", kst(9, 28, 19, 30))  # MT05 진행 중, D의 발표 구성 제안(19:15) 직후
    assert s.tools["MeetingSearchTool"].search(query="4단").items == []
    s.advance_to(kst(9, 28, 20, 5))
    assert "UT-MT05-04" in s.tools["MeetingSearchTool"].search(query="4단").source_ids()


def test_10_claim_tool_only_returns_submitted_claims():
    s = ToolSession("P001", kst(10, 15, 20, 11))
    assert set(s.tools["ClaimTool"].list_claims().source_ids()) == {"CLM-09", "CLM-01"}
    s.advance_to(kst(10, 15, 20, 15))
    assert "CLM-06" in s.tools["ClaimTool"].list_claims().source_ids()


# ---------------------------------------------------------------- 시간 역행 차단
def test_session_time_cannot_move_backward():
    s = ToolSession("P001", kst(10, 9, 23))
    with pytest.raises(SnapshotTimeError):
        s.advance_to(kst(10, 9, 22))
