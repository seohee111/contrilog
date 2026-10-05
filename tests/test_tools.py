"""Tool 동작: 원본 ID 추적성, 판단 비포함, Human-in-the-loop, ClaimTool 구분, 호출 로그."""

import json
import typing

import pytest

import contrilog.tools.results as R
from contrilog.data_access import load_project_input
from contrilog.schemas import ActionStatus, ClaimStatus, ContributionType, StagnationState, ToolCallLog
from contrilog.simulation.loader import load_simulated_replies
from contrilog.tools import ToolError, ToolSession
from tests.timeline_helpers import kst

FULL = load_project_input("P001")
SOURCE_IDS = FULL.source_record_ids() | {c.claim_id for c in FULL.claims}


@pytest.fixture
def session():
    return ToolSession("P001", kst(10, 9, 12), clock=lambda: kst(10, 9, 12))


# ---------------------------------------------------------------- 원본 ID 추적성
def test_every_returned_source_id_points_to_original_record():
    session = ToolSession("P001", kst(10, 16))
    t = session.tools
    results = [t["ProjectStatusTool"].get_status(), t["MeetingSearchTool"].search(limit=200),
               t["DocumentHistoryTool"].search(limit=200), t["MessageSearchTool"].search(limit=200),
               t["ClaimTool"].list_claims()]
    for r in results:
        assert r.source_ids(), r.tool_name
        assert set(r.source_ids()) <= SOURCE_IDS, r.tool_name


def test_search_hit_fields_match_original_records(session):
    revs = {r.revision_id: r for r in FULL.document_history}
    for hit in session.tools["DocumentHistoryTool"].search(query="기간 필터").items:
        orig = revs[hit.source_id]
        assert (hit.author_id, hit.edited_at, hit.document_id, hit.diff_excerpt) == (
            orig.author_id, orig.edited_at, orig.document_id, orig.diff_excerpt)
    utt = {u.utterance_id: u for u in FULL.utterances}
    for hit in session.tools["MeetingSearchTool"].search(query="타임라인").items:
        assert hit.text == utt[hit.source_id].text and hit.speaker_id == utt[hit.source_id].speaker_id


def test_search_filters(session):
    t = session.tools
    assert {h.speaker_id for h in t["MeetingSearchTool"].search(speaker_id="M_D").items} == {"M_D"}
    assert {h.author_id for h in t["DocumentHistoryTool"].search(author_id="M_C").items} == {"M_C"}
    mine = t["MessageSearchTool"].search(participant_id="M_C").items
    assert mine and all("M_C" in (h.sender_id, *h.recipient_ids) for h in mine)
    thread = t["MessageSearchTool"].search(thread_root_id="MSG-020").source_ids()
    assert thread == ["MSG-020", "MSG-021", "MSG-022", "MSG-023"]
    assert t["MeetingSearchTool"].search(query="타임라인 nginx", match="all").source_ids() == []
    assert "UT-MT03-05" in t["MeetingSearchTool"].search(query="타임라인 nginx", match="any").source_ids()
    assert t["MeetingSearchTool"].search(query="타임라인 구현", match="all").source_ids() == ["UT-MT03-05"]
    newest = t["MessageSearchTool"].search(order="desc", limit=1)
    assert newest.items[0].sent_at == max(m.sent_at for m in session.snapshot.messages)
    assert newest.total_matched == len(session.snapshot.messages)
    with pytest.raises(ToolError):
        t["MeetingSearchTool"].search(speaker_id="M_Z")
    with pytest.raises(ToolError):
        t["MessageSearchTool"].search(limit=0)


# ---------------------------------------------------------------- 판단 비포함
def _annotation_types(model):
    for f in model.model_fields.values():
        yield from _flatten(f.annotation)


def _flatten(tp):
    yield tp
    for a in typing.get_args(tp):
        yield from _flatten(a)


def test_tool_results_contain_no_judgment_fields():
    banned_words = ["stagnation", "blocked", "verdict", "judg", "score", "rank", "rating", "weight", "point",
                    "contribution_type", "importance", "risk"]
    models = [getattr(R, n) for n in dir(R) if isinstance(getattr(R, n), type)
              and issubclass(getattr(R, n), R.BaseModel) and getattr(R, n).__module__ == R.__name__]
    assert models
    for m in models:
        for name in m.model_fields:
            assert not any(w in name.lower() for w in banned_words), f"{m.__name__}.{name}"
        assert StagnationState not in set(_annotation_types(m)), m.__name__


