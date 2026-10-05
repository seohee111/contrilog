"""3단계 전 수정 사항: due_date 이력, RPL-* Evidence 허용, 개인 DM 접근 차단."""

import json

import pytest
from pydantic import ValidationError

from contrilog.data_access import build_snapshot, load_project_input
from contrilog.data_access.access_policy import apply_access_policy
from contrilog.schemas import AgentDecision, ContributionEvidence, Task
from contrilog.schemas import ground_truth as G
from contrilog.tools import ToolSession
from tests.timeline_helpers import GRID, SEC, expected_agent_message_ids, kst, raw

FULL = load_project_input("P001")
CHANGE_AT = kst(10, 1, 14)  # T10 마감일 변경 시각 (일정 순서 조정)
DM_IDS = {m.message_id for m in FULL.messages if m.channel_type.value == "DIRECT_MESSAGE"}
DM_TEXTS = [m.text for m in FULL.messages if m.message_id in DM_IDS]


# ================================================================ 1. due_date history
def _t10(as_of):
    return next(t for t in build_snapshot(FULL, as_of).tasks if t.task_id == "T10")


def test_t10_due_date_before_change_is_previous_value():
    t = _t10(CHANGE_AT - SEC)
    assert t.due_date.isoformat() == "2026-10-09" and t.due_date_history == []
    t = _t10(kst(9, 28, 19, 24))  # 생성 직후
    assert t.due_date.isoformat() == "2026-10-09"


def test_t10_due_date_from_change_time_is_new_value():
    t = _t10(CHANGE_AT)
    assert t.due_date.isoformat() == "2026-10-07"
    (change,) = t.due_date_history
    assert (change.from_due_date.isoformat(), change.to_due_date.isoformat()) == ("2026-10-09", "2026-10-07")


def test_future_due_date_never_visible_in_past_snapshots():
    for as_of in GRID:
        if as_of < CHANGE_AT and as_of >= kst(9, 28, 19, 24):
            dumped = json.dumps(_t10(as_of).model_dump(mode="json"))
            assert "2026-10-07" not in dumped, as_of


def test_project_status_tool_reports_due_date_as_of():
    s = ToolSession("P001", CHANGE_AT - SEC)
    (t10,) = s.tools["ProjectStatusTool"].get_status(task_id="T10").tasks
    before_hours = t10.hours_until_due_end
    assert t10.due_date.isoformat() == "2026-10-09" and t10.due_date_history == []
    s.advance_to(CHANGE_AT)
    (t10,) = s.tools["ProjectStatusTool"].get_status(task_id="T10").tasks
    assert t10.due_date.isoformat() == "2026-10-07" and len(t10.due_date_history) == 1
    assert t10.hours_until_due_end == pytest.approx(before_hours - 48, abs=0.1)


def test_tasks_without_changes_keep_due_date():
    final = {t["task_id"]: t["due_date"] for t in raw()["tasks"]}
    snap = build_snapshot(FULL, kst(10, 16))
    for t in snap.tasks:
        assert t.due_date.isoformat() == final[t.task_id]
        if t.task_id != "T10":
            assert t.due_date_history == []


def _task_with(history):
    data = raw()["tasks"][9]  # T10
    return Task.model_validate({**data, "due_date_history": history})


def test_due_date_history_schema_rules():
    ok = {"changed_at": "2026-10-01T14:00:00+09:00", "changed_by": "M_B",
          "from_due_date": "2026-10-09", "to_due_date": "2026-10-07"}
    assert _task_with([ok]).initial_due_date.isoformat() == "2026-10-09"
    with pytest.raises(ValidationError):  # 마지막 변경값과 due_date 불일치
        _task_with([{**ok, "to_due_date": "2026-10-08"}])
    with pytest.raises(ValidationError):  # 생성 이전 변경
        _task_with([{**ok, "changed_at": "2026-09-20T00:00:00+09:00"}])
    with pytest.raises(ValidationError):  # 같은 날짜로 '변경'
        _task_with([{**ok, "from_due_date": "2026-10-07"}])
    with pytest.raises(ValidationError):  # 체인 끊김
        _task_with([ok, {**ok, "changed_at": "2026-10-02T00:00:00+09:00", "from_due_date": "2026-10-05",
                         "to_due_date": "2026-10-07"}])


