"""LLM 응답 해석기 — 팀원 응답 문장의 의미를 LLM이 구조화된 값으로 분류한다.

백엔드: 로컬 오픈소스 LLM(Ollama, 기본 Qwen3 32B — 팀 기록이 서버 밖으로 나가지 않음) 또는 Claude API.

정체 Agent의 규칙 해석기(contrilog.agent.stagnation.interpreter)와 같은 함수 형태다.
  status(text)  -> (ReplySemantic, block_kind | None)    # STATUS_CHECK 응답
  support(text) -> ReplySemantic                          # 지원 요청 응답
Agent 생성자에 주입한다: StagnationAgent(tools, status_interpreter=llm.status, support_interpreter=llm.support)

LLM이 맡는 일은 '자연어 응답의 의미 분류' 하나다. 상태 전이, Human Approval, Memory 보정 범위, RESOLVED 조건은
Agent의 결정적 규칙 그대로다. LLM 결과도 정해진 enum 값만 허용한다 (JSON schema 구조화 출력).

안전장치
- API 오류·키 없음·거절·형식 오류 → 규칙 해석기 결과로 대체하고 calls에 사유를 남긴다 (Agent는 멈추지 않는다).
- 같은 (모델, 프롬프트 버전, 종류, 문장)은 캐시 파일에서 재사용한다 (평가 재현성·비용).
- 프롬프트에는 범주 정의만 있고 예시 문장이 없다. 평가 데이터(P001/P002)의 표현·유형을 힌트로 넣지 않는다
  (reply-v1은 평가 데이터의 까다로운 유형을 힌트로 담고 있어 폐기했다).
- 사람에 대한 판단(성실성·능력)은 출력에 없다. 응답 문장이 말하는 '업무 상태'만 분류한다.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ValidationError

from contrilog.agent.stagnation.interpreter import interpret_status_reply, interpret_support_reply
from contrilog.schemas import ReplySemantic

DEFAULT_MODELS = {"ollama": "qwen3:32b", "anthropic": "claude-opus-5-5"}
DEFAULT_PROVIDER = "ollama"  # 로컬 오픈소스 LLM (팀 기록이 외부로 나가지 않음). Claude API 키가 있으면 provider="anthropic"
DEFAULT_MODEL = DEFAULT_MODELS[DEFAULT_PROVIDER]
OLLAMA_URL = "http://localhost:11434/api/chat"
PROMPT_VERSION = "reply-v2"
DEFAULT_CACHE = Path(__file__).resolve().parents[2] / ".cache" / "llm_reply_cache.jsonl"


class StatusReading(BaseModel):
    semantic: Literal["REPORTS_BLOCKED", "REPORTS_ON_TRACK", "CONFIRMS_COMPLETION", "NOT_INFORMATIVE"]
    block_kind: Optional[Literal["INTERNAL_ISSUE", "EXTERNAL_DEPENDENCY"]]
    evidence_phrase: str
    reason: str


class SupportReading(BaseModel):
    semantic: Literal["ACCEPTS_SUPPORT", "DECLINES_SUPPORT", "NOT_INFORMATIVE"]
    evidence_phrase: str
    reason: str


STATUS_SYSTEM = """당신은 회사 프로젝트 팀의 업무 진행 상황 확인을 돕는 분류기입니다.
팀원에게 "이 작업이 계획대로 진행되고 있는지, 막혀서 도움이 필요한지"를 물었고, 그 답장 한 개를 받습니다.
답장이 말하는 '이 작업의 현재 상태'를 아래 넷 중 하나로 분류하세요. 사람의 성실성이나 능력은 판단하지 않습니다.

- REPORTS_BLOCKED: 지금 이 작업을 더 진행할 수 없는 상태다.
- REPORTS_ON_TRACK: 작업이 정상적으로 진행 중이다.
- CONFIRMS_COMPLETION: 작업이 이미 끝났거나, 막혀 있던 문제가 해결되었다.
- NOT_INFORMATIVE: 답장만으로는 작업 상태를 판단할 수 없다.

block_kind (REPORTS_BLOCKED일 때만 값을 넣고, 그 밖에는 null):
- INTERNAL_ISSUE: 팀 안에서 풀 수 있는 문제다. 팀원의 도움이 해결에 도움이 될 수 있다.
- EXTERNAL_DEPENDENCY: 팀 밖(외부 업체, 다른 조직, 승인·결재 절차 등)의 처리를 기다려야만 풀린다.

키워드 하나가 아니라 문장 전체의 뜻으로 판단하세요.
evidence_phrase에는 판단 근거가 된 답장 속 구절을 그대로 옮기고, reason에는 한 문장으로 이유를 쓰세요."""

SUPPORT_SYSTEM = """당신은 회사 프로젝트 팀의 업무 지원 요청을 돕는 분류기입니다.
막힌 동료를 도와줄 수 있는지 한 팀원에게 물었고, 그 답장 한 개를 받습니다. 답장을 아래 셋 중 하나로 분류하세요.

- ACCEPTS_SUPPORT: 답장한 사람 본인이 돕겠다고 한다.
- DECLINES_SUPPORT: 답장한 사람 본인은 돕기 어렵다고 한다.
- NOT_INFORMATIVE: 답장만으로는 도울지 판단할 수 없다.

