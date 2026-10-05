"""Interactive Verification: Observe → Reason → Act(CheckIn) → Observe(RPL) → Re-evaluate."""

from datetime import timedelta

import pytest

from contrilog.agent.claim_verification import ClaimVerificationAgent
from contrilog.agent.claim_verification.agent import MAX_CHECKINS_PER_ATOMIC
from contrilog.agent.claim_verification.protocols import PlannedCheckIn
from contrilog.data_access import load_project_input
from contrilog.schemas import ClaimStatus as CS
from contrilog.schemas import EvidenceRelation as R
from contrilog.schemas import InteractionStatus, VerificationGapKind
from contrilog.tools import ToolSession
from tests.claim_fixtures import claim, load_raw, load_simulation, write_data_root
from tests.interactive_fixtures import CLAIM_ID, SCENARIOS, run_scenario, trace_text

FULL = load_project_input("P001")
DMS = {m.message_id: m.text for m in FULL.messages if m.channel_type.value == "DIRECT_MESSAGE"}


def _checkins(session):
    return [c for c in session.call_log if c.tool_name == "CheckInTool"]


# ---------------------------------------------------------------- 1. PENDING → CheckIn → VERIFIED
@pytest.mark.parametrize("name,gap,role", [
    ("claim_api_fixed", VerificationGapKind.COMPLETION_UNCONFIRMED, "completion"),
    ("support_via_dm", VerificationGapKind.DIRECT_EVIDENCE_MISSING, "counterpart_confirmation"),
])
def test_pending_then_checkin_then_verified(tmp_path, name, gap, role):
    session, _, run = run_scenario(tmp_path, SCENARIOS[name])
    first, last = run.rounds[0], run.rounds[-1]
    assert first.phase == "INITIAL" and first.atomic_states[0].status == CS.PENDING_VERIFICATION
    assert [g.kind for g in first.gaps] == [gap] and first.gaps[0].resolvable and first.action_ids
    assert last.phase == "REEVALUATION" and last.atomic_states[0].status == CS.VERIFIED
    (interaction,) = run.interactions
    assert interaction.status == InteractionStatus.ANSWERED and last.new_reply_ids == interaction.reply_ids
    (rpl,) = interaction.reply_ids
    ev = next(e for e in run.evidence if e.source_id == rpl)
    assert ev.source_type.value == "INBOUND_REPLY" and ev.relation == R.SUPPORTS and ev.note.startswith(role)
    assert run.atomic_results[0].predicted_status == CS.VERIFIED
    # 같은 Judge: 공개 근거는 그대로이고 응답 하나가 더해져 판정이 바뀌었다
    before = {e.source_id for e in first.atomic_states[0].evidence}
    after = {e.source_id for e in last.atomic_states[0].evidence}
    assert after - before == {rpl}
    assert len(_checkins(session)) == 1


def test_decisions_chain_initial_checkin_final(tmp_path):
    _, _, run = run_scenario(tmp_path, SCENARIOS["claim_api_fixed"])
    kinds = [d.decision_type.value for d in run.decisions]
    assert kinds == ["CLAIM_VERIFICATION", "CHECKIN_REQUEST", "CLAIM_VERIFICATION"]
    initial, checkin, final = run.decisions
    assert initial.claim_status == CS.PENDING_VERIFICATION and initial.evidence_ids == []
    assert checkin.previous_decision_id == initial.decision_id and checkin.subject_member_id == "M_C"
    assert final.claim_status == CS.VERIFIED and final.previous_decision_id == initial.decision_id
    assert final.as_of > initial.as_of and set(final.evidence_ids) == {e.evidence_id for e in run.evidence}


# ---------------------------------------------------------------- 2. 응답이 부족하면 PENDING 유지
@pytest.mark.parametrize("name", ["github_blocked", "dataset_local", "claim_api_blocked"])
def test_reply_saying_not_done_keeps_pending(tmp_path, name):
    session, _, run = run_scenario(tmp_path, SCENARIOS[name])
    assert run.atomic_results[0].predicted_status == CS.PENDING_VERIFICATION
    (interaction,) = run.interactions
    (rpl,) = interaction.reply_ids
    ev = next(e for e in run.evidence if e.source_id == rpl)
    assert ev.relation == R.CONTEXT and ev.note.startswith("incomplete_report")
    last_gap = run.rounds[-1].gaps[0]
    assert not last_gap.resolvable and "반복 질문 안 함" in last_gap.unresolvable_reason
    assert len(_checkins(session)) == 1


def test_checkin_alone_does_not_verify(tmp_path):
    """응답이 있어도 내용이 주장을 지지하지 않으면 VERIFIED가 되지 않는다."""
    sim = load_simulation()
    for r in sim:
        r["reply_text"] = "지금 이동 중이라 이따가 다시 얘기해요."
    _, _, run = run_scenario(tmp_path, SCENARIOS["claim_api_fixed"], simulation=sim)
    assert run.interactions[0].status == InteractionStatus.ANSWERED
    assert run.atomic_results[0].predicted_status == CS.PENDING_VERIFICATION
    rpl = run.interactions[0].reply_ids[0]
    assert rpl in run.atomic_results[0].context_source_ids and rpl not in run.atomic_results[0].supporting_source_ids


