"""웹 화면용 ViewModel (읽기 전용 adapter).

DemoRun.state()가 주는 사건 목록만으로는 화면에 보여 주기 어려운 정보 — 확인 질문 원문, 지원자 선정 근거의
구조(관련 기록·이전 지원·급한 업무 여부), 지원 요청 상태 이력, 후속 관찰 근거, Memory 보정 값 — 를
Agent가 이미 남긴 기록에서 그대로 읽어 화면용 dict로 바꾼다.

- Agent·Tool·Memory 객체를 읽기만 하고 호출·수정하지 않는다 (판단에 관여하지 않음).
- 근거 기록의 설명은 현재 시각(as_of)의 스냅숏에서만 찾는다 → 미래 정보가 화면에 나오지 않는다.
- 사람 점수·순위를 만들지 않는다.
"""


def build_view(run) -> dict:
    snap = run.session.snapshot
    names = run.names
    revs = {r.revision_id: r for r in snap.document_history}
    msgs = {m.message_id: m for m in snap.messages}
    tasks = {t.task_id: t for t in snap.tasks}
    labels = {m.memory_id: m.feedback_label.value for m in run.store.all()}

    def record(source_id):
        if source_id in revs:
            r = revs[source_id]
            return {"id": source_id, "type": "revision", "at": r.edited_at.isoformat(),
                    "who": names.get(r.author_id, r.author_id), "title": r.document_title, "text": r.change_summary}
        if source_id in msgs:
            m = msgs[source_id]
            return {"id": source_id, "type": "message", "at": m.sent_at.isoformat(),
                    "who": names.get(m.sender_id, m.sender_id), "title": m.channel, "text": m.text}
        if source_id in tasks:
            t = tasks[source_id]
            return {"id": source_id, "type": "task", "at": None, "who": None, "title": t.title,
                    "text": f"업무 상태 {t.status.value}"}
        return {"id": source_id, "type": "other", "at": None, "who": None, "title": None, "text": None}

    def check_view(c):
        if c is None:
            return None
        return {"at": c.observed_at.isoformat(), "is_candidate": c.is_candidate, "base_is_candidate": c.base_is_candidate,
                "idle_hours": c.effective_idle_hours, "raw_idle_hours": c.raw_idle_hours,
                "team_pause_hours": c.team_pause_overlap_hours, "limit_hours": c.effective_idle_limit_hours,
                "base_limit_hours": c.base_idle_limit_hours, "memory_adjustment_hours": c.memory_adjustment_hours,
                "explanation": c.adjustment_explanation, "reasons": list(c.reasons),
                "applied_memories": [{"id": i, "label": labels.get(i)} for i in c.applied_memory_ids]}

    episodes = []
    for ep in run.agent.episodes:
        support = None
        a = ep.support_analysis
        if a is not None:
            chosen = next((c for c in a.candidates if c.member_id == a.selected_member_id), None)
            support = {
                "block_kind": a.block_kind, "reason": a.reason,
                "supporter": names.get(a.selected_member_id) if a.selected_member_id else None,
                "best_record": record(chosen.best_related_source_id) if chosen and chosen.best_related_source_id else None,
                "related_records": [record(s) for s in chosen.related_source_ids[:4]] if chosen else [],
                "prior_help": [record(s) for s in chosen.prior_help_source_ids] if chosen else [],
                "no_urgent_task": bool(chosen) and not chosen.urgent_task_ids,
                "others": [names.get(c.member_id) for c in a.candidates if c.eligible and c.member_id != a.selected_member_id],
            }
        action = ep.intervention
        episodes.append({
            "run_id": ep.run_id, "task_id": ep.task_id, "title": ep.title,
            "assignee": names.get(ep.assignee_id, ep.assignee_id), "state": ep.state.value,
            "started_at": ep.started_at.isoformat(),
            "check": check_view(ep.checks[0] if ep.checks else None),
            "questions": [{"action_id": r.action_id, "at": r.sent_at.isoformat(), "text": r.question,
                           "status": r.status.value} for r in ep.check_ins.values()],
            "confirmed_at": ep.confirmed_at.isoformat() if ep.confirmed_at else None,
            "support": support,
            "action": None if action is None else {
                "action_id": action.action_id, "recipient": names.get(action.recipient_id), "message": action.message,
                "history": [{"status": h.status.value, "at": h.changed_at.isoformat(),
                             "by": names.get(h.changed_by) if h.changed_by else None} for h in action.status_history]},
            "support_sent_at": ep.support_sent_at.isoformat() if ep.support_sent_at else None,
            "follow_ups": [{"at": f.at.isoformat(), "resolved": f.resolved, "note": f.note,
                            "records": [record(s) for s in f.resolution_source_ids]} for f in ep.follow_ups],
        })

    adjustments = []
    for p in run.agent.policy_applications():
        c = p.check
        if c.applied_memory_ids or (c.team_pause_overlap_hours or 0) > 0:
            adjustments.append({"task_id": p.task_id, "title": tasks[p.task_id].title if p.task_id in tasks else p.task_id,
                                **check_view(c)})
    counts = {}
    for label in labels.values():
        counts[label] = counts.get(label, 0) + 1
    return {"episodes": episodes, "memory": {"counts": counts, "adjustments": adjustments}}