# ================================================================ 2. RPL-* Evidence
T0 = kst(10, 9, 12)


def _evidence(source_type, source_id):
    return ContributionEvidence(
        evidence_id="EV-001", project_id="P001", member_id="M_C", source_type=source_type, source_id=source_id,
        relation="SUPPORTS", excerpt="...", collected_at=T0)


def _decision(source_ids):
    return AgentDecision(
        decision_id="DEC-001", project_id="P001", decision_type="FOLLOW_UP", as_of=T0, created_at=T0,
        source_ids=source_ids, rationale="...", confidence="MEDIUM")


def test_rpl_evidence_allowed():
    assert _evidence("INBOUND_REPLY", "RPL-001").source_id == "RPL-001"
    assert _decision(["RPL-001", "REV-055", "MSG-036"]).source_ids[0] == "RPL-001"


@pytest.mark.parametrize("bad", ["SIM-001", "SIM-004", "ACT-001", "TC-0001", "RPL-1", "rpl-001"])
def test_simulation_and_other_internal_ids_rejected_as_evidence(bad):
    with pytest.raises(ValidationError):
        _evidence("INBOUND_REPLY", bad)
    with pytest.raises(ValidationError):
        _decision([bad])


def test_rpl_source_type_must_match():
    with pytest.raises(ValidationError):
        _evidence("MESSAGE", "RPL-001")
    with pytest.raises(ValidationError):
        _evidence("INBOUND_REPLY", "MSG-036")


def test_ground_truth_still_rejects_runtime_reply_ids():
    """RPL-* 번호는 실행마다 달라지므로 Ground Truth의 expected evidence에는 쓸 수 없다."""
    with pytest.raises(ValidationError):
        G.GroundTruthContribution(
            gt_contribution_id="GTC-99", case_id="CASE10", project_id="P001", member_id="M_B",
            contribution_type="SUPPORT", description="x", expected_evidence_ids=["RPL-001"])


def test_reply_received_through_tool_can_be_cited_as_evidence():
    s = ToolSession("P001", kst(10, 8, 10))
    s.tools["CheckInTool"].send(task_id="T11", member_id="M_C", question="진행 상황이 궁금해요")
    s.advance_to(kst(10, 8, 11))
    (reply,) = s.tools["InboxTool"].list_replies().replies
    ev = _evidence("INBOUND_REPLY", reply.reply_id)
    assert ev.source_id == reply.reply_id and not ev.source_id.startswith("SIM-")


# ================================================================ 3. 개인 DM 접근 차단
@pytest.fixture
def session():
    return ToolSession("P001", kst(10, 16))


def _all_tool_text(s):
    t = s.tools
    outs = [t["MessageSearchTool"].search(limit=200), t["ProjectStatusTool"].get_status(),
            t["MeetingSearchTool"].search(limit=200), t["DocumentHistoryTool"].search(limit=200),
            t["ClaimTool"].list_claims()]
    return "\n".join(json.dumps(o.model_dump(mode="json"), ensure_ascii=False) for o in outs), outs


def test_data_still_contains_dms():
    """원본 데이터는 삭제하지 않았다 — 정책으로만 차단한다."""
    assert DM_IDS == {"MSG-012", "MSG-013", "MSG-038", "MSG-039", "MSG-040"}


def test_public_channel_messages_searchable(session):
    r = session.tools["MessageSearchTool"].search(limit=200)
    assert set(r.source_ids()) == expected_agent_message_ids(kst(10, 16))
    assert {"MSG-020", "MSG-021", "MSG-036"} <= set(r.source_ids())
    assert {h.channel for h in r.items} <= {"#general", "#dev", "#docs"}
    assert "MSG-021" in session.tools["MessageSearchTool"].search(query="nginx").source_ids()


