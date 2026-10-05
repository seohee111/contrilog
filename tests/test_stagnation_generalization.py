"""Stagnation anti-overfitting: ID·이름·noise 변경, 같은 신호 구조의 새 막힘/정상 진행 시나리오."""

import pytest

from contrilog.schemas import ReplySemantic, StagnationState as S
from tests.stagnation_fixtures import GT, evaluate, kst, metrics, monitor, remap_gt, remap_json, rename_text, unit_runs
from tests.test_claim_agent_generalization import _noise


@pytest.fixture(scope="module")
def baseline():
    _, _, _, runs = monitor()
    return {e.case_id: metrics(e) for e in evaluate(runs)}


def _same(runs, gt, baseline):
    got = {e.case_id: metrics(e) for e in evaluate(runs, gt)}
    assert got == baseline


def test_case_id_change(baseline):
    _, _, _, runs = monitor()
    gt = GT.model_copy(update={"stagnations": [s.model_copy(update={"case_id": s.case_id.replace("CASE0", "CASE1")
                                                                    if s.case_id != "CASE10" else "CASE01"})
                                               for s in GT.stagnations]})
    got = sorted(metrics(e).items() for e in evaluate(runs, gt))
    want = sorted(baseline[c].items() for c in ["CASE03", "CASE04", "CASE10"])
    assert got == want


TASK_MAP = {f"T{i:02d}": f"T{i + 50:02d}" for i in range(1, 12)}
MEMBER_MAP = {"M_A": "M_W", "M_B": "M_X", "M_C": "M_Y", "M_D": "M_Z"}


@pytest.mark.parametrize("mapping", [TASK_MAP, MEMBER_MAP], ids=["task_ids", "member_ids"])
def test_id_changes(tmp_path, baseline, mapping):
    remap = lambda obj: remap_json(obj, mapping)  # noqa: E731
    _, _, _, runs = monitor(tmp_path, input_transform=remap, simulation_transform=remap, decisions_transform=remap)
    gt = remap_gt(mapping)
    got = {e.case_id: metrics(e) for e in evaluate(runs, gt)}
    assert got == baseline
    c10 = next(e for e in evaluate(runs, gt) if e.case_id == "CASE10")
    assert c10.supporter_selected == mapping.get("M_B", "M_B")


def test_name_change(tmp_path, baseline):
    _, _, _, runs = monitor(tmp_path, input_transform=rename_text, simulation_transform=rename_text,
                            decisions_transform=rename_text)
    _same(runs, GT, baseline)


def test_unrelated_noise(tmp_path, baseline):
    _, _, _, runs = monitor(tmp_path, input_transform=_noise)
    _same(runs, GT, baseline)


# ---------------------------------------------------------------- 새 시나리오
def _task(tid, member, title, created, doc, due):
    return {"task_id": tid, "project_id": "P001", "title": title, "description": title, "created_by": "M_B",
            "created_at": created, "assignee_ids": [member], "due_date": due, "status": "IN_PROGRESS",
            "due_date_history": [], "related_document_ids": [doc], "depends_on_task_ids": [],
            "status_history": [{"changed_at": created, "changed_by": "M_B", "from_status": None, "to_status": "TODO",
                                "note": None},
                               {"changed_at": created.replace("T09:00", "T10:00"), "changed_by": member,
                                "from_status": "TODO", "to_status": "IN_PROGRESS", "note": None}]}


def _rev(rid, doc, title, author, at, summary, diff=""):
    return {"revision_id": rid, "project_id": "P001", "document_id": doc, "document_title": title,
            "document_type": "CODE", "author_id": author, "edited_at": at, "change_summary": summary,
            "diff_excerpt": diff or summary, "chars_added": 300, "chars_deleted": 0}


def _status_reply(rid, member, task, start, end, text):
    return {"reply_id": rid, "project_id": "P001", "trigger": "CHECKIN", "responder_id": member,
            "about_member_id": member, "task_id": task, "available_from": start, "available_until": end,
            "reply_text": text, "reply_delay_minutes": 30, "question_intent": "STATUS_CHECK"}


def _blocked_world(raw):
    task = _task("T21", "M_A", "알림 메일 발송", "2026-10-03T09:00:00+09:00", "DOC-MAILER", "2026-10-12")
    task["status"] = "DONE"  # 수정 다음 날 완료 처리
    task["status_history"].append({"changed_at": "2026-10-08T12:00:00+09:00", "changed_by": "M_A",
                                   "from_status": "IN_PROGRESS", "to_status": "DONE", "note": None})
    raw["tasks"].append(task)
    raw["document_history"] += [
        _rev("REV-941", "DOC-NOTIFY", "deploy/notify/smtp.env", "M_D", "2026-09-20T15:00:00+09:00",
             "알림 메일 SMTP 설정 정리 (앱 비밀번호 인증 방식)"),
        _rev("REV-940", "DOC-MAILER", "server/services/mailer.py", "M_A", "2026-10-04T10:00:00+09:00",
             "알림 메일 발송 모듈 초안 (SMTP 연결)", "+ smtp.login(user, password)"),
        _rev("REV-942", "DOC-MAILER", "server/services/mailer.py", "M_A", "2026-10-07T15:00:00+09:00",
             "SMTP 인증 방식 수정 (앱 비밀번호 적용)"),
    ]
    return raw


