"""Stagnation 테스트 공용 helper (테스트 전용)."""

import json
import re

from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.stagnation_evaluation import evaluate_all, run_monitoring
from tests.timeline_helpers import kst

GT = load_ground_truth("P001")


def monitor(tmp_path=None, **kwargs):
    session, agent, human = run_monitoring(tmp_path, **kwargs)
    return session, agent, human, agent.runs()


def unit_runs(runs, task_id, member_id):
    return [r for r in runs if r.task_id == task_id and r.assignee_id == member_id]


def metrics(evaluation) -> dict:
    """ID·시각 표현과 무관한 채점 결과 비교용."""
    d = evaluation.model_dump(mode="json")
    for k in ("gt_stagnation_id", "case_id", "task_id", "member_id", "run_ids", "supporter_selected", "approver_id",
              "support_reasons", "resolution_source_ids"):
        d.pop(k, None)
    return d


def remap_json(obj, mapping: dict[str, str]):
    """JSON 값 중 정확히 일치하는 ID 문자열만 바꾼다 (예: "T03" → "T53")."""
    text = json.dumps(obj, ensure_ascii=False)
    for old, new in mapping.items():
        text = re.sub(rf'"{re.escape(old)}"', f'"{new}"', text)
    return json.loads(text)


def remap_gt(mapping: dict[str, str]):
    return GT.model_validate(remap_json(GT.model_dump(mode="json"), mapping))


def evaluate(runs, gt=None):
    return evaluate_all(gt or GT, runs)


NEW_NAMES = {"윤서진": "강가람", "한도윤": "문나래", "박지후": "서다온", "이하은": "조라온",
             "서진": "가람", "도윤": "나래", "지후": "다온", "하은": "라온"}


def rename_text(obj):
    text = json.dumps(obj, ensure_ascii=False)
    for old, new in NEW_NAMES.items():
        text = text.replace(old, new)
    return json.loads(text)


__all__ = ["GT", "evaluate", "kst", "metrics", "monitor", "remap_gt", "remap_json", "rename_text", "unit_runs"]
