"""모든 데이터의 schema validation, enum 범위, 금지 필드 검사."""

import json
from datetime import datetime, timedelta, timezone
from enum import Enum

import pytest
from pydantic import BaseModel, ValidationError

import contrilog.schemas as S
from contrilog.schemas import ground_truth as G

KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 10, 9, 10, 0, tzinfo=KST)


def test_input_files_pass_schema(project_input):
    assert project_input.project.project_id == "P001"
    assert {m.label for m in project_input.members} == {"A", "B", "C", "D"}
    for name in ["meetings", "utterances", "document_history", "tasks", "messages", "claims"]:
        assert getattr(project_input, name), f"{name} is empty"


def test_ground_truth_and_simulation_pass_schema(ground_truth, replies):
    assert len(ground_truth.cases) == 10
    assert replies


def test_every_json_file_under_data_is_covered(data_root):
    """data/ 아래 JSON 파일은 모두 로더가 읽는 파일이어야 한다 (검증되지 않는 파일 방지)."""
    from contrilog.data_access.paths import INPUT_FILES
    from contrilog.evaluation.paths import GROUND_TRUTH_FILES
    from contrilog.simulation.loader import HUMAN_DECISIONS_FILE, REPLIES_FILE

    known = {
        "input": set(INPUT_FILES.values()),
        "ground_truth": set(GROUND_TRUTH_FILES.values()),
        "simulation": {REPLIES_FILE, HUMAN_DECISIONS_FILE},
    }
    for path in data_root.rglob("*.json"):
        top = path.relative_to(data_root).parts[0]
        assert top in known, f"unexpected data directory: {path}"
        assert path.name in known[top], f"unvalidated json file: {path}"
        json.loads(path.read_text(encoding="utf-8"))


def test_enum_members_are_fixed():
    assert {e.value for e in S.ContributionType} == {"IDEA", "EXECUTION", "REVIEW", "COORDINATION", "SUPPORT"}
    assert {e.value for e in S.ClaimStatus} == {
        "VERIFIED", "INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE", "PENDING_VERIFICATION"}
    assert {e.value for e in S.StagnationState} == {
        "NORMAL", "STAGNATION_CANDIDATE", "CONFIRMED_BLOCK", "RESOLVED"}


# ---- enum 외 값 거부 -------------------------------------------------------

def _mutated(raw: dict, **changes) -> dict:
    out = json.loads(json.dumps(raw))
    out.update(changes)
    return out


@pytest.mark.parametrize("bad", ["LEADERSHIP", "idea", "", "SCORE"])
def test_invalid_contribution_type_rejected(raw_ground_truth, bad):
    item = _mutated(raw_ground_truth["contributions"][0], contribution_type=bad)
    with pytest.raises(ValidationError):
        G.GroundTruthContribution.model_validate(item)


def test_invalid_claim_status_rejected(raw_ground_truth, raw_input):
    with pytest.raises(ValidationError):
        G.GroundTruthClaimJudgment.model_validate(
            _mutated(raw_ground_truth["claim_judgments"][0], expected_status="REJECTED"))
    with pytest.raises(ValidationError):
        S.ContributionClaim.model_validate(_mutated(raw_input["claims"][0], status="APPROVED"))


def test_invalid_stagnation_state_rejected(raw_ground_truth):
    with pytest.raises(ValidationError):
        G.GroundTruthStagnation.model_validate(
            _mutated(raw_ground_truth["stagnations"][0], expected_final_state="BLOCKED"))
    with pytest.raises(ValidationError):
        G.GroundTruthStagnation.model_validate(
            _mutated(raw_ground_truth["stagnations"][2], expected_state_sequence=["STAGNATION_CANDIDATE", "STUCK", "RESOLVED"]))


def test_invalid_task_status_rejected(raw_input):
    with pytest.raises(ValidationError):
        S.Task.model_validate(_mutated(raw_input["tasks"][2], status="BLOCKED"))


def test_raw_enum_fields_only_contain_enum_values(raw_input, raw_ground_truth):
    """JSON 원문을 직접 훑어 enum 필드 값이 정의된 enum 안에 있는지 확인한다."""
    enum_fields = {
        "contribution_type": S.ContributionType, "claimed_type": S.ContributionType,
        "expected_status": S.ClaimStatus, "status": None,  # status는 Task/Claim에 따라 다름
        "expected_final_state": S.StagnationState, "document_type": S.DocumentType,
        "channel_type": S.ChannelType, "source": S.ClaimSource, "to_status": S.TaskStatus,
        "from_status": S.TaskStatus, "intervention_type": S.InterventionType,
    }
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                enum_cls = enum_fields.get(k)
                if enum_cls is not None and v is not None:
                    assert v in {e.value for e in enum_cls}, f"{k}={v!r} not in {enum_cls.__name__}"
                    seen.add(k)
                if k in ("expected_state_sequence", "forbidden_states") and v:
                    assert all(s in {e.value for e in S.StagnationState} for s in v)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw_input)
    walk(raw_ground_truth)
    for t in raw_input["tasks"]:
        assert t["status"] in {e.value for e in S.TaskStatus}
    for c in raw_input["claims"]:
        assert c["status"] in {e.value for e in S.ClaimStatus}
    assert {"contribution_type", "expected_status", "expected_final_state", "to_status"} <= seen


def test_extra_fields_rejected(raw_input):
    with pytest.raises(ValidationError):
        S.Member.model_validate(_mutated(raw_input["members"][0], diligence="high"))


