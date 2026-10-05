"""전체 평가: 응답 해석기(규칙 / LLM / 오라클) × 프로젝트(P001, P002) × Memory(OFF / ON).

사용법:
  python scripts/evaluate_all.py              # 로컬 LLM(Ollama qwen3:32b) 포함. 서버가 없으면 LLM 행은 규칙으로 대체됨
  python scripts/evaluate_all.py --provider anthropic   # Claude API (.env의 ANTHROPIC_API_KEY)
  python scripts/evaluate_all.py --no-llm     # 규칙·오라클만
출력: reports/evaluation_<시각>.json, reports/evaluation_<시각>.md (+ reports/latest.{json,md})

- 규칙: 기존 결정적 단서 해석기 (baseline)
- LLM: contrilog.llm.LLMReplyInterpreter (응답 의미 분류만 교체, 나머지 흐름은 동일)
- 오라클: Ground Truth 응답 라벨을 그대로 돌려주는 평가용 상한선 (해석 오류를 제거했을 때 나머지 단계의 성능)
주의: Agent와 같은 팀이 만든 synthetic 데이터다. 개수는 비교·회귀 확인용이며 일반 성능 추정치가 아니다.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from contrilog.agent.stagnation import FeedbackSettings, StagnationAgent
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.memory_evaluation import mode_metrics
from contrilog.evaluation.reply_evaluation import evaluate_replies, oracle_interpreters, summarize_replies
from contrilog.evaluation.stagnation_evaluation import evaluate_all, run_monitoring, summarize, unlabeled_candidates
from contrilog.memory import InMemoryMemoryStore
from contrilog.simulation.loader import load_simulated_replies

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ["P001", "P002"]


def interpreters(kind: str, llm):
    if kind == "rule":
        return {}
    if kind == "llm":
        return {"status_interpreter": llm.status, "support_interpreter": llm.support}
    labels, replies = [], []
    for p in PROJECTS:
        labels += load_ground_truth(p).reply_labels
        replies += load_simulated_replies(p)
    status, support = oracle_interpreters(labels, replies)
    return {"status_interpreter": status, "support_interpreter": support}


def run_stagnation(project_id: str, kind: str, memory: bool, llm):
    store = InMemoryMemoryStore() if memory else None
    feedback = FeedbackSettings(store=store) if memory else None
    extra = interpreters(kind, llm)
    _, agent, _ = run_monitoring(project_id=project_id, agent_factory=lambda tools: StagnationAgent(
        tools=tools, feedback=feedback, **extra))
    gt = load_ground_truth(project_id)
    runs = agent.runs()
    evals = evaluate_all(gt, runs)
    unl = unlabeled_candidates(runs, gt)
    off_hours = [c for r in runs for c in r.check_ins
                 if c.sent_at.weekday() >= 5 or not 9 <= c.sent_at.hour < 19]
    metrics = mode_metrics("ON" if memory else "OFF", agent, store or InMemoryMemoryStore(), gt)
    return {
        "summary": summarize(evals, len(unl)).model_dump(mode="json"),
        "items": [{k: e.model_dump(mode="json")[k] for k in (
            "gt_stagnation_id", "case_id", "task_id", "member_id", "state_sequence", "reply_semantic",
            "expected_reply_semantic", "block_kind", "expected_block_kind", "supporter_selected", "supporter_correct",
            "final_state", "final_state_correct", "forbidden_state_violations", "detection_delay_confirmed_hours",
            "runs_after_block_episode")} | {"all_correct": e.all_correct} for e in evals],
        "questions": metrics.status_checks, "candidates": metrics.candidates,
        "questions_outside_work_hours": len(off_hours),
        "false_negatives": metrics.false_negatives, "true_positive": metrics.true_positive,
        "false_positive": metrics.false_positive, "unresolved": metrics.unresolved,
    }


def reply_benchmark(llm, kinds):
    out = {}
    labels, replies = [], []
    for p in PROJECTS:
        labels += load_ground_truth(p).reply_labels
        replies += load_simulated_replies(p)
    for kind in kinds:
        extra = interpreters(kind, llm)
        cases = evaluate_replies(labels, replies, **extra)
        out[kind] = summarize_replies(cases, kind).model_dump(mode="json")
    return out


def pct(c):
    return f"{c['correct']}/{c['total']}" + (f" ({100 * c['correct'] / c['total']:.0f}%)" if c["total"] else "")


def markdown(result) -> str:
    lines = [f"# ContriLog 평가 결과 ({result['generated_at']})", "", f"> {result['caveat']}", ""]
    llm = result["llm"]
    lines += [f"- LLM: {llm.get('provider')} {llm['model']} (think={llm.get('think')}) · 사용 가능: {llm['available']} · 호출 {llm['calls']}회 "
              f"(API {llm['api']} / 캐시 {llm['cache']} / 규칙 대체 {llm['fallback']})", ""]
    lines += ["## 1. 응답 해석 (P001+P002 시뮬레이션 응답, 정답 라벨 대비)", "",
              "| 해석기 | 전체 | 상태 확인 응답 | 지원 요청 응답 | 해석 주의 응답 | Block 종류 |", "|---|---|---|---|---|---|"]
    for k, s in result["reply_benchmark"].items():
        lines.append(f"| {k} | {pct(s['overall'])} | {pct(s['by_kind']['STATUS_CHECK'])} | "
                     f"{pct(s['by_kind']['SUPPORT_REQUEST'])} | {pct(s['hard_cases'])} | {pct(s['block_kind'])} |")
    lines += ["", "## 2. 정체 Agent 전체 (프로젝트 시작~종료 연속 실행)", ""]
    head = ("| 프로젝트 | 해석기 | Memory | 질문 수 | 업무시간 외 질문 | Block 판정 | Block 종류 | 최종 상태 | 지원자 | 해결 판정 | "
            "놓친 실제 Block |")
    lines += [head, "|" + "---|" * 11]
    for row in result["stagnation"]:
        s = row["summary"]
        lines.append(f"| {row['project']} | {row['interpreter']} | {'ON' if row['memory'] else 'OFF'} | {row['questions']} | "
                     f"{row['questions_outside_work_hours']} | {pct(s['block_classification'])} | {pct(s['block_kind'])} | "
                     f"{pct(s['final_state'])} | {pct(s['support_candidate'])} | {pct(s['resolution'])} | "
                     f"{', '.join(row['false_negatives']) or '-'} |")
    lines += ["", "## 3. 항목별 (Memory OFF)", ""]
    for row in result["stagnation"]:
        if row["memory"]:
            continue
        lines += [f"### {row['project']} · {row['interpreter']}", "", "| 항목 | Case | Task·담당 | 응답 해석 (기대) | 지원자 | 최종 (정답 여부) | 금지 상태 |",
                  "|---|---|---|---|---|---|---|"]
        for it in row["items"]:
            lines.append(f"| {it['gt_stagnation_id']} | {it['case_id']} | {it['task_id']}·{it['member_id']} | "
                         f"{it['reply_semantic'] or '-'} ({it['expected_reply_semantic'] or '-'}) | "
                         f"{it['supporter_selected'] or '-'}{'' if it['supporter_correct'] is None else (' ✓' if it['supporter_correct'] else ' ✗')} | "
                         f"{it['final_state']} ({'✓' if it['final_state_correct'] else '✗'}) | "
                         f"{', '.join(it['forbidden_state_violations']) or '-'} |")
        lines.append("")
    errs = result["reply_benchmark"].get("llm", {}).get("errors", [])
    if errs:
        lines += ["## 4. LLM 해석 오답", "", "| 응답 | 기대 | LLM | 문장 |", "|---|---|---|---|"]
        for e in errs:
            lines.append(f"| {e['project_id']} {e['reply_id']} | {e['expected']} {e['expected_block_kind'] or ''} | "
                         f"{e['predicted']} {e['predicted_block_kind'] or ''} | {e['text'][:60]} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--provider", choices=["ollama", "anthropic"], default="ollama")
    ap.add_argument("--model", default=None)
    ap.add_argument("--think", action="store_true", help="ollama 추론 모델의 사고 단계 사용")
    ap.add_argument("--tag", default="", help="출력 파일 이름에 붙일 표시")
    args = ap.parse_args(argv)
    llm = None
    kinds = ["rule", "oracle"]
    if not args.no_llm:
        from contrilog.llm import LLMReplyInterpreter

        llm = LLMReplyInterpreter(provider=args.provider, model=args.model, think=args.think)
        kinds = ["rule", "llm", "oracle"]
    result = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
              "caveat": "Agent와 같은 팀이 만든 synthetic 데이터(P001·P002)의 개수다. 비교·회귀 확인용이며 일반 성능 추정치가 아니다.",
              "reply_benchmark": reply_benchmark(llm, kinds), "stagnation": []}
    for p in PROJECTS:
        for kind in kinds:
            for memory in (False, True):
                row = run_stagnation(p, kind, memory, llm)
                result["stagnation"].append({"project": p, "interpreter": kind, "memory": memory, **row})
                print(f"{p} {kind} memory={memory}: final {pct(row['summary']['final_state'])}", file=sys.stderr)
    calls = llm.calls if llm else []
    result["llm"] = {"provider": llm.provider if llm else None, "think": llm.think if llm else None,
                     "model": llm.model if llm else None, "calls": len(calls),
                     "api": sum(c.source == "llm" for c in calls), "cache": sum(c.source == "cache" for c in calls),
                     "fallback": sum(c.source == "rule_fallback" for c in calls),
                     "available": bool(llm) and any(c.source in ("llm", "cache") for c in calls),
                     "first_error": next((c.error for c in calls if c.error), None),
                     "key_present": bool(os.environ.get("ANTHROPIC_API_KEY"))}
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    for name in (f"evaluation_{stamp}{'_' + args.tag if args.tag else ''}", "latest"):
        (out / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / f"{name}.md").write_text(markdown(result), encoding="utf-8")
    print(markdown(result))


if __name__ == "__main__":
    main()
