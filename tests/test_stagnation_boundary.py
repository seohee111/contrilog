"""Stagnation Agent 경계: Agent-facing Tool만, 승인·시간 이동 불가, 파일·Ground Truth·DM 미접근."""

import json
import os
import subprocess
import sys
from pathlib import Path

import contrilog
from contrilog.agent.stagnation import TOOL_OPERATIONS
from contrilog.data_access import load_project_input
from tests.stagnation_fixtures import monitor

PKG = Path(contrilog.__file__).parent
PROJECT_ROOT = PKG.parent


def test_allowed_operations_exclude_approval_and_time():
    assert set(TOOL_OPERATIONS) == {
        ("ProjectStatusTool", "get_status"), ("DocumentHistoryTool", "search"), ("MessageSearchTool", "search"),
        ("MeetingSearchTool", "search"), ("CheckInTool", "send"), ("InboxTool", "list_replies"),
        ("SupportRequestTool", "propose"), ("SupportRequestTool", "send"), ("SupportRequestTool", "list_requests")}


def test_static_boundary_scans_cover_stagnation_package():
    from tests.test_claim_agent_boundary import _files

    names = {f.relative_to(PKG / "agent").as_posix() for f in _files()}
    assert {"stagnation/agent.py", "stagnation/policy.py", "stagnation/support.py", "stagnation/interpreter.py",
            "stagnation/resolution.py", "stagnation/thresholds.py"} <= names


SCRIPT = r"""
import json, sys, traceback, os.path
from datetime import datetime, timedelta, timezone
from contrilog.tools import ToolSession
from contrilog.agent.stagnation import StagnationAgent
from contrilog.runtime import run_stagnation_monitoring
from contrilog.simulation.human import HumanDecisionSimulator
K = timezone(timedelta(hours=9))
session = ToolSession("P001", datetime(2026, 9, 1, 9, tzinfo=K))
agent = StagnationAgent(tools=session.tools)
human = HumanDecisionSimulator("P001")
before = set(sys.modules)
events = []
def hook(ev, args):
    if ev != "open" or not isinstance(args[0], str) or not args[0].endswith(".json"):
        return
    opener = None
    for fr in reversed(traceback.extract_stack()):
        fn = os.path.abspath(fr.filename)
        if "/contrilog/contrilog/" in fn:
            opener = fn.split("/contrilog/contrilog/")[1]
            break
    events.append([args[0], opener])
sys.addaudithook(hook)
run_stagnation_monitoring(session, agent, datetime(2026, 10, 16, 21, tzinfo=K), human)
print(json.dumps({"events": events, "new_modules": sorted(set(sys.modules) - before),
                  "final": [r.final_state.value for r in agent.runs() if r.task_id == "T11"]}))
"""


def test_runtime_file_access_and_modules():
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=PROJECT_ROOT, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["final"] == ["RESOLVED"]
    files = sorted(Path(p).name for p, _ in out["events"])
    assert files == ["human_decisions.json", "simulated_replies.json"]  # 환경이 행동을 처리할 때 한 번씩
    for path, opener in out["events"]:
        assert "/ground_truth/" not in path and opener.startswith("simulation/"), (path, opener)
    assert not [m for m in out["new_modules"] if m.startswith(("contrilog.evaluation", "contrilog.schemas.ground_truth"))]


def test_no_private_dm_in_runs_or_tool_trace():
    full = load_project_input("P001")
    dms = {m.message_id: m.text for m in full.messages if m.channel_type.value == "DIRECT_MESSAGE"}
    session, _, _, runs = monitor()
    text = json.dumps([r.model_dump(mode="json") for r in runs], ensure_ascii=False)
    for dm_id, dm_text in dms.items():
        assert f'"{dm_id}"' not in text and dm_text not in text
    for c in session.call_log:
        assert not set(c.returned_source_ids) & set(dms)


def test_agent_cannot_approve_or_move_time():
    session, agent, _, _ = monitor(until=None)
    assert not hasattr(agent, "human") and not hasattr(agent, "advance_to")
    assert set(agent.tools) == set(session.tools)