def test_counterpart_denial_contradicts(tmp_path):
    sim = load_simulation()
    for r in sim:
        r["reply_text"] = "아니요, 도윤님은 이 문제에 관여하지 않았어요. 제가 혼자 해결했어요."
    _, _, run = run_scenario(tmp_path, SCENARIOS["support_via_dm"], simulation=sim)
    r = run.atomic_results[0]
    assert run.interactions[0].reply_ids[0] in r.contradicting_source_ids
    assert r.predicted_status == CS.CONFLICTING_EVIDENCE


def test_no_reply_closes_question_and_keeps_judgment(tmp_path):
    _, _, run = run_scenario(tmp_path, SCENARIOS["github_blocked"], simulation=[])
    assert run.interactions[0].status == InteractionStatus.NO_REPLY
    assert run.rounds[-1].phase == "FINAL" and "응답이 대기 시간 안에 오지 않음" in run.rounds[-1].gaps[0].unresolvable_reason
    assert run.atomic_results[0].predicted_status == CS.PENDING_VERIFICATION


# ---------------------------------------------------------------- 3. 적절한 사람에게 묻는다
def test_target_selection_follows_evidence_relations(tmp_path):
    _, _, run = run_scenario(tmp_path / "a", SCENARIOS["support_via_dm"])
    i = run.interactions[0]
    assert i.target_member_id == "M_C" and i.target_member_id != run.claimant_id  # 지원받은 사람
    assert "REV-058" in i.target_reason and i.task_id == "T11"  # 근거 문서가 속한 Task
    _, _, run = run_scenario(tmp_path / "b", SCENARIOS["dataset_local"])
    assert (run.interactions[0].target_member_id, run.interactions[0].task_id) == ("M_D", "T04")  # 담당자=주장자


def test_support_claim_without_named_counterpart_uses_evidence_actor(tmp_path):
    s = SCENARIOS["support_via_dm"]
    unnamed = type(s)(s.member_id, s.submitted_at, "Evidence 검색 기간 필터 오류 해결을 도왔습니다.", s.verify_at)
    _, _, run = run_scenario(tmp_path, unnamed)
    i = run.interactions[0]
    assert i.target_member_id == "M_C" and "REV-058의 주체" in i.target_reason


def test_no_question_when_only_own_records_and_no_counterpart(tmp_path):
    """간접 근거가 주장자 본인 기록뿐이면 주장자에게 다시 묻지 않는다 (답도 본인 보고일 뿐)."""
    raw = load_raw()
    raw["document_history"].append({
        "revision_id": "REV-910", "project_id": "P001", "document_id": "DOC-DESIGN",
        "document_title": "TeamLens 설계 문서", "document_type": "DESIGN_DOC", "author_id": "M_D",
        "edited_at": "2026-10-04T10:00:00+09:00", "change_summary": "4.5 음성 메모 첨부 기능 정리",
        "diff_excerpt": "+ 4.5 음성 메모 첨부 (작성: 이하은)", "chars_added": 300, "chars_deleted": 0})
    s = type(SCENARIOS["dataset_local"])("M_D", "2026-10-15T09:00:00+09:00",
                                          "음성 메모 첨부 기능 아이디어를 제안했습니다.", SCENARIOS["support_via_dm"].verify_at)
    session, _, run = run_scenario(tmp_path, s, raw=raw)
    assert run.atomic_results[0].predicted_status == CS.PENDING_VERIFICATION
    assert run.interactions == [] and not _checkins(session)
    assert "상대방을 기록에서 식별할 수 없음" in run.rounds[0].gaps[0].unresolvable_reason


# ---------------------------------------------------------------- 4. 시간 누출
def test_reply_is_not_evidence_before_it_arrives(tmp_path):
    s = SCENARIOS["claim_api_fixed"]
    raw = load_raw()
    raw["claims"].append(claim(CLAIM_ID, s.member_id, s.submitted_at, s.text))
    session = ToolSession("P001", s.verify_at, data_root=write_data_root(tmp_path, raw))
    agent = ClaimVerificationAgent(tools=session.tools)
    run = agent.verify_claim(claim_id=CLAIM_ID)
    assert run.awaiting_action_ids and not [e for e in run.evidence if e.source_type.value == "INBOUND_REPLY"]
    session.advance_to(s.verify_at + timedelta(minutes=19))  # 응답 지연(20분) 직전
    run = agent.continue_verification(run)
    assert len(run.rounds) == 1 and run.awaiting_action_ids
    assert run.atomic_results[0].predicted_status == CS.PENDING_VERIFICATION
    session.advance_to(s.verify_at + timedelta(minutes=20))
    run = agent.continue_verification(run)
    assert len(run.rounds) == 2 and run.atomic_results[0].predicted_status == CS.VERIFIED
    rpl = run.rounds[-1].new_reply_ids[0]
    assert run.rounds[-1].as_of >= run.interactions[0].sent_at + timedelta(minutes=20)
    assert all(e.source_id != rpl for e in run.rounds[0].atomic_states[0].evidence)


