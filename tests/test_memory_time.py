"""미래 Memory 누출 방지, 결정성, Ground Truth 미사용."""

import json
import os
import subprocess
import sys
from pathlib import Path

import contrilog
from contrilog.agent.stagnation import FeedbackSettings, StagnationAgent
from contrilog.evaluation.memory_evaluation import run_mode
from contrilog.evaluation.stagnation_evaluation import run_monitoring
from contrilog.memory import InMemoryMemoryStore
from contrilog.schemas import AgentMemory, DecisionOutcome, DecisionType, FeedbackLabel, MemoryContext
from tests.stagnation_fixtures import kst, unit_runs

PROJECT_ROOT = Path(contrilog.__file__).parent.parent


def _all_checks(agent):
    return [c for r in agent.runs() for c in r.candidate_checks] + [p.check for p in agent.policy_applications()]


def test_every_applied_memory_was_created_before_the_decision():
    _, agent, store = run_mode("ON")
    created = {m.memory_id: m.created_at for m in store.all()}
    pairs = [(c.observed_at, mid) for c in _all_checks(agent) for mid in c.applied_memory_ids]
    assert pairs and all(created[mid] < at for at, mid in pairs)


def test_case04_outcome_is_not_used_at_or_before_its_time():
    _, agent, store = run_mode("ON")
    m04 = next(m for m in store.all() if "T04" in m.evidence_ids)
    c03 = unit_runs(agent.runs(), "T03", "M_C")[0].candidate_checks[0]
    assert c03.observed_at < m04.created_at and m04.memory_id not in c03.applied_memory_ids
    first_use = min(c.observed_at for c in _all_checks(agent) if m04.memory_id in c.applied_memory_ids)
    assert first_use > m04.created_at


def test_preloaded_future_memory_is_ignored_until_its_created_at():
    ctx = MemoryContext(kind="CANDIDATE", deadline_bucket="DUE_96_168H", idle_ratio_bucket="0_5_TO_1",
                        task_status="IN_PROGRESS", team_context="TEAM_ACTIVE")
    future = AgentMemory(
        memory_id="MEM-001", project_id="P001", created_at=kst(10, 1), source_decision_ids=["DEC-00001"],
        decision_type=DecisionType.STAGNATION_ASSESSMENT, signal_pattern="x", agent_judgment="x",
        observed_outcome=DecisionOutcome.FALSE_POSITIVE, lesson="x", feedback_label=FeedbackLabel.FALSE_POSITIVE,
        context=ctx, observed_signal="REPORTS_ON_TRACK")
    store = InMemoryMemoryStore([future])
    _, agent, _ = run_monitoring(agent_factory=lambda tools: StagnationAgent(
        tools=tools, feedback=FeedbackSettings(store=store)))
    for c in _all_checks(agent):
        if "MEM-001" in c.applied_memory_ids:
            assert c.observed_at > kst(10, 1)
    # Case03·04(9/19)는 이 Memory의 영향을 받지 않는다
    assert unit_runs(agent.runs(), "T03", "M_C")[0].candidate_checks[0].applied_memory_ids == []


def test_replay_is_deterministic():
    def dump():
        _, agent, store = run_mode("ON")
        return (json.dumps([m.model_dump(mode="json") for m in store.all()], ensure_ascii=False),
                json.dumps([p.model_dump(mode="json") for p in agent.policy_applications()], ensure_ascii=False),
                json.dumps([r.model_dump(mode="json") for r in agent.runs()], ensure_ascii=False))
    assert dump() == dump()


SCRIPT = r"""
import json, sys, traceback, os.path, tempfile
from datetime import datetime, timedelta, timezone
from contrilog.tools import ToolSession
from contrilog.agent.stagnation import StagnationAgent, FeedbackSettings
from contrilog.memory import JsonlMemoryStore
from contrilog.runtime import run_stagnation_monitoring
from contrilog.simulation.human import HumanDecisionSimulator
K = timezone(timedelta(hours=9))
path = os.path.join(tempfile.mkdtemp(), "agent_memory.jsonl")
session = ToolSession("P001", datetime(2026, 9, 1, 9, tzinfo=K))
agent = StagnationAgent(tools=session.tools, feedback=FeedbackSettings(store=JsonlMemoryStore(path)))
human = HumanDecisionSimulator("P001")
before = set(sys.modules)
events = []
def hook(ev, args):
    if ev != "open" or not isinstance(args[0], str) or not args[0].endswith((".json", ".jsonl")):
        return
    opener = None
    for fr in reversed(traceback.extract_stack()):
        fn = os.path.abspath(fr.filename)
        if "/contrilog/contrilog/" in fn:
            opener = fn.split("/contrilog/contrilog/")[1]
            break
    events.append([os.path.basename(args[0]), opener])
sys.addaudithook(hook)
run_stagnation_monitoring(session, agent, datetime(2026, 10, 16, 21, tzinfo=K), human)
print(json.dumps({"events": events, "new_modules": sorted(set(sys.modules) - before),
                  "lines": len(agent.feedback.store.all())}))
"""


def test_memory_run_never_touches_ground_truth_and_only_memory_writes_memory():
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=PROJECT_ROOT, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["lines"] > 0
    for name, opener in out["events"]:
        if name == "agent_memory.jsonl":
            assert opener == "memory/store.py"
        else:
            assert name in ("simulated_replies.json", "human_decisions.json") and opener.startswith("simulation/")
    assert not [m for m in out["new_modules"] if m.startswith(("contrilog.evaluation", "contrilog.schemas.ground_truth"))]


def test_memory_package_does_not_import_ground_truth_or_environment():
    import ast

    for f in (Path(contrilog.__file__).parent / "memory").glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(("contrilog.evaluation", "contrilog.schemas.ground_truth",
                                                   "contrilog.simulation", "contrilog.data_access", "contrilog.tools"))