키워드 하나가 아니라 문장 전체의 뜻으로 판단하세요.
evidence_phrase에는 근거 구절을 그대로, reason에는 한 문장 이유를 쓰세요."""


def _http_post(url: str, payload: dict, timeout: float = 300.0) -> dict:
    import urllib.request

    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _load_dotenv(path: Path = DEFAULT_CACHE.parents[1] / ".env") -> None:
    """프로젝트 루트 .env의 ANTHROPIC_* 값을 환경변수로 읽는다 (이미 설정된 값은 덮어쓰지 않음, 키는 저장소에 넣지 않음)."""
    import os

    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and name.startswith("ANTHROPIC_") and name not in os.environ:
            os.environ[name] = value.strip().strip("'\"")


def _schema(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    schema["additionalProperties"] = False
    schema["required"] = list(schema["properties"])
    return schema


@dataclass
class InterpretationCall:
    kind: str  # STATUS / SUPPORT
    text: str
    semantic: str
    block_kind: Optional[str] = None
    source: str = "llm"  # llm / cache / rule_fallback
    evidence_phrase: str = ""
    reason: str = ""
    error: Optional[str] = None


@dataclass
class LLMReplyInterpreter:
    """provider: "ollama"(로컬, 기본) / "anthropic"(Claude API).
    client: anthropic일 때 anthropic.Anthropic 호환 객체, ollama일 때 post(url, payload) -> dict 호출 가능 객체.
    None이면 처음 호출할 때 만든다 (테스트에서는 가짜 객체를 넣는다)."""

    client: object = None
    provider: str = DEFAULT_PROVIDER
    model: str = None
    effort: str = "low"
    think: bool = False  # ollama: 추론 모델의 사고 단계 사용 여부
    cache_path: Optional[Path] = DEFAULT_CACHE
    use_fallbacks: bool = True
    calls: list = field(default_factory=list)

    def __post_init__(self):
        if self.provider not in DEFAULT_MODELS:
            raise ValueError(f"unknown provider {self.provider}")
        self.model = self.model or DEFAULT_MODELS[self.provider]
        self._cache = {}
        if self.cache_path and Path(self.cache_path).exists():
            for line in Path(self.cache_path).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._cache[row["key"]] = row["value"]

    # ------------------------------------------------------------ Agent에 주입하는 함수
    def status(self, text: str):
        value, call = self._interpret("STATUS", text, StatusReading, STATUS_SYSTEM)
        if value is None:
            semantic, kind = interpret_status_reply(text)
            call.semantic, call.block_kind = semantic.value, kind
            return semantic, kind
        kind = value["block_kind"] if value["semantic"] == "REPORTS_BLOCKED" else None
        if value["semantic"] == "REPORTS_BLOCKED" and kind is None:
            kind = "INTERNAL_ISSUE"
        call.semantic, call.block_kind = value["semantic"], kind
        return ReplySemantic(value["semantic"]), kind

    def support(self, text: str):
        value, call = self._interpret("SUPPORT", text, SupportReading, SUPPORT_SYSTEM)
        if value is None:
            semantic = interpret_support_reply(text)
            call.semantic = semantic.value
            return semantic
        call.semantic = value["semantic"]
        return ReplySemantic(value["semantic"])

    # ------------------------------------------------------------ 내부
    def _key(self, kind, text) -> str:
        raw = json.dumps([self.provider, self.model, self.effort if self.provider == "anthropic" else self.think,
                          PROMPT_VERSION, kind, text], ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _interpret(self, kind, text, model_cls, system):
        call = InterpretationCall(kind=kind, text=text, semantic="")
        self.calls.append(call)
        key = self._key(kind, text)
        if key in self._cache:
            value = self._cache[key]
            call.source, call.evidence_phrase, call.reason = "cache", value["evidence_phrase"], value["reason"]
            return value, call
        try:
            value = self._request(text, model_cls, system)
        except Exception as e:  # noqa: BLE001 — 어떤 실패든 규칙 해석기로 대체 (사유는 기록)
            call.source, call.error = "rule_fallback", f"{type(e).__name__}: {e}"[:300]
            return None, call
        call.evidence_phrase, call.reason = value["evidence_phrase"], value["reason"]
        self._cache[key] = value
        if self.cache_path:
            Path(self.cache_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "kind": kind, "text": text, "model": self.model,
                                    "prompt_version": PROMPT_VERSION, "value": value}, ensure_ascii=False) + "\n")
        return value, call

    def _request(self, text, model_cls, system) -> dict:
        if self.provider == "ollama":
            return self._request_ollama(text, model_cls, system)
        if self.client is None:
            import anthropic

            _load_dotenv()
            self.client = anthropic.Anthropic()
        params = dict(
            model=self.model, max_tokens=2048, system=system,
            messages=[{"role": "user", "content": f"답장:\n{text}"}],
            output_config={"effort": self.effort,
                           "format": {"type": "json_schema", "schema": _schema(model_cls)}},
        )
        if self.use_fallbacks:
            response = self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params)
        else:
            response = self.client.messages.create(**params)
        if response.stop_reason == "refusal":
            raise RuntimeError("model refused")
        body = next(b.text for b in response.content if b.type == "text")
        try:
            return model_cls.model_validate_json(body).model_dump()
        except ValidationError as e:
            raise ValueError(f"invalid structured output: {e}") from e

    def _request_ollama(self, text, model_cls, system) -> dict:
        post = self.client or _http_post
        payload = {"model": self.model, "stream": False, "think": self.think, "format": _schema(model_cls),
                   "options": {"temperature": 0, "seed": 7},
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": f"답장:\n{text}"}]}
        body = post(OLLAMA_URL, payload)
        try:
            return model_cls.model_validate_json(body["message"]["content"]).model_dump()
        except (KeyError, ValidationError) as e:
            raise ValueError(f"invalid structured output: {e}") from e

    def trace(self) -> list[dict]:
        return [asdict(c) for c in self.calls]
