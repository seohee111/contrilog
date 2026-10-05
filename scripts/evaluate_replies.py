"""응답 해석기 단독 비교 (P001+P002 시뮬레이션 응답 × 정답 라벨). 전체 실행보다 빠른 확인용.

사용법: python scripts/evaluate_replies.py [--provider ollama|anthropic] [--model M] [--think]
"""

import argparse
import json
import time

from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.reply_evaluation import evaluate_replies, summarize_replies
from contrilog.llm import LLMReplyInterpreter
from contrilog.simulation.loader import load_simulated_replies


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["ollama", "anthropic"], default="ollama")
    ap.add_argument("--model", default=None)
    ap.add_argument("--think", action="store_true")
    args = ap.parse_args(argv)
    labels = [x for p in ("P001", "P002") for x in load_ground_truth(p).reply_labels]
    replies = [r for p in ("P001", "P002") for r in load_simulated_replies(p)]
    llm = LLMReplyInterpreter(provider=args.provider, model=args.model, think=args.think)
    started = time.time()
    rule = summarize_replies(evaluate_replies(labels, replies), "rule")
    cases = evaluate_replies(labels, replies, status_interpreter=llm.status, support_interpreter=llm.support)
    s = summarize_replies(cases, f"{llm.provider}:{llm.model}")
    sources = {k: sum(c.source == k for c in llm.calls) for k in ("llm", "cache", "rule_fallback")}
    print(json.dumps({"rule": {k: rule.model_dump()[k] for k in ("overall", "by_kind", "hard_cases", "block_kind")},
                      "llm": {k: s.model_dump()[k] for k in ("interpreter", "overall", "by_kind", "hard_cases", "block_kind")},
                      "calls": sources, "seconds": round(time.time() - started, 1),
                      "first_error": next((c.error for c in llm.calls if c.error), None),
                      "llm_errors": s.errors}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
