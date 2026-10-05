"""Memory 테스트용 synthetic 시퀀스 (테스트 전용).

X(담당 A): 후보 → 정상 진행 응답 → FALSE_POSITIVE Memory
Y(담당 C): 같은 상황 → Memory 보정으로 질문 없이 넘김 → 실제로 곧 기록이 다시 생김 (불필요한 질문이었음)
Z(담당 D): 같은 상황이지만 실제 막힘 → 공백이 보정 범위를 넘어서면 후보 → 막힘 확인
"""


def _task(tid, member, title, created, doc, due):
    started = created.replace("T09:00", "T10:00")
    return {"task_id": tid, "project_id": "P001", "title": title, "description": title, "created_by": "M_B",
            "created_at": created, "assignee_ids": [member], "due_date": due, "status": "IN_PROGRESS",
            "due_date_history": [], "related_document_ids": [doc], "depends_on_task_ids": [],
            "status_history": [
                {"changed_at": created, "changed_by": "M_B", "from_status": None, "to_status": "TODO", "note": None},
                {"changed_at": started, "changed_by": member, "from_status": "TODO", "to_status": "IN_PROGRESS",
                 "note": None}]}


def _rev(rid, doc, author, at, summary):
    return {"revision_id": rid, "project_id": "P001", "document_id": doc, "document_title": doc.lower(),
            "document_type": "CODE", "author_id": author, "edited_at": at, "change_summary": summary,
            "diff_excerpt": summary, "chars_added": 200, "chars_deleted": 0}


def _status(rid, member, task, start, end, text):
    return {"reply_id": rid, "project_id": "P001", "trigger": "CHECKIN", "responder_id": member,
            "about_member_id": member, "task_id": task, "available_from": start, "available_until": end,
            "reply_text": text, "reply_delay_minutes": 30, "question_intent": "STATUS_CHECK"}


def sequence_world(raw, assignees=("M_A", "M_C", "M_D")):
    x, y, z = assignees
    raw["tasks"] += [
        _task("T31", x, "API 문서 정리", "2026-09-29T09:00:00+09:00", "DOC-APIDOC", "2026-10-06"),
        _task("T32", y, "로그 수집 스크립트 정리", "2026-09-30T09:00:00+09:00", "DOC-LOGCOL", "2026-10-07"),
        _task("T33", z, "배포 자동화 스크립트", "2026-09-30T09:00:00+09:00", "DOC-DEPLOYCI", "2026-10-07"),
    ]
    raw["document_history"] += [
        _rev("REV-951", "DOC-APIDOC", x, "2026-09-29T12:00:00+09:00", "API 문서 목차 초안"),
        _rev("REV-952", "DOC-LOGCOL", y, "2026-09-30T15:00:00+09:00", "로그 수집 스크립트 구조 정리"),
        _rev("REV-953", "DOC-DEPLOYCI", z, "2026-09-30T12:00:00+09:00", "배포 자동화 스크립트 초안"),
        _rev("REV-954", "DOC-LOGCOL", y, "2026-10-03T18:00:00+09:00", "로그 수집 스크립트 마무리"),
        _rev("REV-955", "DOC-APIDOC", x, "2026-10-03T11:00:00+09:00", "API 문서 업로드"),
    ]
    _done(raw["tasks"][-3], x, "2026-10-03T11:30:00+09:00")
    _done(raw["tasks"][-2], y, "2026-10-03T18:30:00+09:00")
    return raw


def _done(task, member, at):
    task["status"] = "DONE"
    task["status_history"].append({"changed_at": at, "changed_by": member, "from_status": "IN_PROGRESS",
                                   "to_status": "DONE", "note": None})


def sequence_sim(sim, assignees=("M_A", "M_C", "M_D")):
    x, y, z = assignees
    return sim + [
        _status("SIM-951", x, "T31", "2026-10-01T00:00:00+09:00", "2026-10-06T00:00:00+09:00",
                "로컬에서 정리 중이고 막힌 건 없어요. 내일 올릴게요."),
        _status("SIM-953", z, "T33", "2026-10-01T00:00:00+09:00", "2026-10-07T00:00:00+09:00",
                "빌드 오류 때문에 배포 스크립트를 진행하지 못하고 있어요. 원인을 못 찾겠어요."),
    ]
