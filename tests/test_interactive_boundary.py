"""Interactive Verification의 경계: 허용 operation, runtime 계층, 실행 중 파일 접근 출처, Ground Truth 격리."""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import contrilog
from contrilog.agent.claim_verification.agent import TOOL_OPERATIONS
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from tests.interactive_fixtures import SCENARIOS, run_scenario, trace_text

PKG = Path(contrilog.__file__).parent
PROJECT_ROOT = PKG.parent


def test_allowed_tool_operations_are_minimal():
    assert set(TOOL_OPERATIONS) == {
        ("ClaimTool", "list_claims"), ("ClaimTool", "register_atomic_claim"), ("ProjectStatusTool", "get_status"),
        ("MeetingSearchTool", "search"), ("DocumentHistoryTool", "search"), ("MessageSearchTool", "search"),
        ("CheckInTool", "send"), ("InboxTool", "list_replies")}
    assert not [k for k in TOOL_OPERATIONS if k[0] == "SupportRequestTool"]


def _docstring_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def _strings_and_imports(paths):
    """로직의 문자열 상수와 import (설명용 docstring 제외)."""
    for f in paths:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        docs = _docstring_ids(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                yield f, "str", node.value
            elif isinstance(node, ast.ImportFrom):
                yield f, "import", ("." * node.level) + (node.module or "")
            elif isinstance(node, ast.Import):
                for a in node.names:
                    yield f, "import", a.name


def test_agent_and_runtime_do_not_know_ground_truth_or_simulation_internals():
    files = list((PKG / "agent").rglob("*.py")) + list((PKG / "runtime").rglob("*.py"))
    for f, kind, value in _strings_and_imports(files):
        if kind == "str":
            for word in ["expected_interactive", "ground_truth", "simulated_replies", "SIM-", "CHECKIN_REPLY",
                         "SUPPORT_REPLY", "inaccessible"]:
                assert word not in value, f"{f.name}: {value[:60]!r}"
        else:
            for bad in ["evaluation", "ground_truth", "simulation", "data_access"]:
                assert bad not in value, f"{f.name} imports {value}"


SCRIPT = r"""
import json, sys, tempfile, pathlib
sys.path.insert(0, ".")
from tests.claim_fixtures import load_raw, write_data_root, claim
from tests.interactive_fixtures import SCENARIOS
s = SCENARIOS["support_via_dm"]
raw = load_raw(); raw["claims"].append(claim("CLM-50", s.member_id, s.submitted_at, s.text))
root = write_data_root(pathlib.Path(tempfile.mkdtemp()), raw)
from contrilog.tools import ToolSession
from contrilog.agent.claim_verification import ClaimVerificationAgent
from contrilog.runtime import run_interactive_verification
session = ToolSession("P001", s.verify_at, data_root=root)
agent = ClaimVerificationAgent(tools=session.tools)
before = set(sys.modules)
events = []
def hook(ev, args):
    if ev != "open" or not isinstance(args[0], str) or not args[0].endswith(".json"):
        return
    import traceback
    opener = None
    import os.path
    for fr in reversed(traceback.extract_stack()):  # 파일을 연 가장 안쪽의 contrilog 코드
        fn = os.path.abspath(fr.filename)
        if "/contrilog/contrilog/" in fn:
            opener = fn.split("/contrilog/contrilog/")[1]
            break
    events.append([args[0], opener])
sys.addaudithook(hook)
run = run_interactive_verification(session, agent, "CLM-50")
print(json.dumps({"events": events, "new_modules": sorted(set(sys.modules) - before),
                  "status": run.atomic_results[0].predicted_status.value}))
"""


def test_runtime_file_access_comes_only_from_environment_layers():
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=PROJECT_ROOT, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["status"] == "VERIFIED"
    for path, opener in out["events"]:
        assert "/ground_truth/" not in path
        # 응답 파일은 환경(simulation)이 Agent의 CheckIn 행동을 처리할 때만 연다. Agent·runtime은 파일을 열지 않는다.
        assert opener and opener.startswith("simulation/"), (path, opener)
    assert len(out["events"]) == 1  # 확인 질문을 보낸 순간 한 번
    assert not [m for m in out["new_modules"] if m.startswith(("contrilog.evaluation", "contrilog.schemas.ground_truth"))]


def test_trace_contains_no_ground_truth_content(tmp_path):
    gt = load_ground_truth("P001")
    texts = [x.expected_content for c in gt.contributions for x in c.expected_interactive_evidence] + \
            [x.expected_content for s in gt.stagnations for x in s.expected_interactive_evidence] + \
            [c.scenario for c in gt.cases]
    for name in SCENARIOS:
        _, _, run = run_scenario(tmp_path / name, SCENARIOS[name])
        text = trace_text(run)
        for t in texts:
            assert t not in text
        for word in ["GTC-", "GTS-", "GTCL-", "CASE0", "CASE1", "CHECKIN_REPLY", "SUPPORT_REPLY", "SIM-"]:
            assert word not in text, (name, word)
