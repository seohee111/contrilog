"""Interactive Verification 테스트 시나리오 (테스트 전용; Agent runtime은 이 파일을 모른다).

각 시나리오는 '언제, 누가, 어떤 Claim을 제출했는가'만 정한다. 질문 대상·질문·판정은 Agent가 결정한다.
"""

import json
from dataclasses import dataclass
from datetime import datetime

from contrilog.agent.claim_verification import ClaimVerificationAgent
from contrilog.runtime import run_interactive_verification
from contrilog.tools import ToolSession
from tests.claim_fixtures import claim, load_raw, load_simulation, write_data_root
from tests.timeline_helpers import kst


@dataclass(frozen=True)
class Scenario:
    member_id: str
    submitted_at: str
    text: str
    verify_at: datetime


SCENARIOS = {
    # Case03 상황: 연동 작업 중 403으로 막힘
    "github_blocked": Scenario("M_C", "2026-09-17T10:00:00+09:00", "GitHub 연동 API를 구현했습니다.", kst(9, 18, 10)),
    # Case04 상황: 로컬에서 작업 중, 업로드 전
    "dataset_local": Scenario("M_D", "2026-09-20T10:00:00+09:00",
                              "평가용 샘플 데이터셋과 생성 스크립트를 만들었습니다.", kst(9, 21, 12)),
    # Case10 상황: Evidence 검색 0건으로 막힘
    "claim_api_blocked": Scenario("M_C", "2026-10-09T09:00:00+09:00",
                                  "Claim 검증 API와 Evidence 검색 모듈을 구현했습니다.", kst(10, 9, 12)),
    # Case10 상황: 수정 직후, Task 보드는 아직 진행 중
    "claim_api_fixed": Scenario("M_C", "2026-10-09T22:50:00+09:00",
                                "Claim 검증 API와 Evidence 검색 모듈을 구현했습니다.", kst(10, 9, 23)),
    # Case10 상황: B의 지원 (실제 지원은 개인 DM에서 일어남)
    "support_via_dm": Scenario("M_B", "2026-10-15T23:00:00+09:00",
                               "지후님의 Evidence 검색 기간 필터 오류 해결을 도왔습니다.", kst(10, 16)),
}
CLAIM_ID = "CLM-50"


def run_scenario(tmp_path, scenario: Scenario, *, raw=None, simulation=None, claim_id=CLAIM_ID, agent_kwargs=None):
    raw = raw or load_raw()
    raw["claims"].append(claim(claim_id, scenario.member_id, scenario.submitted_at, scenario.text))
    root = write_data_root(tmp_path, raw, simulation)
    session = ToolSession("P001", scenario.verify_at, data_root=root)
    agent = ClaimVerificationAgent(tools=session.tools, **(agent_kwargs or {}))
    run = run_interactive_verification(session, agent, claim_id)
    return session, agent, run


def behavior(run) -> dict:
    """Claim ID·실행 ID와 무관한 행동·판정 요약."""
    return {
        "rounds": [(r.phase, [(s.status.value, sorted(e.source_id for e in s.evidence)) for s in r.atomic_states],
                    [(g.kind.value, g.resolvable) for g in r.gaps]) for r in run.rounds],
        "interactions": [(i.target_member_id, i.task_id, i.gap_kind.value, i.status.value) for i in run.interactions],
        "final": [(r.predicted_contribution_type.value, r.predicted_status.value, r.confidence.value)
                  for r in run.atomic_results],
    }


def trace_text(run) -> str:
    return json.dumps(run.model_dump(mode="json"), ensure_ascii=False)


__all__ = ["CLAIM_ID", "SCENARIOS", "Scenario", "behavior", "load_raw", "load_simulation", "run_scenario",
           "trace_text"]
