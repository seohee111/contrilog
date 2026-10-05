"""Claim Agent 테스트용 데이터 디렉터리 생성.

원본 data/input/P001(과 확인 질문 응답용 data/simulation/P001)을 tmp 디렉터리에 복사한 뒤
테스트가 기록을 추가·변경한다. Ground Truth는 복사하지 않는다 (Agent 실행에 필요 없음).
원본 데이터와 Ground Truth는 바꾸지 않는다.
"""

import json
from datetime import datetime
from pathlib import Path

from contrilog.agent.claim_verification import ClaimVerificationAgent
from contrilog.data_access.paths import DATA_ROOT, INPUT_FILES
from contrilog.tools import ToolSession


def load_raw() -> dict:
    base = DATA_ROOT / "input" / "P001"
    return {k: json.loads((base / f).read_text(encoding="utf-8")) for k, f in INPUT_FILES.items()}


def load_simulation() -> list:
    return json.loads((DATA_ROOT / "simulation" / "P001" / "simulated_replies.json").read_text(encoding="utf-8"))


def write_data_root(root: Path, raw: dict, simulation: list | None = None) -> Path:
    base = root / "input" / "P001"
    base.mkdir(parents=True, exist_ok=True)
    for k, f in INPUT_FILES.items():
        (base / f).write_text(json.dumps(raw[k], ensure_ascii=False, indent=2), encoding="utf-8")
    sim = root / "simulation" / "P001"
    sim.mkdir(parents=True, exist_ok=True)
    (sim / "simulated_replies.json").write_text(
        json.dumps(load_simulation() if simulation is None else simulation, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return root


def claim(claim_id: str, member_id: str, submitted_at: str, text: str) -> dict:
    return {"claim_id": claim_id, "project_id": "P001", "member_id": member_id, "submitted_at": submitted_at,
            "source": "SELF_REPORT_FORM", "source_message_id": None, "text": text, "parent_claim_id": None,
            "claimed_type": None, "status": "PENDING_VERIFICATION"}


def run_claims(as_of: datetime, claim_ids, data_root: Path | None = None) -> dict:
    session = ToolSession("P001", as_of, data_root=data_root)
    agent = ClaimVerificationAgent(tools=session.tools)
    return {cid: agent.verify_claim(claim_id=cid) for cid in claim_ids}


def summary(run) -> list[tuple]:
    """Claim ID와 무관한 판단 요약 (유형, 상태, 확신도, 근거 ID 집합)."""
    return sorted((r.predicted_contribution_type.value, r.predicted_status.value, r.confidence.value,
                   tuple(sorted(r.supporting_source_ids)), tuple(sorted(r.contradicting_source_ids)))
                  for r in run.atomic_results)
