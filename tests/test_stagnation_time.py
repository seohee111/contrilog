"""Stagnation 미래 정보 누출: 응답·승인·지원 응답·해결 근거는 실제로 일어난 뒤에만 보인다."""

from contrilog.schemas import ActionStatus, StagnationState as S
from contrilog.simulation.loader import load_human_decisions
from tests.stagnation_fixtures import kst, monitor, unit_runs

DECISIONS = load_human_decisions("P001")


def _t11(runs):
    return unit_runs(runs, "T11", "M_C")[0]


def test_no_reply_before_it_arrives():
    _, _, _, runs = monitor(until=kst(10, 8, 21, 10))  # 후보·질문 직후, 응답(30분 지연) 전
    r = _t11(runs)
    assert r.state_sequence == [S.NORMAL, S.STAGNATION_CANDIDATE]
    assert r.check_ins[0].reply_ids == [] and r.support_analysis is None


def test_no_support_sent_before_approval(tmp_path):
    def slow(ds):
        for d in ds:
            d["delay_minutes"] = 180
        return ds
    _, _, _, runs = monitor(tmp_path / "a", decisions_transform=slow, until=kst(10, 9, 0, 30))
    r = _t11(runs)
    assert r.intervention.status == ActionStatus.PROPOSED and not r.support_interactions
    _, _, _, runs = monitor(tmp_path / "b", decisions_transform=slow)
    hist = _t11(runs).intervention.status_history
    approved = next(h for h in hist if h.status == ActionStatus.APPROVED)
    sent = next(h for h in hist if h.status == ActionStatus.SENT)
    assert approved.changed_at >= hist[0].changed_at.replace() and sent.changed_at >= approved.changed_at


def test_without_human_decision_support_is_never_sent_and_no_support_reply(tmp_path):
    session, _, _, runs = monitor(tmp_path, decisions_transform=lambda ds: [])
    r = _t11(runs)
    assert r.intervention.status == ActionStatus.PROPOSED and not r.support_interactions
    assert not [c for c in session.call_log if c.tool_name == "SupportRequestTool" and c.operation == "send"]
    inbox_ids = {rid for c in session.call_log if c.tool_name == "InboxTool" for rid in c.returned_reply_ids}
    assert len(inbox_ids) == sum(len(c.reply_ids) for rr in runs for c in rr.check_ins)  # 지원 응답은 없음
    # 해결은 지원 여부가 아니라 실제 후속 근거로만 판단된다
    assert r.final_state == S.RESOLVED and r.transitions[-1].source_ids == ["REV-058"]


def test_not_resolved_before_fix_then_resolved_after():
    _, _, _, runs = monitor(until=kst(10, 9, 22, 39))
    assert _t11(runs).final_state == S.CONFIRMED_BLOCK
    _, _, _, runs = monitor(until=kst(10, 10, 9))
    assert _t11(runs).final_state == S.RESOLVED


def test_follow_up_never_uses_records_after_its_own_time():
    _, _, _, runs = monitor()
    from contrilog.data_access import load_project_input

    full = load_project_input("P001")
    times = {r.revision_id: r.edited_at for r in full.document_history}
    for r in runs:
        for f in r.follow_ups:
            for sid in f.new_source_ids:
                if sid in times:
                    assert f.reference_at < times[sid] <= f.at
        for e in r.timeline:
            for sid in e.source_ids:
                if sid in times:
                    assert times[sid] <= e.at


def test_human_decision_data_is_only_environment_side():
    assert DECISIONS and all(d.action_type.value == "SUPPORT_REQUEST" for d in DECISIONS)
