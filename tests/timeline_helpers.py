"""테스트용 시각 헬퍼. 기대값은 snapshot 코드를 거치지 않고 원본 JSON에서 직접 계산한다."""

import json
from datetime import datetime, timedelta, timezone

from contrilog.data_access.paths import INPUT_FILES, input_dir

KST = timezone(timedelta(hours=9))
SEC = timedelta(seconds=1)


def kst(month, day, hour=0, minute=0, second=0):
    return datetime(2026, month, day, hour, minute, second, tzinfo=KST)


def raw(project_id="P001"):
    base = input_dir(project_id)
    return {k: json.loads((base / f).read_text(encoding="utf-8")) for k, f in INPUT_FILES.items()}


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def expected_visible_ids(as_of: datetime, data=None) -> dict[str, set[str]]:
    """원본 JSON만으로 계산한 'as_of에 보여야 하는 ID' 집합."""
    d = data or raw()
    ended = {m["meeting_id"] for m in d["meetings"] if ts(m["ended_at"]) <= as_of}
    return {
        "meetings": ended,
        "utterances": {u["utterance_id"] for u in d["utterances"] if u["meeting_id"] in ended},
        "document_history": {r["revision_id"] for r in d["document_history"] if ts(r["edited_at"]) <= as_of},
        "tasks": {t["task_id"] for t in d["tasks"] if ts(t["created_at"]) <= as_of},
        "messages": {m["message_id"] for m in d["messages"] if ts(m["sent_at"]) <= as_of},
        "claims": {c["claim_id"] for c in d["claims"] if ts(c["submitted_at"]) <= as_of},
    }


def expected_agent_message_ids(as_of: datetime, data=None) -> set[str]:
    """Agent 접근 정책(공유 채널만, 개인 DM 제외)을 원본 JSON으로 직접 적용한 기대 집합."""
    d = data or raw()
    return {m["message_id"] for m in d["messages"] if ts(m["sent_at"]) <= as_of and m["channel_type"] == "CHANNEL"}


def expected_task_status(task_id: str, as_of: datetime, data=None):
    d = data or raw()
    task = next(t for t in d["tasks"] if t["task_id"] == task_id)
    hist = [h for h in task["status_history"] if ts(h["changed_at"]) <= as_of]
    return hist[-1]["to_status"] if hist else None


# 프로젝트 전체를 12시간 간격으로 훑는 관찰 시각
GRID = [kst(9, 1) + timedelta(hours=12 * i) for i in range(0, 2 * 46)]