@pytest.mark.parametrize("query", ["밀리초", "1000 곱하면", "보안팀에 organization 승인 건", "봐 주실 수 있을까요",
                                   "고쳤어요", "대시보드 API 먼저"])
def test_query_cannot_reach_dm(session, query):
    assert set(session.tools["MessageSearchTool"].search(query=query, match="any", limit=200).source_ids()) \
        .isdisjoint(DM_IDS)


@pytest.mark.parametrize("params", [
    {"channel_type": "DIRECT_MESSAGE"},
    {"channel": "dm"},
    {"participant_id": "M_C", "channel_type": "DIRECT_MESSAGE"},
    {"participant_id": "M_B"},
    {"sender_id": "M_C", "channel": "dm"},
    {"thread_root_id": "MSG-038"},
    {"thread_root_id": "MSG-012"},
    {"start": kst(10, 9, 19), "end": kst(10, 9, 23)},
])
def test_filters_cannot_reach_dm(session, params):
    r = session.tools["MessageSearchTool"].search(limit=200, **params)
    assert set(r.source_ids()).isdisjoint(DM_IDS)
    if params.get("channel_type") == "DIRECT_MESSAGE" or params.get("channel") == "dm" or "thread_root_id" in params:
        assert r.items == [] and r.total_matched == 0


def test_full_listing_and_every_tool_output_exclude_dm(session):
    text, outs = _all_tool_text(session)
    for dm_id in DM_IDS:
        assert f'"{dm_id}"' not in text, dm_id
    for dm_text in DM_TEXTS:
        assert dm_text not in text
    for out in outs:
        assert set(out.source_ids()).isdisjoint(DM_IDS)


def test_project_status_last_message_is_never_dm():
    # 10/9 22:45 시점 C의 가장 최근 메시지는 DM(MSG-040, 22:45)이지만 Agent에게는 공유 채널 기록만 보인다
    s = ToolSession("P001", kst(10, 9, 22, 50))
    members = {m.member_id: m for m in s.tools["ProjectStatusTool"].get_status().members}
    assert members["M_C"].last_message.source_id == "MSG-036"
    assert members["M_B"].last_message.source_id not in DM_IDS


def test_session_snapshot_and_call_log_exclude_dm(session):
    assert not [m for m in session.snapshot.messages if m.message_id in DM_IDS]
    session.tools["MessageSearchTool"].search(query="밀리초")
    session.tools["MessageSearchTool"].search(limit=200)
    for c in session.call_log:
        assert set(c.returned_source_ids).isdisjoint(DM_IDS)


def test_dm_policy_holds_at_every_time():
    s = ToolSession("P001", GRID[0])
    for as_of in GRID:
        s.advance_to(as_of)
        ids = set(s.tools["MessageSearchTool"].search(limit=200).source_ids())
        assert ids == expected_agent_message_ids(as_of) and ids.isdisjoint(DM_IDS)


def test_reply_pointer_to_dm_is_removed():
    """공유 채널 메시지가 DM에 답장한 경우에도 DM ID가 드러나지 않아야 한다."""
    snap = build_snapshot(FULL, kst(10, 16))
    leaked = snap.messages[0].model_copy(update={"reply_to_message_id": "MSG-038"})
    snap = snap.model_copy(update={"messages": [leaked, *snap.messages[1:]]})
    filtered = apply_access_policy(snap)
    assert filtered.messages[0].reply_to_message_id is None
    assert not [m for m in filtered.messages if m.message_id in DM_IDS]


def test_time_only_snapshot_is_unchanged_by_policy():
    """시간 필터(build_snapshot)는 데이터 계층 그대로 DM을 포함한다. 정책은 Agent용 session에서만 적용."""
    assert DM_IDS <= {m.message_id for m in build_snapshot(FULL, kst(10, 16)).messages}
