"""LLM 응답 해석기: 구조화 출력, 규칙 대체, 캐시, Agent 주입 경계 (실제 API를 부르지 않는 가짜 클라이언트로 검사)."""

import json
from types import SimpleNamespace

import pytest

from contrilog.agent.stagnation import StagnationAgent
from contrilog.evaluation.stagnation_evaluation import run_monitoring
from contrilog.llm import LLMReplyInterpreter
from contrilog.schemas import ReplySemantic


class FakeMessages:
    def __init__(self, answer, stop_reason="end_turn"):
        self.answer, self.stop_reason, self.requests = answer, stop_reason, []

    def create(self, **params):
        self.requests.append(params)
        if isinstance(self.answer, Exception):
            raise self.answer
        payload = self.answer(params) if callable(self.answer) else self.answer
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=json.dumps(payload, ensure_ascii=False))])


def fake_client(answer, stop_reason="end_turn"):
    messages = FakeMessages(answer, stop_reason)
    return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages)), messages


BLOCKED = {"semantic": "REPORTS_BLOCKED", "block_kind": "EXTERNAL_DEPENDENCY", "evidence_phrase": "결재가 안 나서",
           "reason": "외부 결재 대기"}


def test_structured_status_reading(tmp_path):
    client, calls = fake_client(BLOCKED)
    llm = LLMReplyInterpreter(provider="anthropic", client=client, cache_path=tmp_path / "c.jsonl")
    assert llm.status("결재가 안 나서 못 하고 있어요") == (ReplySemantic.REPORTS_BLOCKED, "EXTERNAL_DEPENDENCY")
    req = calls.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["output_config"]["format"]["type"] == "json_schema"
    assert req["output_config"]["effort"] == "low" and req["fallbacks"] == "default"
    assert llm.trace()[0]["source"] == "llm" and llm.trace()[0]["reason"] == "외부 결재 대기"


def test_block_kind_only_for_blocked(tmp_path):
    client, _ = fake_client({"semantic": "REPORTS_ON_TRACK", "block_kind": "INTERNAL_ISSUE",
                             "evidence_phrase": "x", "reason": "y"})
    llm = LLMReplyInterpreter(provider="anthropic", client=client, cache_path=None)
    assert llm.status("진행 중") == (ReplySemantic.REPORTS_ON_TRACK, None)


@pytest.mark.parametrize("failure", [RuntimeError("network"), "refusal", "bad_json"])
def test_failures_fall_back_to_rule(tmp_path, failure):
    if failure == "refusal":
        client, _ = fake_client(BLOCKED, stop_reason="refusal")
    elif failure == "bad_json":
        client, _ = fake_client({"semantic": "MAYBE"})
    else:
        client, _ = fake_client(failure)
    llm = LLMReplyInterpreter(provider="anthropic", client=client, cache_path=tmp_path / "c.jsonl")
    # 규칙 해석기와 같은 결과 ('막혀' → 막힘)
    assert llm.status("원인을 못 찾아서 막혀 있어요")[0] == ReplySemantic.REPORTS_BLOCKED
    assert llm.trace()[0]["source"] == "rule_fallback" and llm.trace()[0]["error"]
    assert not (tmp_path / "c.jsonl").exists()  # 실패한 결과는 캐시하지 않는다


def test_cache_is_reused(tmp_path):
    client, calls = fake_client({"semantic": "ACCEPTS_SUPPORT", "evidence_phrase": "같이 볼게요", "reason": "수락"})
    path = tmp_path / "c.jsonl"
    assert LLMReplyInterpreter(provider="anthropic", client=client, cache_path=path).support("네 같이 볼게요") == ReplySemantic.ACCEPTS_SUPPORT
    again = LLMReplyInterpreter(provider="anthropic", client=None, cache_path=path)  # 새 인스턴스, 클라이언트 없음
    assert again.support("네 같이 볼게요") == ReplySemantic.ACCEPTS_SUPPORT
    assert len(calls.requests) == 1 and again.trace()[0]["source"] == "cache"


def test_prompt_examples_do_not_reuse_evaluation_replies():
    from contrilog.llm.reply_interpreter import STATUS_SYSTEM, SUPPORT_SYSTEM
    from contrilog.simulation.loader import load_simulated_replies

    for pid in ("P001", "P002"):
        for r in load_simulated_replies(pid):
            assert r.reply_text[:20] not in STATUS_SYSTEM + SUPPORT_SYSTEM


def test_llm_never_bypasses_human_approval(tmp_path):
    """LLM이 모든 응답을 '막힘'으로 읽어도, 지원 요청은 사람의 승인 없이 전송되지 않는다."""
    client, _ = fake_client(lambda p: BLOCKED | {"block_kind": "INTERNAL_ISSUE"} if "막혀서" in p["system"]
                            else {"semantic": "ACCEPTS_SUPPORT", "evidence_phrase": "", "reason": ""})
    llm = LLMReplyInterpreter(provider="anthropic", client=client, cache_path=None)
    _, agent, _ = run_monitoring(project_id="P002", use_human=False, agent_factory=lambda tools: StagnationAgent(
        tools=tools, status_interpreter=llm.status, support_interpreter=llm.support))
    proposals = [r.intervention for r in agent.runs() if r.intervention is not None]
    assert proposals and all(a.status.value == "PROPOSED" for a in proposals)


def test_ollama_backend_uses_json_schema_and_local_url(tmp_path):
    sent = []

    def post(url, payload):
        sent.append((url, payload))
        return {"message": {"content": json.dumps(BLOCKED, ensure_ascii=False)}}

    llm = LLMReplyInterpreter(client=post, cache_path=tmp_path / "c.jsonl")
    assert llm.provider == "ollama" and llm.model == "qwen3:32b"
    assert llm.status("결재 대기 중") == (ReplySemantic.REPORTS_BLOCKED, "EXTERNAL_DEPENDENCY")
    url, payload = sent[0]
    assert url.startswith("http://localhost:11434")  # 로컬 서버로만 보낸다
    assert payload["format"]["properties"]["semantic"]["enum"] and payload["options"]["temperature"] == 0


def test_ollama_server_down_falls_back_to_rule(tmp_path):
    def post(url, payload):
        raise ConnectionRefusedError("ollama not running")

    llm = LLMReplyInterpreter(client=post, cache_path=tmp_path / "c.jsonl")
    assert llm.support("네, 오늘 같이 볼게요") == ReplySemantic.ACCEPTS_SUPPORT
    assert llm.trace()[0]["source"] == "rule_fallback"
