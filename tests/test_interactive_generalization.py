"""Interactive Verification 일반화: ID·이름·Case 번호·noise에 의존하지 않고, 새 시나리오에서도 루프가 돈다."""

import json
import shutil

import pytest

from contrilog.data_access.paths import DATA_ROOT
from contrilog.schemas import ClaimStatus as CS
from contrilog.schemas import InteractionStatus
from tests.claim_fixtures import load_raw, load_simulation
from tests.interactive_fixtures import SCENARIOS, Scenario, behavior, run_scenario
from tests.test_claim_agent_generalization import _noise

LOOP_SCENARIOS = ["support_via_dm", "claim_api_fixed", "dataset_local", "github_blocked"]


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    return {n: run_scenario(tmp_path_factory.mktemp(n), SCENARIOS[n]) for n in LOOP_SCENARIOS}


# ---------------------------------------------------------------- 7. Case ID 변경 / Ground Truth 유무
def test_case_ids_and_ground_truth_presence_do_not_matter(tmp_path, baseline):
    """같은 데이터 루트에 Case ID를 바꾼 Ground Truth를 두든, 아예 두지 않든 행동이 같다."""
    for name in LOOP_SCENARIOS:
        root = tmp_path / name
        gt = root / "ground_truth" / "P001"
        gt.mkdir(parents=True)
        for f in (DATA_ROOT / "ground_truth" / "P001").glob("*.json"):
            (gt / f.name).write_text(f.read_text(encoding="utf-8").replace("CASE", "SCN"), encoding="utf-8")
        _, _, run = run_scenario(root, SCENARIOS[name])
        assert behavior(run) == behavior(baseline[name][2]), name
        shutil.rmtree(gt)


# ---------------------------------------------------------------- 8. Claim ID 변경
@pytest.mark.parametrize("name", LOOP_SCENARIOS)
def test_claim_id_change(tmp_path, baseline, name):
    _, _, run = run_scenario(tmp_path, SCENARIOS[name], claim_id="CLM-83")
    assert behavior(run) == behavior(baseline[name][2])
    assert [i.question for i in run.interactions] == [i.question for i in baseline[name][2].interactions]


# ---------------------------------------------------------------- 9. 팀원 이름 변경
NEW_NAMES = {"윤서진": "강가람", "한도윤": "문나래", "박지후": "서다온", "이하은": "조라온",
             "서진": "가람", "도윤": "나래", "지후": "다온", "하은": "라온"}


def _rename(text: str) -> str:
    for old, new in NEW_NAMES.items():  # 전체 이름을 먼저 바꾼 뒤 이름(성 제외)을 바꾼다
        text = text.replace(old, new)
    return text


@pytest.mark.parametrize("name", ["support_via_dm", "claim_api_fixed"])
def test_member_name_change(tmp_path, baseline, name):
    raw = json.loads(_rename(json.dumps(load_raw(), ensure_ascii=False)))
    sim = json.loads(_rename(json.dumps(load_simulation(), ensure_ascii=False)))
    s = SCENARIOS[name]
    renamed = Scenario(s.member_id, s.submitted_at, _rename(s.text), s.verify_at)
    _, _, run = run_scenario(tmp_path, renamed, raw=raw, simulation=sim)
    assert behavior(run) == behavior(baseline[name][2])
    assert [i.question for i in run.interactions] == [_rename(i.question) for i in baseline[name][2].interactions]


# ---------------------------------------------------------------- 10. 새로운 시나리오
def _new_execution_world():
    raw = load_raw()
    raw["tasks"].append({
        "task_id": "T21", "project_id": "P001", "title": "다크 모드 적용", "description": "로그인 화면 다크 모드 색상표 작성과 적용",
        "created_by": "M_B", "created_at": "2026-10-03T11:00:00+09:00", "assignee_ids": ["M_A"], "due_date": "2026-10-08",
        "status": "IN_PROGRESS", "due_date_history": [], "related_document_ids": ["DOC-THEME"], "depends_on_task_ids": [],
        "status_history": [
            {"changed_at": "2026-10-03T11:00:00+09:00", "changed_by": "M_B", "from_status": None, "to_status": "TODO", "note": None},
            {"changed_at": "2026-10-04T09:00:00+09:00", "changed_by": "M_A", "from_status": "TODO", "to_status": "IN_PROGRESS", "note": None}]})
    raw["document_history"].append({
        "revision_id": "REV-920", "project_id": "P001", "document_id": "DOC-THEME", "document_title": "web/src/theme/dark.ts",
        "document_type": "CODE", "author_id": "M_A", "edited_at": "2026-10-05T16:00:00+09:00",
        "change_summary": "다크 모드 색상표 토큰 정의", "diff_excerpt": "+ export const dark = { bg: '#121212', accent: '#4F8EF7' }",
        "chars_added": 820, "chars_deleted": 0})
    sim = load_simulation() + [{
        "reply_id": "SIM-920", "project_id": "P001", "trigger": "CHECKIN", "responder_id": "M_A", "about_member_id": "M_A",
        "task_id": "T21", "available_from": "2026-10-06T00:00:00+09:00", "available_until": "2026-10-08T00:00:00+09:00",
        "reply_text": "색상표 작성 끝냈고 로그인 화면에도 적용 완료했어요.", "reply_delay_minutes": 30,
        "question_intent": "COMPLETION_CONFIRMATION"}]
    return raw, sim


