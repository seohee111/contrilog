"""Memory OFF / CONTEXT_ONLY / MEMORY_ONLY / ON / 약한 UNRESOLVED 변형 비교 (실제 결과를 그대로 고정)."""

import pytest

from contrilog.evaluation.memory_evaluation import CAVEAT, MODES, mode_metrics, run_mode
from tests.stagnation_fixtures import GT


@pytest.fixture(scope="module")
def table():
    out = {}
    for mode in MODES:
        _, agent, store = run_mode(mode)
        out[mode] = mode_metrics(mode, agent, store, GT)
    return out


def test_comparison_table(table):
    row = {m: (v.candidates, v.status_checks, v.true_positive, v.false_positive, v.unresolved, v.confirmed_blocks)
           for m, v in table.items()}
    assert row == {"OFF": (13, 13, 2, 1, 10, 2), "CONTEXT_ONLY": (11, 11, 2, 1, 8, 2),
                   "MEMORY_ONLY": (13, 13, 2, 1, 10, 2), "ON": (11, 11, 2, 1, 8, 2),
                   "ON_WEAK_UNRESOLVED": (11, 11, 2, 1, 8, 2)}


def test_real_blocks_and_case04_in_every_mode(table):
    for m, v in table.items():
        assert v.gt_blocks_detected == ["CASE03", "CASE10"] and v.false_negatives == [], m
        assert v.non_block_correct == {"GTS-02": True} and v.resolved_correct == {"GTS-03": True}, m


def test_detection_delay_by_mode(table):
    assert table["ON"].detection_delay_candidate_hours == table["OFF"].detection_delay_candidate_hours == \
           {"CASE03": 91.3, "CASE10": 28.8}
    # 약한 UNRESOLVED 변형은 질문을 줄이지 못하고 Case10 탐지만 12시간 늦췄다 (기본값으로 채택하지 않은 이유)
    assert table["ON_WEAK_UNRESOLVED"].detection_delay_candidate_hours["CASE10"] == 40.8


def test_where_the_reduction_comes_from(table):
    assert table["CONTEXT_ONLY"].suppressed_by_adjustment > 0  # 팀 전체 휴지기 맥락
    assert table["MEMORY_ONLY"].adjusted_checks == 0  # P001 재생에서는 같은 상황의 FP·TP가 상쇄되어 보정 없음
    assert "회귀 확인용" in CAVEAT
