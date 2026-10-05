"""웹 시연 실행기: 사람 승인 대기, 승인·거절 반영, 화면 상태, HTTP API, 정답 비의존 (규칙 해석기로 결정적 실행)."""

import ast
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import contrilog
from contrilog.webui import DemoRun


def run_until_pending(run):
    while not run.finished and not run.pending():
        if run.advance_to_next_event() == 0:
            break
    return run


@pytest.fixture
def pending_run():
    return run_until_pending(DemoRun("webhook", interpreter="rule"))


def test_time_stops_while_waiting_for_pm(pending_run):
    assert len(pending_run.pending()) == 1
    at = pending_run.session.as_of
    assert pending_run.advance(5) == 0 and pending_run.advance_to_next_event() == 0
    assert pending_run.session.as_of == at
    focus = [e for e in pending_run.state()["events"] if e["task_id"] == "T08"]
    assert focus[-1]["label"] == "지원 제안" and not any(e["kind"] == "ACTION" for e in focus)


def test_approve_sends_and_reaches_resolved(pending_run):
    action = pending_run.pending()[0]
    pending_run.decide(action.action_id, approve=True)
    labels = [e["label"] for e in pending_run.state()["events"] if e["task_id"] == "T08"]
    assert labels[-2:] == ["사람 결정", "전송"]
    while not pending_run.finished:
        pending_run.advance_to_next_event()
    s = pending_run.state()
    assert next(t for t in s["tasks"] if t["focus"])["agent_state"] == "RESOLVED"
    assert s["decisions"][0]["approve"] is True and s["memories"]


def test_reject_never_sends(pending_run):
    action = pending_run.pending()[0]
    pending_run.decide(action.action_id, approve=False)
    while not pending_run.finished:
        pending_run.advance_to_next_event()
    run = next(r for r in pending_run.agent.runs() if r.intervention and r.intervention.action_id == action.action_id)
    assert [h.status.value for h in run.intervention.status_history] == ["PROPOSED", "REJECTED"]
    assert not run.support_interactions


def test_state_shows_reply_text_and_supporter(pending_run):
    s = pending_run.state()
    reply = next(e for e in s["events"] if e["task_id"] == "T08" and e["kind"] == "REPLY")
    assert "401" in reply["reply_text"]
    p = s["pending"][0]
    assert p["supporter"] == s["members"]["M_E"] and p["evidence"]
    json.dumps(s, ensure_ascii=False)  # 화면으로 보낼 수 있는 값만


def test_webui_does_not_touch_ground_truth():
    for f in (Path(contrilog.__file__).parent / "webui").glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                assert not any(n.startswith(("contrilog.evaluation", "contrilog.schemas.ground_truth")) for n in names), f


def test_http_api_rejects_unknown_decision():
    import importlib.util

    spec = importlib.util.spec_from_file_location("web_demo", Path(contrilog.__file__).parents[1] / "scripts" / "web_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    server = ThreadingHTTPServer(("127.0.0.1", 0), mod.make_handler(mod.App("ollama")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST")
        try:
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    try:
        assert post("/api/start", {"scenario": "webhook", "interpreter": "rule"})["scenario"]["focus_task"] == "T08"
        assert "error" in post("/api/decide", {"action_id": "ACT-999", "approve": True})
        assert "<!doctype html>" in urllib.request.urlopen(base + "/", timeout=10).read().decode().lower()
    finally:
        server.shutdown()
