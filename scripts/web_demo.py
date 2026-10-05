"""ContriLog 웹 시연 화면 (Python 내장 웹서버, 추가 패키지 없음).

사용법:
  python scripts/web_demo.py                 # http://127.0.0.1:8790
  python scripts/web_demo.py --port 9000 --host 0.0.0.0

화면: 요약 카드 · 지금 확인이 필요한 업무 · 대화형 확인 · 지원 제안 · PM 승인 · 진행 단계 · AI 판단 보정 · 팀 업무 표.
API:  GET /api/state · GET /api/scenarios · POST /api/start {scenario, interpreter}
      POST /api/advance {mode: "event"|"wake"} · POST /api/decide {action_id, approve}
      상태 응답에는 화면용 ViewModel(view, contrilog/webui/view.py)이 함께 담긴다.
"""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from contrilog.webui import SCENARIOS, DemoRun
from contrilog.webui.view import build_view

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "frontend" / "index.html"


def payload(run) -> dict:
    """DemoRun.state()에 화면용 ViewModel(읽기 전용)을 덧붙인다."""
    data = run.state()
    data["view"] = build_view(run)
    return data


class App:
    def __init__(self, provider: str):
        self.lock = threading.Lock()
        self.provider = provider
        self.llm = None
        self.run = None

    def start(self, scenario: str, interpreter: str) -> DemoRun:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario}")
        if interpreter == "llm" and self.llm is None:
            from contrilog.llm import LLMReplyInterpreter

            self.llm = LLMReplyInterpreter(provider=self.provider)
        self.run = DemoRun(scenario, interpreter, llm=self.llm if interpreter == "llm" else None)
        return self.run


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 조용히
            pass

        def _json(self, payload, status=200):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = INDEX.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/scenarios":
                self._json([{"key": k, "title": v["title"], "project": v["project"]} for k, v in SCENARIOS.items()])
            elif self.path == "/api/state":
                with app.lock:
                    self._json(payload(app.run) if app.run else {"empty": True})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            try:
                data = self._body()
                with app.lock:
                    if self.path == "/api/start":
                        run = app.start(data.get("scenario", "webhook"), data.get("interpreter", "llm"))
                    elif self.path == "/api/advance":
                        run = app.run
                        if run is None:
                            raise ValueError("start first")
                        if data.get("mode") == "wake":
                            run.advance(1)
                        else:
                            run.advance_to_next_event(task_only=data.get("task_only", True))
                    elif self.path == "/api/decide":
                        run = app.run
                        if run is None or data.get("action_id") not in {a.action_id for a in run.pending()}:
                            raise ValueError("no such pending proposal")
                        run.decide(data["action_id"], bool(data.get("approve")))
                    else:
                        return self._json({"error": "not found"}, 404)
                    self._json(payload(run))
            except Exception as e:  # noqa: BLE001 — 화면에 오류를 보여 준다
                self._json({"error": f"{type(e).__name__}: {e}"}, 400)

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--provider", choices=["ollama", "anthropic"], default="ollama")
    args = ap.parse_args(argv)
    app = App(args.provider)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"ContriLog 웹 시연: http://{args.host}:{args.port}  (종료: Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