def test_every_round_uses_only_records_up_to_its_time(tmp_path):
    _, _, run = run_scenario(tmp_path, SCENARIOS["support_via_dm"])
    times = {**{r.revision_id: r.edited_at for r in FULL.document_history},
             **{m.message_id: m.sent_at for m in FULL.messages}, **{u.utterance_id: u.spoken_at for u in FULL.utterances}}
    for rd in run.rounds:
        for st in rd.atomic_states:
            for e in st.evidence:
                if e.source_id in times:
                    assert times[e.source_id] <= rd.as_of


# ---------------------------------------------------------------- 5. 개인 DM 미사용
def test_private_dm_never_used_even_when_the_act_happened_in_dm(tmp_path):
    session, _, run = run_scenario(tmp_path, SCENARIOS["support_via_dm"])
    text = trace_text(run)
    for dm_id, dm_text in DMS.items():
        assert f'"{dm_id}"' not in text and dm_text not in text
        assert dm_id not in {sid for s in run.search_steps for sid in s.returned_source_ids}
    for c in session.call_log:
        assert not set(c.returned_source_ids) & set(DMS)


# ---------------------------------------------------------------- 12. 반복 행동 방지
def test_no_repeated_checkins_across_polls_and_reruns(tmp_path):
    session, agent, run = run_scenario(tmp_path, SCENARIOS["github_blocked"])
    for _ in range(5):
        run = agent.continue_verification(run)
    again = agent.verify_claim(claim_id=CLAIM_ID)  # 같은 Agent가 같은 Claim을 다시 검증
    assert len(_checkins(session)) == 1
    assert [i.action_id for i in again.interactions] == [run.interactions[0].action_id]
    assert again.atomic_results[0].predicted_status == CS.PENDING_VERIFICATION
    assert agent.finalize(agent.finalize(run)).interactions == run.interactions


class _AlwaysAskAnotherTask:
    """종료 조건 검증용 planner: gap 근거의 Task부터 시작해 매번 다른 Task로 다시 묻겠다고 계획한다."""

    def plan(self, gap, atomic, ctx, already_asked):
        basis = [a.candidate.source_id for a in gap.basis if a.candidate.source_type.value == "TASK"]
        for t in sorted(ctx.tasks.values(), key=lambda t: (t.source_id not in basis, t.source_id)):
            key = (atomic.atomic_claim_id, gap.kind, atomic.claimant_id, t.source_id)
            if atomic.claimant_id in t.actor_ids and key not in already_asked:
                from contrilog.agent.claim_verification.interactive import INTENT_FOR_GAP
                return PlannedCheckIn(atomic.claimant_id, t.source_id, "진행 상황을 알려 주세요.", "test",
                                      INTENT_FOR_GAP[gap.kind])
        from contrilog.agent.claim_verification.protocols import NoAction
        return NoAction("없음")


def test_checkin_budget_per_atomic_claim(tmp_path):
    """planner가 계속 묻자고 해도, 응답이 계속 와도 atomic claim당 질문 수 상한에서 멈춘다."""
    sim = load_simulation()
    for i, task in enumerate(["T01", "T03", "T06"]):  # 주장자가 담당한 다른 Task에도 응답이 오는 환경
        sim.append({"reply_id": f"SIM-9{i}0", "project_id": "P001", "trigger": "CHECKIN", "responder_id": "M_C",
                    "about_member_id": "M_C", "task_id": task, "available_from": "2026-09-01T00:00:00+09:00",
                    "available_until": "2026-10-16T23:59:00+09:00", "reply_text": "아직 진행 중이에요.",
                    "reply_delay_minutes": 10, "question_intent": "COMPLETION_CONFIRMATION"})
    session, _, run = run_scenario(tmp_path, SCENARIOS["claim_api_blocked"], simulation=sim,
                                   agent_kwargs={"interactive_planner": _AlwaysAskAnotherTask()})
    assert len(_checkins(session)) == MAX_CHECKINS_PER_ATOMIC == 2
    assert any("상한" in (g.unresolvable_reason or "") for rd in run.rounds for g in rd.gaps)


def test_non_interactive_mode_takes_no_action(tmp_path):
    session, _, run = run_scenario(tmp_path, SCENARIOS["claim_api_fixed"], agent_kwargs={"interactive": False})
    assert not _checkins(session) and run.interactions == []
    assert run.atomic_results[0].predicted_status == CS.PENDING_VERIFICATION