def _blocked_sim(sim):
    return sim + [
        _status_reply("SIM-940", "M_A", "T21", "2026-10-06T00:00:00+09:00", "2026-10-09T00:00:00+09:00",
                      "SMTP 인증 오류 때문에 메일 발송을 진행하지 못하고 있어요. 원인을 못 찾겠어요."),
        {"reply_id": "SIM-941", "project_id": "P001", "trigger": "SUPPORT_REQUEST", "responder_id": "M_D",
         "about_member_id": "M_A", "task_id": "T21", "available_from": "2026-10-06T00:00:00+09:00",
         "available_until": "2026-10-09T00:00:00+09:00", "reply_text": "네, 오늘 같이 볼게요. 앱 비밀번호 설정을 확인해 봐요.",
         "reply_delay_minutes": 40, "question_intent": None}]


def _blocked_decisions(decisions):
    return decisions + [{"decision_id": "HDC-940", "project_id": "P001", "approver_id": "M_A", "decision": "APPROVE",
                         "action_type": "SUPPORT_REQUEST", "task_id": "T21", "about_member_id": "M_A",
                         "available_from": "2026-10-06T00:00:00+09:00", "available_until": "2026-10-09T00:00:00+09:00",
                         "delay_minutes": 20, "note": None}]


def test_new_blocked_scenario_full_flow(tmp_path):
    _, _, human, runs = monitor(tmp_path, input_transform=_blocked_world, simulation_transform=_blocked_sim,
                                decisions_transform=_blocked_decisions)
    (r,) = unit_runs(runs, "T21", "M_A")
    assert r.state_sequence == [S.NORMAL, S.STAGNATION_CANDIDATE, S.CONFIRMED_BLOCK, S.RESOLVED]
    assert r.check_ins[0].reply_interpretations[0].semantic == ReplySemantic.REPORTS_BLOCKED
    assert r.support_analysis.selected_member_id == "M_D"
    assert r.support_analysis.candidates and "REV-941" in r.support_analysis.reason
    assert [h.changed_by for h in r.intervention.status_history] == [None, "M_A", None]
    assert r.support_interactions[0].reply_interpretations[0].semantic == ReplySemantic.ACCEPTS_SUPPORT
    assert r.transitions[-1].source_ids == ["REV-942"]
    # 기존 Case 결과는 그대로
    assert {e.case_id: e.all_correct for e in evaluate(runs)} == {"CASE03": True, "CASE04": True, "CASE10": True}


def _on_track_world(raw):
    raw["tasks"].append(_task("T22", "M_B", "프로젝트 회고 문서 정리", "2026-10-03T09:00:00+09:00", "DOC-RETRO",
                              "2026-10-11"))
    raw["document_history"] += [
        _rev("REV-943", "DOC-RETRO", "회고 문서", "M_B", "2026-10-03T12:00:00+09:00", "회고 문서 목차 초안"),
        _rev("REV-944", "DOC-RETRO", "회고 문서", "M_B", "2026-10-07T17:30:00+09:00", "회고 본문 업로드")]
    return raw


def _on_track_sim(sim):
    return sim + [_status_reply("SIM-943", "M_B", "T22", "2026-10-04T00:00:00+09:00", "2026-10-11T00:00:00+09:00",
                                "로컬에서 작업 중이고 내일 17:30에 올릴 예정이에요. 막힌 건 없어요.")]


def test_new_on_track_scenario_low_activity_is_not_block(tmp_path):
    _, _, _, runs = monitor(tmp_path, input_transform=_on_track_world, simulation_transform=_on_track_sim)
    rs = unit_runs(runs, "T22", "M_B")
    assert rs and rs[0].state_sequence == [S.NORMAL, S.STAGNATION_CANDIDATE, S.NORMAL]
    assert rs[0].check_ins[0].reply_interpretations[0].semantic == ReplySemantic.REPORTS_ON_TRACK
    assert not [r for r in rs if S.CONFIRMED_BLOCK in r.state_sequence] and all(r.intervention is None for r in rs)


def test_case04_variant_different_on_track_wording(tmp_path):
    def reword(sim):
        for r in sim:
            if r["task_id"] == "T04" and r["question_intent"] == "STATUS_CHECK":
                r["reply_text"] = "오프라인 노트북에서 정리하느라 공유 기록이 없었어요. 문제 없고 수요일에 한꺼번에 올려요."
        return sim
    _, _, _, runs = monitor(tmp_path, simulation_transform=reword)
    e = {x.case_id: x for x in evaluate(runs)}["CASE04"]
    assert e.candidate_detected and e.reply_semantic == ReplySemantic.REPORTS_ON_TRACK
    assert not e.confirmed_block and e.final_state == S.NORMAL and e.all_correct


def test_case03_and_new_blocked_differ_only_by_block_kind(tmp_path):
    """Case03(외부 승인 대기)은 지원을 제안하지 않고, 팀 내부 문제는 제안한다 — 같은 규칙에서 갈린다."""
    _, _, _, runs = monitor(tmp_path, input_transform=_blocked_world, simulation_transform=_blocked_sim,
                            decisions_transform=_blocked_decisions)
    r03, r21 = unit_runs(runs, "T03", "M_C")[0], unit_runs(runs, "T21", "M_A")[0]
    assert (r03.support_analysis.block_kind, r21.support_analysis.block_kind) == ("EXTERNAL_DEPENDENCY", "INTERNAL_ISSUE")
    assert r03.intervention is None and r21.intervention is not None
