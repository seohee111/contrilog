"""Tool 실행 경로의 Ground Truth 격리 + 시뮬레이션 응답 지연 로딩."""

import json
import os
import subprocess
import sys
from pathlib import Path

import contrilog
from contrilog.data_access.paths import DATA_ROOT

PKG = Path(contrilog.__file__).parent
PROJECT_ROOT = PKG.parent

SCRIPT = r"""
import json, sys
opened = []
def hook(ev, args):
    if ev == "open" and isinstance(args[0], str) and args[0].endswith(".json"):
        opened.append(args[0])
sys.addaudithook(hook)
from datetime import datetime, timedelta, timezone
from contrilog.tools import ToolSession
K = timezone(timedelta(hours=9))
s = ToolSession("P001", datetime(2026, 10, 8, 10, tzinfo=K))
t = s.tools
t["ProjectStatusTool"].get_status()
t["MeetingSearchTool"].search(query="Evidence")
t["DocumentHistoryTool"].search(query="기간 필터")
t["MessageSearchTool"].search()
t["ClaimTool"].list_claims()
t["InboxTool"].list_replies()
s.advance_to(datetime(2026, 10, 16, tzinfo=K))
t["ClaimTool"].register_atomic_claim(parent_claim_id="CLM-06", claimed_type="IDEA", text="x")
before_action = list(opened)
s2 = ToolSession("P001", datetime(2026, 10, 9, 10, tzinfo=K))
s2.tools["CheckInTool"].send(task_id="T11", member_id="M_C", question="?")
aid = s2.tools["SupportRequestTool"].propose(task_id="T11", about_member_id="M_C", supporter_id="M_B", message="?").actions[0].action_id
s2.human.approve(aid, "M_A")
s2.tools["SupportRequestTool"].send(action_id=aid)
s2.advance_to(datetime(2026, 10, 9, 12, tzinfo=K))
s2.tools["InboxTool"].list_replies()
bad = [m for m in sys.modules if m.startswith(("contrilog.evaluation", "contrilog.schemas.ground_truth"))]
print(json.dumps({"before_action": before_action, "all": opened, "modules": bad}))
"""


def _run():
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=PROJECT_ROOT, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)})
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_full_tool_run_never_opens_ground_truth_or_loads_evaluation():
    out = _run()
    gt = (DATA_ROOT / "ground_truth").resolve()
    for p in out["all"]:
        assert not Path(p).resolve().is_relative_to(gt), p
    assert out["modules"] == []


def test_observation_tools_never_open_simulation_file():
    out = _run()
    sim = (DATA_ROOT / "simulation").resolve()
    assert out["before_action"], "input files should have been read"
    assert not [p for p in out["before_action"] if Path(p).resolve().is_relative_to(sim)]
    # 행동한 뒤에는 열린다
    assert [p for p in out["all"] if Path(p).resolve().is_relative_to(sim)]


def test_new_modules_are_covered_by_static_isolation_scan():
    from tests.test_isolation import _agent_side_files

    scanned = {p.relative_to(PKG).as_posix() for p in _agent_side_files()}
    for rel in ["data_access/snapshot.py", "simulation/responder.py", "tools/session.py", "tools/actions.py",
                "tools/search.py", "tools/claims.py", "tools/project_status.py", "tools/base.py",
                "tools/results.py", "tools/text_match.py", "schemas/snapshot.py", "schemas/tooling.py"]:
        assert rel in scanned, rel


def test_tool_session_exposes_no_simulation_or_full_input_attributes():
    from tests.timeline_helpers import kst
    from contrilog.tools import ToolSession

    s = ToolSession("P001", kst(9, 18, 10))
    public = [n for n in dir(s) if not n.startswith("_")]
    assert sorted(public) == ["advance_to", "as_of", "call_log", "export_call_log", "human", "project_id",
                              "snapshot", "tools"]