def test_new_execution_scenario_loop(tmp_path):
    raw, sim = _new_execution_world()
    s = Scenario("M_A", "2026-10-06T09:00:00+09:00", "다크 모드 색상표를 작성했습니다.", SCENARIOS["support_via_dm"].verify_at.replace(month=10, day=6, hour=10))
    session, _, run = run_scenario(tmp_path, s, raw=raw, simulation=sim)
    assert run.rounds[0].atomic_states[0].status == CS.PENDING_VERIFICATION
    (i,) = run.interactions
    assert (i.target_member_id, i.task_id, i.status) == ("M_A", "T21", InteractionStatus.ANSWERED)
    assert run.atomic_results[0].predicted_status == CS.VERIFIED


def _new_support_world():
    raw = load_raw()
    raw["document_history"].append({
        "revision_id": "REV-930", "project_id": "P001", "document_id": "DOC-TIMELINE",
        "document_title": "web/src/views/TimelineView.tsx", "document_type": "CODE", "author_id": "M_A",
        "edited_at": "2026-10-03T21:00:00+09:00", "change_summary": "필터 초기화 시 빈 화면 버그 수정 (하은님 도움)",
        "diff_excerpt": "- setRange(null)\n+ setRange(defaultRange)", "chars_added": 120, "chars_deleted": 80})
    sim = load_simulation() + [{
        "reply_id": "SIM-930", "project_id": "P001", "trigger": "CHECKIN", "responder_id": "M_A", "about_member_id": "M_A",
        "task_id": "T05", "available_from": "2026-10-04T00:00:00+09:00", "available_until": "2026-10-10T00:00:00+09:00",
        "reply_text": "네, 하은님이 같이 재현해 주셔서 원인을 찾았어요.", "reply_delay_minutes": 15,
        "question_intent": "COUNTERPART_CONFIRMATION"}]
    return raw, sim


def test_new_support_scenario_loop(tmp_path):
    raw, sim = _new_support_world()
    s = Scenario("M_D", "2026-10-04T09:00:00+09:00", "서진님의 타임라인 필터 빈 화면 버그 수정을 도왔습니다.",
                 SCENARIOS["support_via_dm"].verify_at.replace(month=10, day=4, hour=10))
    session, _, run = run_scenario(tmp_path, s, raw=raw, simulation=sim)
    first = run.rounds[0]
    assert first.atomic_states[0].status == CS.PENDING_VERIFICATION and first.gaps[0].kind.value == "DIRECT_EVIDENCE_MISSING"
    (i,) = run.interactions
    assert i.target_member_id == "M_A" and i.target_member_id != "M_D" and i.task_id == "T05"
    assert run.atomic_results[0].predicted_status == CS.VERIFIED


# ---------------------------------------------------------------- 11. 무관한 기록 추가
@pytest.mark.parametrize("name", LOOP_SCENARIOS)
def test_noise_does_not_change_target_or_judgment(tmp_path, baseline, name):
    _, _, run = run_scenario(tmp_path, SCENARIOS[name], raw=_noise(load_raw()))
    base = baseline[name][2]
    assert [(i.target_member_id, i.task_id, i.question) for i in run.interactions] == \
           [(i.target_member_id, i.task_id, i.question) for i in base.interactions]
    assert behavior(run)["final"] == behavior(base)["final"]
    assert [r.atomic_states[0].status for r in run.rounds] == [r.atomic_states[0].status for r in base.rounds]
