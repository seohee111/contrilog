"""Memory 학습 시퀀스와 anti-profiling: 같은 상황이면 누구의 Task든 같은 보정, 상황이 다르면 미적용."""

import json

import pytest

from contrilog.evaluation.memory_evaluation import run_mode
from contrilog.schemas import FeedbackLabel, StagnationState as S
from tests.memory_fixtures import sequence_sim, sequence_world
from tests.stagnation_fixtures import kst, remap_json, rename_text
from tests.test_claim_agent_generalization import _noise


def _run(tmp_path, mode="ON", assignees=("M_A", "M_C", "M_D"), pre=None, post=None):
    def world(raw):
        raw = pre(raw) if pre else raw
        return sequence_world(raw, assignees)

    def sim(s):
        return sequence_sim(s, assignees)

    kwargs = dict(input_transform=world, simulation_transform=sim)
    if post:
        kwargs = dict(input_transform=lambda raw: post(world(raw)), simulation_transform=lambda s: post(sim(s)),
                      decisions_transform=post)
    session, agent, store = run_mode(mode, tmp_path, **kwargs)
    return agent, store


def _seq(agent):
    runs = {r.task_id: r for r in reversed(agent.runs()) if r.task_id in ("T31", "T32", "T33")}
    apps = [p for p in agent.policy_applications() if p.task_id in ("T31", "T32", "T33")]
    return runs, apps


def _summary(agent, store):
    runs, apps = _seq(agent)
    return {
        "runs": {t: [s.value for s in r.state_sequence] for t, r in sorted(runs.items())},
        "apps": [(p.task_id, p.check.observed_at.isoformat(), p.check.base_is_candidate, p.check.is_candidate,
                  p.check.memory_adjustment_hours) for p in apps],
        "memories": [(m.feedback_label.value, m.context.model_dump(mode="json"), m.observed_signal, m.created_at.isoformat())
                     for m in store.all()],
    }


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    on = _run(tmp_path_factory.mktemp("on"))
    off = _run(tmp_path_factory.mktemp("off"), mode="OFF")
    return on, off


def test_false_positive_memory_reduces_unnecessary_question_for_another_persons_task(base):
    (agent, store), (off_agent, _) = base
    on_runs, apps = _seq(agent)
    off_runs, _ = _seq(off_agent)
    assert "T32" in off_runs and "T32" not in on_runs  # OFF는 Y에게 물었고, ON은 묻지 않았다
    x_memory = next(m for m in store.all() if "T31" in m.evidence_ids)
    assert x_memory.feedback_label == FeedbackLabel.FALSE_POSITIVE
    y = next(p for p in apps if p.task_id == "T32" and p.check.base_is_candidate)
    assert not y.check.is_candidate and y.check.memory_adjustment_hours == 12.0
    assert x_memory.memory_id in y.decision.applied_memory_ids
    assert x_memory.created_at < y.check.observed_at
    assert "Memory 보정 +12h" in " ".join(y.check.reasons) or "+12" in y.decision.rationale
    # Y는 실제로 곧 기록을 남겼다 (불필요한 질문이었음)
    assert y.check.observed_at < kst(10, 3, 18)


def test_real_block_still_detected_despite_relaxation(base):
    (agent, store), _ = base
    on_runs, _ = _seq(agent)
    z = on_runs["T33"]
    assert z.state_sequence == [S.NORMAL, S.STAGNATION_CANDIDATE, S.CONFIRMED_BLOCK]
    check = z.candidate_checks[0]
    assert check.memory_adjustment_hours == 12.0 and check.effective_idle_hours >= check.effective_idle_limit_hours
    assert any(m.feedback_label == FeedbackLabel.TRUE_POSITIVE and "T33" in m.evidence_ids for m in store.all())


def test_same_context_different_people_get_same_adjustment(base, tmp_path):
    (agent, store), _ = base
    permuted = _run(tmp_path, assignees=("M_D", "M_B", "M_A"))  # X/Y/Z 담당자를 바꾼다
    assert _summary(*permuted) == _summary(agent, store)


def test_member_id_and_name_changes_do_not_change_memory(base, tmp_path):
    (agent, store), _ = base
    mapping = {"M_A": "M_W", "M_B": "M_X", "M_C": "M_Y", "M_D": "M_Z"}
    remapped = _run(tmp_path / "ids", pre=None, post=lambda o: remap_json(o, mapping))
    assert _summary(*remapped) == _summary(agent, store)
    renamed = _run(tmp_path / "names", post=rename_text)
    assert _summary(*renamed) == _summary(agent, store)


def test_task_id_change(base, tmp_path):
    (agent, store), _ = base
    mapping = {f"T{i:02d}": f"T{i + 60:02d}" for i in range(1, 12)}  # 기존 Task ID 전체 변경
    remapped = _run(tmp_path, post=lambda o: remap_json(o, mapping))
    assert _summary(*remapped)["apps"] == _summary(agent, store)["apps"]
    assert [m[:3] for m in _summary(*remapped)["memories"]] == [m[:3] for m in _summary(agent, store)["memories"]]


def test_same_person_different_context_does_not_reuse_memory(base):
    (agent, store), _ = base
    x_memory = next(m for m in store.all() if "T31" in m.evidence_ids)
    for p in agent.policy_applications():
        if x_memory.memory_id in p.check.applied_memory_ids:
            assert p.check.context.model_dump() == x_memory.context.model_dump()
    # X 담당자(A)의 다른 Task(T10)는 다른 상황이므로 X의 Memory가 적용되지 않는다
    a_checks = [c for r in agent.runs() if r.task_id == "T10" for c in r.candidate_checks] + \
               [p.check for p in agent.policy_applications() if p.task_id == "T10"]
    assert a_checks and all(x_memory.memory_id not in c.applied_memory_ids for c in a_checks)


def test_noise_does_not_change_sequence_outcome(base, tmp_path):
    (agent, store), _ = base
    noisy = _run(tmp_path, pre=_noise)
    runs, _ = _seq(noisy[0])
    assert "T32" not in runs and runs["T33"].state_sequence[-1] == S.CONFIRMED_BLOCK


def test_memory_has_no_person_tokens(base):
    (agent, store), _ = base
    text = json.dumps([m.model_dump(mode="json") for m in store.all()], ensure_ascii=False)
    for token in ["윤서진", "한도윤", "박지후", "이하은", "reliab", "diligen", "slow", "frequent_blocker"]:
        assert token not in text
