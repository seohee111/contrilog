import json
from pathlib import Path

from pydantic import TypeAdapter

from contrilog.data_access.paths import DATA_ROOT
from contrilog.schemas import ProjectInput, SimulatedHumanDecision, SimulatedReply

SIMULATION_DIRNAME = "simulation"
REPLIES_FILE = "simulated_replies.json"
HUMAN_DECISIONS_FILE = "human_decisions.json"

_adapter = TypeAdapter(list[SimulatedReply])
_decision_adapter = TypeAdapter(list[SimulatedHumanDecision])


def simulation_dir(project_id: str, data_root: Path | None = None) -> Path:
    return (data_root or DATA_ROOT) / SIMULATION_DIRNAME / project_id


def load_simulated_replies(project_id: str, data_root: Path | None = None) -> list[SimulatedReply]:
    with open(simulation_dir(project_id, data_root) / REPLIES_FILE, encoding="utf-8") as f:
        return _adapter.validate_python(json.load(f))


def load_human_decisions(project_id: str, data_root: Path | None = None) -> list[SimulatedHumanDecision]:
    path = simulation_dir(project_id, data_root) / HUMAN_DECISIONS_FILE
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return _decision_adapter.validate_python(json.load(f))


def check_human_decision_integrity(decisions: list[SimulatedHumanDecision], data: ProjectInput) -> list[str]:
    errors = []
    members = {m.member_id for m in data.members}
    tasks = {t.task_id: t for t in data.tasks}
    for d in decisions:
        if d.project_id != data.project.project_id:
            errors.append(f"{d.decision_id}: wrong project")
        for mid in (d.approver_id, d.about_member_id):
            if mid not in members:
                errors.append(f"{d.decision_id}: unknown member {mid}")
        if d.task_id not in tasks:
            errors.append(f"{d.decision_id}: unknown task {d.task_id}")
        elif d.about_member_id not in tasks[d.task_id].assignee_ids:
            errors.append(f"{d.decision_id}: {d.about_member_id} is not assigned to {d.task_id}")
    return errors


def check_simulation_integrity(replies: list[SimulatedReply], data: ProjectInput) -> list[str]:
    errors = []
    members = {m.member_id for m in data.members}
    tasks = {t.task_id: t for t in data.tasks}
    seen = set()
    for r in replies:
        if r.reply_id in seen:
            errors.append(f"duplicate reply id {r.reply_id}")
        seen.add(r.reply_id)
        if r.project_id != data.project.project_id:
            errors.append(f"{r.reply_id}: wrong project")
        for mid in (r.responder_id, r.about_member_id):
            if mid not in members:
                errors.append(f"{r.reply_id}: unknown member {mid}")
        task = tasks.get(r.task_id)
        if task is None:
            errors.append(f"{r.reply_id}: unknown task {r.task_id}")
        elif r.about_member_id not in task.assignee_ids:
            errors.append(f"{r.reply_id}: {r.about_member_id} is not assigned to {r.task_id}")
    # 같은 조건(trigger·응답자·대상·Task·의도)에서 시간 창이 겹치면 어떤 응답이 선택될지 모호하다
    for i, a in enumerate(replies):
        for b in replies[i + 1:]:
            same = (a.trigger, a.responder_id, a.about_member_id, a.task_id, a.question_intent) == \
                   (b.trigger, b.responder_id, b.about_member_id, b.task_id, b.question_intent)
            if same and a.available_from < b.available_until and b.available_from < a.available_until:
                errors.append(f"{a.reply_id}/{b.reply_id}: overlapping windows for the same question")
    return errors
