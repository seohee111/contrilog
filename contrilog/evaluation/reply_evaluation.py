"""응답 해석기 단독 평가 (평가 계층 전용).

시뮬레이션 응답(SIM-*) 문장마다 Ground Truth 의미 라벨(reply_labels.json)이 있다. 해석기에 문장만 넣고
나온 의미를 라벨과 비교한다. Agent 실행 경로와 무관하게, 응답이 실제로 전달되는지와도 무관하게 채점한다.

대상: 정체 Agent의 두 해석기
  - STATUS_CHECK 응답    → status_interpreter(text) -> (ReplySemantic, block_kind | None)
  - SUPPORT_REQUEST 응답 → support_interpreter(text) -> ReplySemantic
COMPLETION_CONFIRMATION / COUNTERPART_CONFIRMATION 응답은 Claim 검증 Agent가 근거 역할로 해석하므로
문장 단위 해석기가 없다 → 'not_covered'로 개수만 보고한다.

oracle_interpreters(): 라벨을 그대로 돌려주는 해석기. 응답 해석 오류를 빼고 나머지 단계(지원자 선정·해결 판정)의
성능을 분리해 보기 위한 평가용 상한선이며, 평가 계층이 Agent 생성자에 주입한다 (Agent는 Ground Truth를 읽지 않는다).
"""

from collections import Counter
from collections.abc import Callable
from typing import Optional

from pydantic import Field

from contrilog.agent.stagnation.interpreter import interpret_status_reply, interpret_support_reply
from contrilog.schemas import QuestionIntent, ReplySemantic, SimulatedReply, SimulatedTrigger
from contrilog.schemas.base import StrictModel
from contrilog.schemas.ground_truth import GroundTruthReplyLabel

COVERED = ("STATUS_CHECK", "SUPPORT_REQUEST")


class ReplyCase(StrictModel):
    reply_id: str
    project_id: str
    kind: str  # STATUS_CHECK / SUPPORT_REQUEST / (그 밖은 채점하지 않음)
    text: str
    expected: ReplySemantic
    predicted: Optional[ReplySemantic] = None
    expected_block_kind: Optional[str] = None
    predicted_block_kind: Optional[str] = None
    correct: Optional[bool] = None
    block_kind_correct: Optional[bool] = None  # 정답·예측 모두 REPORTS_BLOCKED일 때만
    note: str = ""


class AccuracyCount(StrictModel):
    correct: int
    total: int


class ReplyEvaluationSummary(StrictModel):
    interpreter: str
    by_kind: dict[str, AccuracyCount]
    overall: AccuracyCount
    hard_cases: AccuracyCount  # 라벨에 해석 주의 note가 붙은 응답
    block_kind: AccuracyCount
    confusion: dict[str, dict[str, int]]  # expected → predicted → 개수
    not_covered: int
    errors: list[dict] = Field(default_factory=list)


def reply_kind(reply: SimulatedReply) -> str:
    if reply.trigger == SimulatedTrigger.SUPPORT_REQUEST:
        return "SUPPORT_REQUEST"
    return reply.question_intent.value if reply.question_intent else "UNKNOWN"


def evaluate_replies(labels: list[GroundTruthReplyLabel], replies: list[SimulatedReply], *,
                     status_interpreter: Callable = interpret_status_reply,
                     support_interpreter: Callable = interpret_support_reply) -> list[ReplyCase]:
    by_id = {(r.project_id, r.reply_id): r for r in replies}  # SIM 번호는 프로젝트마다 새로 시작한다
    out = []
    for label in labels:
        r = by_id[(label.project_id, label.reply_id)]
        kind = reply_kind(r)
        case = dict(reply_id=r.reply_id, project_id=r.project_id, kind=kind, text=r.reply_text,
                    expected=label.expected_semantic, expected_block_kind=label.expected_block_kind, note=label.note)
        if kind == "STATUS_CHECK":
            semantic, block_kind = status_interpreter(r.reply_text)
            case.update(predicted=semantic, predicted_block_kind=block_kind)
        elif kind == "SUPPORT_REQUEST":
            case.update(predicted=support_interpreter(r.reply_text))
        if case.get("predicted") is not None:
            case["correct"] = case["predicted"] == label.expected_semantic
            if label.expected_semantic == ReplySemantic.REPORTS_BLOCKED == case["predicted"]:
                case["block_kind_correct"] = case["predicted_block_kind"] == label.expected_block_kind
        out.append(ReplyCase(**case))
    return out


def summarize_replies(cases: list[ReplyCase], interpreter: str = "rule") -> ReplyEvaluationSummary:
    scored = [c for c in cases if c.correct is not None]

    def count(items):
        return AccuracyCount(correct=sum(bool(x) for x in items), total=len(items))

    confusion: dict[str, Counter] = {}
    for c in scored:
        confusion.setdefault(c.expected.value, Counter())[c.predicted.value] += 1
    return ReplyEvaluationSummary(
        interpreter=interpreter,
        by_kind={k: count([c.correct for c in scored if c.kind == k]) for k in COVERED},
        overall=count([c.correct for c in scored]),
        hard_cases=count([c.correct for c in scored if c.note]),
        block_kind=count([c.block_kind_correct for c in scored if c.block_kind_correct is not None]),
        confusion={k: dict(v) for k, v in sorted(confusion.items())},
        not_covered=len(cases) - len(scored),
        errors=[{"reply_id": c.reply_id, "project_id": c.project_id, "kind": c.kind, "text": c.text,
                 "expected": c.expected.value, "predicted": c.predicted.value,
                 "expected_block_kind": c.expected_block_kind, "predicted_block_kind": c.predicted_block_kind,
                 "note": c.note}
                for c in scored if not c.correct or c.block_kind_correct is False])


def oracle_interpreters(labels: list[GroundTruthReplyLabel], replies: list[SimulatedReply]):
    """(status_interpreter, support_interpreter): 응답 문장 → 정답 라벨. 모르는 문장은 NOT_INFORMATIVE."""
    by_id = {(r.project_id, r.reply_id): r for r in replies}
    table = {by_id[(x.project_id, x.reply_id)].reply_text: x for x in labels}
    if len(table) != len(labels):
        raise ValueError("oracle needs unique reply texts")

    def status(text: str):
        x = table.get(text)
        return (x.expected_semantic, x.expected_block_kind) if x else (ReplySemantic.NOT_INFORMATIVE, None)

    def support(text: str):
        x = table.get(text)
        return x.expected_semantic if x else ReplySemantic.NOT_INFORMATIVE

    return status, support


__all__ = ["ReplyCase", "ReplyEvaluationSummary", "evaluate_replies", "oracle_interpreters", "reply_kind",
           "summarize_replies", "QuestionIntent"]