def test_project_status_is_observation_only(session):
    (t11,) = session.tools["ProjectStatusTool"].get_status(task_id="T11").tasks
    assert set(t11.model_dump()) >= {"status", "due_date", "assignee_ids", "last_task_activity",
                                     "hours_since_last_task_activity", "hours_until_due_end"}
    assert t11.last_task_activity.source_id == "REV-055"
    assert t11.hours_since_last_task_activity == pytest.approx(43.8)


def test_original_claims_are_not_judged(session):
    session.advance_to(kst(10, 16))
    for c in session.tools["ClaimTool"].list_claims().items:
        assert c.origin == "SUBMITTED" and c.status == ClaimStatus.PENDING_VERIFICATION and c.claimed_type is None


# ---------------------------------------------------------------- ClaimTool: 원본 / atomic 구분
def test_claim_tool_keeps_original_and_agent_derived_separate():
    s = ToolSession("P001", kst(10, 16))
    claims = s.tools["ClaimTool"]
    a = claims.register_atomic_claim(parent_claim_id="CLM-06", claimed_type="IDEA", text="Timeline UI 아이디어 제안")
    b = claims.register_atomic_claim(parent_claim_id="CLM-06", claimed_type=ContributionType.EXECUTION,
                                     text="Timeline UI 구현")
    assert [a.items[0].source_id, b.items[0].source_id] == ["CLM-06-01", "CLM-06-02"]
    items = {c.source_id: c for c in claims.list_claims(member_id="M_A").items}
    assert items["CLM-06"].origin == "SUBMITTED" and items["CLM-06"].claimed_type is None
    assert items["CLM-06-01"].origin == "AGENT_DERIVED" and items["CLM-06-01"].parent_claim_id == "CLM-06"
    assert items["CLM-06-01"].status == ClaimStatus.PENDING_VERIFICATION
    assert "CLM-06-01" not in claims.list_claims(include_agent_derived=False).source_ids()
    # 입력 데이터(원본 Claim)는 변하지 않는다
    assert not [c for c in s.snapshot.claims if c.parent_claim_id]
    with pytest.raises(ToolError):
        claims.register_atomic_claim(parent_claim_id="CLM-06", claimed_type="LEADERSHIP", text="x")


def test_claim_tool_cannot_split_future_claim():
    s = ToolSession("P001", kst(10, 15, 20, 11))
    with pytest.raises(ToolError, match="not found"):
        s.tools["ClaimTool"].register_atomic_claim(parent_claim_id="CLM-06", claimed_type="IDEA", text="x")


# ---------------------------------------------------------------- Human-in-the-loop
def test_support_request_requires_human_approval(session):
    sr = session.tools["SupportRequestTool"]
    aid = sr.propose(task_id="T11", about_member_id="M_C", supporter_id="M_B",
                     message="Evidence 검색 문제 같이 봐주실 수 있을까요?").actions[0].action_id
    with pytest.raises(ToolError, match="only APPROVED"):
        sr.send(action_id=aid)
    assert not hasattr(sr, "approve")
    assert all("approve" not in op for t in session.tools.values() for op in t.operations())
    with pytest.raises(ToolError):
        session.human.approve(aid, "M_Z")
    approved = session.human.approve(aid, "M_A", note="좋아요")
    assert approved.status == ActionStatus.APPROVED and approved.status_history[-1].changed_by == "M_A"
    sent = sr.send(action_id=aid).actions[0]
    assert [h.status for h in sent.status_history] == [ActionStatus.PROPOSED, ActionStatus.APPROVED, ActionStatus.SENT]
    with pytest.raises(ToolError):
        session.human.approve(aid, "M_A")  # 이미 SENT


def test_rejected_request_cannot_be_sent(session):
    sr = session.tools["SupportRequestTool"]
    aid = sr.propose(task_id="T11", about_member_id="M_C", supporter_id="M_B", message="지원 요청").actions[0].action_id
    session.human.reject(aid, "M_C", note="혼자 해볼게요")
    with pytest.raises(ToolError):
        sr.send(action_id=aid)
    assert [a.status for a in sr.list_requests(status="REJECTED").actions] == [ActionStatus.REJECTED]


