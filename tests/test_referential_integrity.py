"""입력/시뮬레이션 데이터의 참조 ID가 실제 객체를 가리키는지 검사."""

from contrilog.data_access.integrity import check_input_integrity
from contrilog.simulation.loader import check_simulation_integrity


def test_input_integrity(project_input):
    assert check_input_integrity(project_input) == []


def test_simulation_integrity(replies, project_input):
    assert check_simulation_integrity(replies, project_input) == []


def test_reply_to_and_dm_references(project_input):
    ids = {m.message_id for m in project_input.messages}
    members = {m.member_id for m in project_input.members}
    for m in project_input.messages:
        assert m.reply_to_message_id is None or m.reply_to_message_id in ids
        assert set(m.recipient_ids) <= members


def test_task_and_document_references(project_input):
    docs = {r.document_id for r in project_input.document_history}
    tasks = {t.task_id for t in project_input.tasks}
    for t in project_input.tasks:
        assert set(t.related_document_ids) <= docs
        assert set(t.depends_on_task_ids) <= tasks


def test_integrity_checker_detects_broken_references(project_input):
    broken = project_input.model_copy(deep=True)
    broken.utterances[0].speaker_id = "M_Z"
    broken.messages[4].reply_to_message_id = "MSG-999"
    broken.tasks[0].related_document_ids.append("DOC-MISSING")
    broken.tasks[1].depends_on_task_ids.append("T99")
    broken.claims[0].member_id = "M_Y"
    broken.document_history[0].author_id = "M_X"
    errors = check_input_integrity(broken)
    for needle in ["M_Z", "MSG-999", "DOC-MISSING", "T99", "M_Y", "M_X"]:
        assert any(needle in e for e in errors), needle


def test_integrity_checker_rejects_judged_input_claims(project_input):
    leaked = project_input.model_copy(deep=True)
    leaked.claims[0].status = "VERIFIED"
    leaked.claims[1].claimed_type = "IDEA"
    errors = check_input_integrity(leaked)
    assert any("PENDING_VERIFICATION" in e for e in errors)
    assert any("must be raw" in e for e in errors)