def test_naive_datetime_rejected(raw_input):
    with pytest.raises(ValidationError):
        S.Message.model_validate(_mutated(raw_input["messages"][0], sent_at="2026-09-02T22:15:00"))


def test_wrong_id_format_rejected(raw_input):
    with pytest.raises(ValidationError):
        S.Message.model_validate(_mutated(raw_input["messages"][0], sender_id="A"))


# ---- 금지 필드: 점수·순위·사람 프로파일링 ------------------------------------

def _all_models():
    mods = [S, G]
    seen = {}
    for mod in mods:
        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__.startswith("contrilog"):
                seen[obj.__name__] = obj
    return seen.values()


FORBIDDEN_FIELD_WORDS = ["score", "rank", "rating", "weight", "point", "grade", "personality", "diligence",
                         "attendance", "sincerity", "productivity"]


def test_no_score_rank_or_profiling_fields():
    for model in _all_models():
        for field in model.model_fields:
            assert not any(w in field.lower() for w in FORBIDDEN_FIELD_WORDS), f"{model.__name__}.{field}"


def test_agent_memory_has_no_person_fields():
    assert not [f for f in S.AgentMemory.model_fields if "member" in f]


# ---- Agent 출력 모델 생성 가능 여부 -----------------------------------------

def test_agent_output_models_construct():
    ev = S.ContributionEvidence(
        evidence_id="EV-001", project_id="P001", member_id="M_A", source_type="MEETING_UTTERANCE",
        source_id="UT-MT02-03", relation="SUPPORTS", excerpt="...", claim_id="CLM-01-01",
        contribution_type="IDEA", collected_at=T0)
    atomic = S.ContributionClaim(
        claim_id="CLM-06-01", project_id="P001", member_id="M_A", submitted_at=T0, source="SELF_REPORT_FORM",
        text="Timeline UI 아이디어를 제안했다", parent_claim_id="CLM-06", claimed_type="IDEA",
        status="CONFLICTING_EVIDENCE")
    dec = S.AgentDecision(
        decision_id="DEC-001", project_id="P001", decision_type="STAGNATION_ASSESSMENT", as_of=T0, created_at=T0,
        subject_member_id="M_C", task_id="T11", previous_stagnation_state="NORMAL",
        stagnation_state="STAGNATION_CANDIDATE", source_ids=["REV-055"], rationale="...", confidence="MEDIUM")
    mem = S.AgentMemory(
        memory_id="MEM-001", project_id="P001", created_at=T0, source_decision_ids=[dec.decision_id],
        decision_type="STAGNATION_ASSESSMENT", signal_pattern="Task 관련 리비전 7일 이상 없음",
        agent_judgment="후보로 올림", observed_outcome="FALSE_POSITIVE", lesson="로컬 작업 가능성을 먼저 확인")
    assert ev.source_type == S.EvidenceSourceType.MEETING_UTTERANCE and atomic.parent_claim_id == "CLM-06"
    assert mem.observed_outcome == S.DecisionOutcome.FALSE_POSITIVE


def test_agent_output_model_invariants():
    with pytest.raises(ValidationError):  # source_type과 source_id 종류 불일치
        S.ContributionEvidence(
            evidence_id="EV-001", project_id="P001", member_id="M_A", source_type="MESSAGE",
            source_id="REV-001", relation="SUPPORTS", excerpt="...", collected_at=T0)
    with pytest.raises(ValidationError):  # atomic claim인데 유형 없음
        S.ContributionClaim(
            claim_id="CLM-06-01", project_id="P001", member_id="M_A", submitted_at=T0, source="SELF_REPORT_FORM",
            text="...", parent_claim_id="CLM-06")
    with pytest.raises(ValidationError):  # 정체 판단인데 상태 없음
        S.AgentDecision(
            decision_id="DEC-001", project_id="P001", decision_type="STAGNATION_ASSESSMENT", as_of=T0,
            created_at=T0, subject_member_id="M_C", task_id="T11", rationale="...", confidence="LOW")
    with pytest.raises(ValidationError):  # 미래 데이터를 보고 과거에 판단할 수 없음
        S.AgentDecision(
            decision_id="DEC-001", project_id="P001", decision_type="FOLLOW_UP", as_of=T0,
            created_at=T0 - timedelta(hours=1), rationale="...", confidence="LOW")


def test_ground_truth_internal_rules(raw_ground_truth):
    judgment = raw_ground_truth["claim_judgments"][0]  # VERIFIED
    with pytest.raises(ValidationError):  # VERIFIED인데 반박 evidence
        G.GroundTruthClaimJudgment.model_validate(
            _mutated(judgment, expected_contradicting_evidence_ids=["UT-MT05-04"]))
    with pytest.raises(ValidationError):  # CONFLICTING인데 한쪽 evidence만
        G.GroundTruthClaimJudgment.model_validate(
            _mutated(judgment, expected_status="CONFLICTING_EVIDENCE"))
    non_block = raw_ground_truth["stagnations"][1]
    with pytest.raises(ValidationError):  # 실제 block이 아닌데 시작 시각
        G.GroundTruthStagnation.model_validate(
            _mutated(non_block, block_started_at="2026-09-15T00:00:00+09:00"))
    block = raw_ground_truth["stagnations"][2]
    with pytest.raises(ValidationError):  # RESOLVED인데 해결 시각 없음
        G.GroundTruthStagnation.model_validate(_mutated(block, resolved_at=None))