def test_reallocation_proposal_never_changes_task(session):
    sr = session.tools["SupportRequestTool"]
    before = session.tools["ProjectStatusTool"].get_status(task_id="T11").tasks[0].assignee_ids
    aid = sr.propose(task_id="T11", about_member_id="M_C", supporter_id="M_B", message="재배분 제안",
                     intervention_type="REALLOCATION").actions[0].action_id
    session.human.approve(aid, "M_A")
    sr.send(action_id=aid)
    session.advance_to(kst(10, 9, 13))
    after = session.tools["ProjectStatusTool"].get_status(task_id="T11").tasks[0].assignee_ids
    assert before == after == ["M_C"]


def test_support_reply_arrives_only_after_sent():
    s = ToolSession("P001", kst(10, 9, 9))
    sr = s.tools["SupportRequestTool"]
    aid = sr.propose(task_id="T11", about_member_id="M_C", supporter_id="M_B", message="지원 요청").actions[0].action_id
    s.advance_to(kst(10, 9, 12))
    assert s.tools["InboxTool"].list_replies().replies == []  # 제안만으로는 아무에게도 전달되지 않음
    s.human.approve(aid, "M_A")
    s.advance_to(kst(10, 9, 14))
    assert s.tools["InboxTool"].list_replies().replies == []  # 승인만으로도 전달되지 않음
    sr.send(action_id=aid)
    s.advance_to(kst(10, 9, 15))
    (reply,) = s.tools["InboxTool"].list_replies(action_id=aid).replies
    assert reply.responder_id == "M_B"


# ---------------------------------------------------------------- Tool 호출 로그
def test_call_log_records_required_fields(session):
    t = session.tools
    r1 = t["MeetingSearchTool"].search(query="타임라인")
    t["CheckInTool"].send(task_id="T11", member_id="M_C", question="Claim 검증 API 진행 상황이 궁금해요")
    with pytest.raises(ToolError):
        t["DocumentHistoryTool"].search(author_id="M_Q")
    log = session.call_log
    assert [c.sequence for c in log] == [1, 2, 3]
    first = log[0]
    assert (first.tool_name, first.operation, first.project_id) == ("MeetingSearchTool", "search", "P001")
    assert first.as_of == session.as_of and first.logged_at == kst(10, 9, 12)
    assert first.parameters == {"query": "타임라인"}
    assert first.returned_source_ids == r1.source_ids() and first.result_count == len(r1.items)
    assert log[1].returned_action_ids == ["ACT-001"]
    assert log[1].parameters["question"] == {"redacted_chars": len("Claim 검증 API 진행 상황이 궁금해요")}
    assert log[2].status.value == "ERROR" and log[2].returned_source_ids == []


def test_call_log_does_not_copy_raw_text(session, tmp_path):
    t = session.tools
    t["MessageSearchTool"].search(limit=200)
    t["MeetingSearchTool"].search(limit=200)
    t["DocumentHistoryTool"].search(limit=200)
    t["CheckInTool"].send(task_id="T11", member_id="M_C", question="비밀스러운 질문 원문입니다")
    session.advance_to(kst(10, 9, 13))
    t["InboxTool"].list_replies()
    path = session.export_call_log(tmp_path / "calls.jsonl")
    text = path.read_text(encoding="utf-8")
    assert "비밀스러운 질문 원문" not in text
    for m in FULL.messages + FULL.utterances:
        assert m.text not in text
    for r in load_simulated_replies("P001"):
        assert r.reply_text not in text
    assert "SIM-" not in text  # 시뮬레이션 내부 ID도 남지 않음
    rows = [ToolCallLog.model_validate(json.loads(line)) for line in text.splitlines()]
    assert len(rows) == 5 and rows[-1].returned_reply_ids == ["RPL-001"]


def test_call_log_is_reproducible():
    def run():
        s = ToolSession("P001", kst(9, 18, 10), clock=lambda: kst(9, 18, 10))
        s.tools["ProjectStatusTool"].get_status(member_id="M_C")
        s.tools["CheckInTool"].send(task_id="T03", member_id="M_C", question="진행 상황?")
        s.advance_to(kst(9, 18, 12))
        s.tools["InboxTool"].list_replies()
        return [c.model_dump(mode="json") for c in s.call_log], [r.model_dump(mode="json")
                                                                 for r in s.tools["InboxTool"].list_replies().replies]
    assert run() == run()
