"""두 번째 평가 프로젝트 P002: 데이터 무결성, 생성기 재현성, 평가 계층의 프로젝트 일반화.

P002는 평가용(held-out) 데이터다. 여기서는 Agent 성능 수치를 고정하지 않는다
(성능을 테스트로 고정하면 P002에 맞춘 튜닝을 유도한다). 데이터가 의도한 상황을 담고 있는지와
평가 파이프라인이 P001 하드코딩 없이 동작하는지만 검사한다.
"""

import importlib.util
import json
from collections import Counter
from datetime import datetime

import pytest
from pydantic import ValidationError

from contrilog.data_access import load_project_input
from contrilog.data_access.integrity import check_input_integrity
from contrilog.data_access.paths import DATA_ROOT
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.integrity import check_ground_truth_integrity
from contrilog.evaluation.memory_evaluation import mode_metrics, run_mode
from contrilog.evaluation.stagnation_evaluation import evaluate_all, run_monitoring, summarize
from contrilog.schemas import ReplySemantic, StagnationState
from contrilog.schemas import ground_truth as G
from contrilog.simulation.loader import (
    check_human_decision_integrity,
    check_simulation_integrity,
    load_human_decisions,
    load_simulated_replies,
)

PID = "P002"
PROJECTS = ["P001", "P002"]


@pytest.fixture(scope="module")
def data():
    return load_project_input(PID)


@pytest.fixture(scope="module")
def gt():
    return load_ground_truth(PID)


@pytest.fixture(scope="module")
def monitored():
    _, agent, _ = run_monitoring(project_id=PID)
    return agent


# ---------------------------------------------------------------- 데이터 무결성
@pytest.mark.parametrize("pid", PROJECTS)
def test_all_layers_valid(pid):
    data = load_project_input(pid)
    replies = load_simulated_replies(pid)
    errors = (check_input_integrity(data) + check_simulation_integrity(replies, data)
              + check_human_decision_integrity(load_human_decisions(pid), data)
              + check_ground_truth_integrity(load_ground_truth(pid), data, replies))
    assert errors == []


@pytest.mark.parametrize("pid", PROJECTS)
def test_every_simulated_reply_has_a_label(pid):
    labeled = {x.reply_id for x in load_ground_truth(pid).reply_labels}
    assert labeled == {r.reply_id for r in load_simulated_replies(pid)}


