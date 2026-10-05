"""Claim Agent 접근 경계: Agent는 생성자로 받은 Agent-facing Tool만 쓴다."""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import contrilog

PKG = Path(contrilog.__file__).parent
AGENT_DIR = PKG / "agent"
PROJECT_ROOT = PKG.parent

FORBIDDEN_MODULE_PREFIXES = (
    "contrilog.data_access", "contrilog.simulation", "contrilog.evaluation", "contrilog.schemas.ground_truth",
    "contrilog.tools.session", "os", "pathlib", "io", "shutil", "glob", "importlib", "builtins", "subprocess",
    "pickle", "sqlite3", "json",
)
FORBIDDEN_CALLS = {"open", "eval", "exec", "compile", "__import__", "getattr", "setattr", "delattr", "vars",
                   "globals", "locals", "input"}
FORBIDDEN_ATTRS = {"snapshot", "human", "advance_to", "call_log", "export_call_log", "_session", "__dict__"}


def _files():
    return [f for f in AGENT_DIR.rglob("*.py")]


def _imports(tree, file):
    pkg_parts = ["contrilog", *file.relative_to(PKG).parent.parts]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg_parts[: len(pkg_parts) - node.level + 1]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            yield mod
            yield from (f"{mod}.{a.name}" for a in node.names)


def test_agent_package_exists_and_is_scanned():
    names = {f.relative_to(AGENT_DIR).as_posix() for f in _files()}
    assert {"claim_verification/agent.py", "claim_verification/decomposer.py", "claim_verification/planner.py",
            "claim_verification/evaluator.py", "claim_verification/judge.py"} <= names


def test_agent_does_not_import_data_simulation_evaluation_or_io():
    for f in _files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for mod in _imports(tree, f):
            bad = [p for p in FORBIDDEN_MODULE_PREFIXES if mod == p or mod.startswith(p + ".")]
            assert not bad, f"{f.relative_to(PROJECT_ROOT)} imports {mod}"


def test_agent_does_not_use_dynamic_or_file_access_calls():
    for f in _files():
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in FORBIDDEN_CALLS, f"{f.name}: {node.func.id}()"


def test_agent_does_not_touch_session_internals():
    for f in _files():
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_ATTRS, f"{f.name}: .{node.attr}"
                if node.attr.startswith("_") and not node.attr.startswith("__"):
                    owner = node.value
                    assert isinstance(owner, ast.Name) and owner.id == "self", f"{f.name}: private .{node.attr}"


def _docstrings(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def test_agent_has_no_hardcoded_cases_claims_records_or_people():
    """로직에 쓰이는 문자열 상수에 Case/Claim/기록/사람 식별자가 없어야 한다 (설명용 docstring 제외)."""
    import re

    pattern = re.compile(r"CASE\d|Case\s?\d|CLM-\d|GTC|GTS|UT-MT\d|REV-\d|MSG-\d|\bT\d{2}\b|\bM_[A-Z]\b|"
                         r"P001|DOC-|윤서진|한도윤|박지후|이하은|서진|도윤|지후|하은")
    for f in _files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                assert not pattern.search(node.value), f"{f.name}: {node.value[:60]!r}"


SCRIPT = r"""
import json, sys
from datetime import datetime, timedelta, timezone
from contrilog.tools import ToolSession
K = timezone(timedelta(hours=9))
session = ToolSession("P001", datetime(2026, 10, 16, tzinfo=K))
before = set(sys.modules)
opened = []
recording = [True]
sys.addaudithook(lambda ev, args: opened.append(str(args[0])) if recording[0] and ev == "open" and isinstance(args[0], str) else None)
from contrilog.agent.claim_verification import ClaimVerificationAgent
agent = ClaimVerificationAgent(tools=session.tools)
for cid in ["CLM-01", "CLM-02", "CLM-03", "CLM-04", "CLM-05", "CLM-06", "CLM-07", "CLM-08", "CLM-09"]:
    agent.verify_claim(claim_id=cid)
recording[0] = False
new_modules = sorted(set(sys.modules) - before)
print(json.dumps({"opened": [p for p in opened if not p.endswith((".py", ".pyc")) and "__pycache__" not in p],
                  "new_modules": new_modules,
                  "tools": sorted({c.tool_name for c in session.call_log})}))
"""


def test_agent_run_opens_no_files_and_loads_no_forbidden_modules():
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=PROJECT_ROOT, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    data_files = [p for p in out["opened"] if "/data/" in p or p.endswith(".json")]
    assert data_files == [], data_files  # 입력·시뮬레이션·Ground Truth 파일을 직접 열지 않는다
    assert not [m for m in out["new_modules"] if m.startswith(("contrilog.evaluation", "contrilog.schemas.ground_truth",
                                                               "contrilog.simulation"))]
    assert "CheckInTool" not in out["tools"] and "SupportRequestTool" not in out["tools"]