def test_generator_matches_files_on_disk():
    """data/*/P002 는 scripts/build_p002_data.py의 출력과 같아야 한다 (손으로 고친 파일이 생성기와 어긋나지 않게)."""
    spec = importlib.util.spec_from_file_location("build_p002", DATA_ROOT.parent / "scripts" / "build_p002_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for layer, files in mod.build().items():
        for name, content in files.items():
            on_disk = json.loads((DATA_ROOT / layer / PID / name).read_text(encoding="utf-8"))
            assert on_disk == json.loads(json.dumps(content, ensure_ascii=False)), f"{layer}/{name}"


def test_p002_is_a_different_project(data):
    p001 = load_project_input("P001")
    assert data.project.name != p001.project.name
    assert {m.name for m in data.members}.isdisjoint({m.name for m in p001.members})
    texts = lambda d: {u.text for u in d.utterances} | {m.text for m in d.messages}  # noqa: E731
    assert texts(data).isdisjoint(texts(p001))


def test_record_ids_are_chronological(data):
    for items, at in [(data.document_history, "edited_at"), (data.messages, "sent_at")]:
        times = [getattr(x, at) for x in items]
        assert times == sorted(times)


# ---------------------------------------------------------------- 인수인계 문서 11.1의 9가지 상황
def test_required_situations_are_present(data, gt):
    tasks = {t.task_id: t for t in data.tasks}
    s = gt.stagnations
    blocks = [x for x in s if x.is_actual_block]
    # 1. 정상적인 장시간 공백 / 3. False Positive 반복 (같은 종류의 정상 공백이 여러 번)
    assert sum(not x.is_actual_block and x.candidate_expected is True for x in s) >= 4
    # 2. 실제 Block (팀 내 지원으로 해결)
    assert any(x.expected_final_state == StagnationState.RESOLVED and x.expected_intervention for x in blocks)
    # 4. 응답 없는 Candidate: 정상 항목인데 그 Task·담당자에게 상태 확인 응답이 전혀 없음
    replies = load_simulated_replies(PID)
    silent = [x for x in s if not any(r.task_id == x.task_id and r.responder_id == x.member_id for r in replies)]
    assert silent
    # 5. 복합 자연어 응답: 해석 주석이 붙은 응답이 여러 개
    assert sum(bool(x.note) for x in gt.reply_labels) >= 5
    # 6. 지원자가 여러 명 / 7. 잘못된 지원자 후보: 지원 요청에 수락·사양 응답이 함께 준비됨
    support = Counter((r.task_id, r.about_member_id) for r in replies if r.trigger.value == "SUPPORT_REQUEST")
    assert sum(n >= 3 for n in support.values()) >= 3
    # 8. 해결되지 않는 Block
    assert any(x.expected_final_state == StagnationState.CONFIRMED_BLOCK and StagnationState.RESOLVED in x.forbidden_states
               for x in blocks)
    # 9. 여러 담당자가 있는 Task에서 주 담당자가 아닌 사람의 Block
    assert any(len(tasks[x.task_id].assignee_ids) > 1 and tasks[x.task_id].assignee_ids[0] != x.member_id
               for x in blocks)
    # 외부 의존 Block과 사람의 거절 결정
    assert {x.block_kind for x in blocks} == {"INTERNAL_ISSUE", "EXTERNAL_DEPENDENCY"}
    assert any(d.decision.value == "REJECT" for d in load_human_decisions(PID))


def test_team_wide_pauses_come_from_data_only(data):
    """휴일은 하드코딩하지 않는다: 연휴(4/30~5/6) 동안 공개 기록이 실제로 비어 있다."""
    times = sorted([r.edited_at for r in data.document_history] + [m.sent_at for m in data.messages]
                   + [u.spoken_at for u in data.utterances])
    gaps = [(b - a).total_seconds() / 3600 for a, b in zip(times, times[1:])]
    assert max(gaps) > 100


# ---------------------------------------------------------------- Ground Truth 스키마 확장
def _stagnation(gt, gid):
    return next(x for x in gt.stagnations if x.gt_stagnation_id == gid).model_dump(mode="json")


def test_resolved_without_team_support_is_allowed(gt):
    external = [x for x in gt.stagnations if x.block_kind == "EXTERNAL_DEPENDENCY"
                and x.expected_final_state == StagnationState.RESOLVED]
    assert external and all(x.expected_intervention is None for x in external)


def test_new_ground_truth_rules(gt):
    non_block = _stagnation(gt, "GTS-01")
    with pytest.raises(ValidationError):  # Block이 아닌데 Block 종류
        G.GroundTruthStagnation.model_validate({**non_block, "block_kind": "INTERNAL_ISSUE"})
    external = _stagnation(gt, "GTS-07")
    with pytest.raises(ValidationError):  # 외부 의존인데 팀 내 지원 기대
        G.GroundTruthStagnation.model_validate({**external, "expected_intervention": {
            "intervention_type": "SUPPORT", "supporter_member_id": "M_E", "earliest_at": None}})
    with pytest.raises(ValidationError):  # 실제 Block인데 확인 불필요
        G.GroundTruthStagnation.model_validate({**external, "candidate_expected": False})
    label = gt.reply_labels[0].model_dump(mode="json")
    with pytest.raises(ValidationError):  # REPORTS_BLOCKED인데 Block 종류 없음
        G.GroundTruthReplyLabel.model_validate({**label, "expected_semantic": "REPORTS_BLOCKED",
                                                "expected_block_kind": None})


def test_reply_label_must_fit_the_question(gt, data):
    replies = load_simulated_replies(PID)
    support_label = next(x for x in gt.reply_labels if x.expected_semantic == ReplySemantic.ACCEPTS_SUPPORT)
    broken = gt.model_copy(update={"reply_labels": [
        x if x is not support_label else x.model_copy(update={"expected_semantic": ReplySemantic.REPORTS_ON_TRACK})
        for x in gt.reply_labels]})
    errors = check_ground_truth_integrity(broken, data, replies)
    assert any("not a possible answer" in e for e in errors)
    missing = gt.model_copy(update={"reply_labels": gt.reply_labels[1:]})
    assert any("has no reply label" in e for e in check_ground_truth_integrity(missing, data, replies))


# ---------------------------------------------------------------- 평가 파이프라인 (P001 하드코딩 없음)
def test_monitoring_starts_at_project_start(monitored, data):
    assert monitored.project_id == PID
    assert min(r.started_at for r in monitored.runs()).date() >= data.project.start_date


def test_evaluation_scores_every_item(monitored, gt):
    evals = evaluate_all(gt, monitored.runs())
    assert [e.gt_stagnation_id for e in evals] == [x.gt_stagnation_id for x in gt.stagnations]
    summary = summarize(evals)
    assert summary.items == len(gt.stagnations)
    by_id = {e.gt_stagnation_id: e for e in evals}
    for item in gt.stagnations:
        e = by_id[item.gt_stagnation_id]
        if item.candidate_expected is None:
            assert e.candidate_correct is None
        if item.block_kind == "EXTERNAL_DEPENDENCY" and item.expected_intervention is None:
            assert e.intervention_scored  # 외부 의존 Block은 '지원 요청 없음'을 채점한다
        if not item.is_actual_block:
            assert e.block_kind_correct is None and e.runs_after_block_episode == []


def test_block_items_are_scored_on_their_block_episode(monitored, gt):
    """Block 확정 에피소드 이후 같은 단위에서 다시 열린 후보는 최종 상태 채점에서 분리해 보고한다."""
    for e in evaluate_all(gt, monitored.runs()):
        for rid in e.runs_after_block_episode:
            assert rid not in e.run_ids
        if e.runs_after_block_episode:
            assert StagnationState.CONFIRMED_BLOCK in e.state_sequence


def test_human_rejection_is_respected(monitored):
    for run in monitored.runs():
        if run.intervention is None:
            continue
        hist = [h.status.value for h in run.intervention.status_history]
        if "REJECTED" in hist:
            assert "SENT" not in hist and not run.support_interactions


def test_memory_comparison_runs_on_p002(gt):
    _, agent, store = run_mode("ON", project_id=PID)
    m = mode_metrics("ON", agent, store, gt)
    assert set(m.non_block_correct) == {x.gt_stagnation_id for x in gt.stagnations if not x.is_actual_block}
    assert set(m.resolved_correct) == {x.gt_stagnation_id for x in gt.stagnations
                                       if x.expected_final_state == StagnationState.RESOLVED}
    assert all(mem.project_id == PID and mem.created_at <= datetime.fromisoformat("2026-06-20T00:00:00+09:00")
               for mem in store.all())


def test_reply_benchmark_keys_replies_by_project():
    """SIM 번호는 프로젝트마다 1부터 시작한다. 여러 프로젝트를 합쳐도 라벨이 자기 프로젝트 문장과 짝지어져야 한다."""
    from contrilog.evaluation.reply_evaluation import evaluate_replies, oracle_interpreters

    labels = [x for p in PROJECTS for x in load_ground_truth(p).reply_labels]
    replies = [r for p in PROJECTS for r in load_simulated_replies(p)]
    by_key = {(r.project_id, r.reply_id): r.reply_text for r in replies}
    assert {(c.project_id, c.reply_id): c.text for c in evaluate_replies(labels, replies)} == by_key
    status, support = oracle_interpreters(labels, replies)
    cases = evaluate_replies(labels, replies, status_interpreter=status, support_interpreter=support)
    assert all(c.correct is not False for c in cases)
