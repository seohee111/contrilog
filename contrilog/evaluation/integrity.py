"""Ground Truth가 입력 데이터의 실제 객체를 가리키는지, 내부적으로 일관적인지 검사한다."""

from collections import Counter
from datetime import datetime, time, timedelta, timezone

from contrilog.data_access.access_policy import is_agent_accessible_message
from contrilog.schemas import ProjectInput
from contrilog.schemas.ground_truth import ALLOWED_REPLY_SEMANTICS, GroundTruthBundle

KST = timezone(timedelta(hours=9))


def check_ground_truth_integrity(gt: GroundTruthBundle, data: ProjectInput, replies=None) -> list[str]:
    """replies(시뮬레이션 응답 목록)를 주면 응답 의미 정답(reply_labels)과의 대응도 검사한다."""
    errors: list[str] = []
    pid = data.project.project_id
    members = {m.member_id for m in data.members}
    tasks = {t.task_id: t for t in data.tasks}
    claims = {c.claim_id: c for c in data.claims}
    sources = data.source_record_ids()
    # Agent 접근 정책(contrilog.data_access.access_policy)으로 볼 수 없는 기록
    private = {m.message_id for m in data.messages if not is_agent_accessible_message(m)}
    period_start = datetime.combine(data.project.start_date, time.min, KST)
    period_end = datetime.combine(data.project.end_date, time.max, KST)

    if gt.project_id != pid:
        errors.append(f"ground truth project {gt.project_id} != input project {pid}")

    for name, ids in [
        ("case", [c.case_id for c in gt.cases]),
        ("contribution", [c.gt_contribution_id for c in gt.contributions]),
        ("claim judgment", [c.gt_claim_id for c in gt.claim_judgments]),
        ("stagnation", [s.gt_stagnation_id for s in gt.stagnations]),
    ]:
        for dup, n in Counter(ids).items():
            if n > 1:
                errors.append(f"duplicate {name} id: {dup}")

    contribs = {c.gt_contribution_id: c for c in gt.contributions}
    judgments = {c.gt_claim_id: c for c in gt.claim_judgments}
    stagnations = {s.gt_stagnation_id: s for s in gt.stagnations}

    # Case <-> 항목 상호 참조
    listed: dict[str, str] = {}
    for case in gt.cases:
        for ids, table in [
            (case.contribution_ids, contribs),
            (case.claim_judgment_ids, judgments),
            (case.stagnation_ids, stagnations),
        ]:
            for i in ids:
                if i not in table:
                    errors.append(f"{case.case_id}: unknown item {i}")
                elif table[i].case_id != case.case_id:
                    errors.append(f"{case.case_id}: item {i} belongs to {table[i].case_id}")
                listed[i] = case.case_id
    for i in [*contribs, *judgments, *stagnations]:
        if i not in listed:
            errors.append(f"{i}: not listed in any case")

    def evidence(label: str, ids):
        for e in ids:
            if e not in sources:
                errors.append(f"{label}: expected evidence {e} does not exist in input")
            elif e in private:
                errors.append(f"{label}: expected evidence {e} is not accessible to the agent (private DM)")

    def inaccessible(label: str, ids):
        for e in ids:
            if e not in private:
                errors.append(f"{label}: inaccessible source {e} is not a private record")

    def interactive(label: str, items):
        for x in items:
            if x.task_id not in tasks:
                errors.append(f"{label}: unknown task {x.task_id}")
                continue
            for mid in (x.responder_id, x.about_member_id):
                if mid is not None and mid not in members:
                    errors.append(f"{label}: unknown member {mid}")
            assignees = tasks[x.task_id].assignee_ids
            if x.kind.value == "CHECKIN_REPLY" and x.responder_id not in assignees:
                errors.append(f"{label}: check-in responder {x.responder_id} is not assigned to {x.task_id}")
            if x.kind.value == "SUPPORT_REPLY" and x.about_member_id not in assignees:
                errors.append(f"{label}: supported member {x.about_member_id} is not assigned to {x.task_id}")

    for c in gt.contributions:
        if c.project_id != pid:
            errors.append(f"{c.gt_contribution_id}: wrong project")
        if c.member_id not in members:
            errors.append(f"{c.gt_contribution_id}: unknown member {c.member_id}")
        for t in c.related_task_ids:
            if t not in tasks:
                errors.append(f"{c.gt_contribution_id}: unknown task {t}")
        if c.related_claim_id is not None:
            claim = claims.get(c.related_claim_id)
            if claim is None:
                errors.append(f"{c.gt_contribution_id}: unknown claim {c.related_claim_id}")
            elif claim.member_id != c.member_id:
                errors.append(f"{c.gt_contribution_id}: claim {claim.claim_id} was made by another member")
        evidence(c.gt_contribution_id, c.expected_evidence_ids)
        inaccessible(c.gt_contribution_id, c.inaccessible_source_ids)
        interactive(c.gt_contribution_id, c.expected_interactive_evidence)

    for j in gt.claim_judgments:
        claim = claims.get(j.claim_id)
        if claim is None:
            errors.append(f"{j.gt_claim_id}: unknown claim {j.claim_id}")
        elif claim.member_id != j.claimant_id:
            errors.append(f"{j.gt_claim_id}: claimant {j.claimant_id} != claim author {claim.member_id}")
        if j.related_gt_contribution_id is not None and j.related_gt_contribution_id not in contribs:
            errors.append(f"{j.gt_claim_id}: unknown contribution {j.related_gt_contribution_id}")
        evidence(j.gt_claim_id, j.expected_evidence_ids)
    for claim_id in claims:
        if not any(j.claim_id == claim_id for j in gt.claim_judgments):
            errors.append(f"{claim_id}: input claim has no ground truth judgment")

    # CHECKIN 기대값은 질문 의도와 기대 응답 의미를 가져야 한다 (구체화된 interactive 기대값)
    for owner, items in [(c.gt_contribution_id, c.expected_interactive_evidence) for c in gt.contributions] + \
                        [(s.gt_stagnation_id, s.expected_interactive_evidence) for s in gt.stagnations]:
        for x in items:
            if x.kind.value == "CHECKIN_REPLY" and (x.question_intent is None or x.expected_semantic_outcome is None):
                errors.append(f"{owner}: CHECKIN_REPLY expectation needs question_intent and expected_semantic_outcome")

    case_ids = {c.case_id for c in gt.cases}
    probe_ids = [sc.probe_claim.claim_id for sc in gt.interactive_scenarios]
    for dup, n in Counter(probe_ids).items():
        if n > 1:
            errors.append(f"duplicate probe claim id {dup}")
    for dup, n in Counter(sc.scenario_id for sc in gt.interactive_scenarios).items():
        if n > 1:
            errors.append(f"duplicate scenario id {dup}")
    for sc in gt.interactive_scenarios:
        label = sc.scenario_id
        if sc.case_id not in case_ids:
            errors.append(f"{label}: unknown case {sc.case_id}")
        if sc.probe_claim.claim_id in claims:
            errors.append(f"{label}: probe claim id {sc.probe_claim.claim_id} collides with an input claim")
        if sc.probe_claim.member_id not in members:
            errors.append(f"{label}: unknown member {sc.probe_claim.member_id}")
        for ts in (sc.probe_claim.submitted_at, sc.verify_at):
            if not (period_start <= ts <= period_end):
                errors.append(f"{label}: timestamp {ts.isoformat()} outside project period")
        interactive(label, sc.expected_interactions)

    for s in gt.stagnations:
        if s.project_id != pid:
            errors.append(f"{s.gt_stagnation_id}: wrong project")
        task = tasks.get(s.task_id)
        if task is None:
            errors.append(f"{s.gt_stagnation_id}: unknown task {s.task_id}")
        elif s.member_id not in task.assignee_ids:
            errors.append(f"{s.gt_stagnation_id}: {s.member_id} is not assigned to {s.task_id}")
        for ts in (s.block_started_at, s.resolved_at, s.evaluation_as_of):
            if ts is not None and not (period_start <= ts <= period_end):
                errors.append(f"{s.gt_stagnation_id}: timestamp {ts.isoformat()} outside project period")
        iv = s.expected_intervention
        if iv is not None and iv.supporter_member_id is not None:
            if iv.supporter_member_id not in members:
                errors.append(f"{s.gt_stagnation_id}: unknown supporter {iv.supporter_member_id}")
            if iv.supporter_member_id == s.member_id:
                errors.append(f"{s.gt_stagnation_id}: supporter must differ from blocked member")
        evidence(s.gt_stagnation_id, s.expected_evidence_ids)
        inaccessible(s.gt_stagnation_id, s.inaccessible_source_ids)
        interactive(s.gt_stagnation_id, s.expected_interactive_evidence)

    for dup, n in Counter(x.reply_id for x in gt.reply_labels).items():
        if n > 1:
            errors.append(f"duplicate reply label {dup}")
    for x in gt.reply_labels:
        if x.project_id != pid:
            errors.append(f"reply label {x.reply_id}: wrong project")
    if replies is not None:
        by_id = {r.reply_id: r for r in replies}
        labeled = {x.reply_id for x in gt.reply_labels}
        for rid in sorted(set(by_id) - labeled):
            errors.append(f"simulated reply {rid} has no reply label")
        for x in gt.reply_labels:
            r = by_id.get(x.reply_id)
            if r is None:
                errors.append(f"reply label {x.reply_id}: unknown simulated reply")
                continue
            kind = r.question_intent if r.question_intent is not None else r.trigger
            if x.expected_semantic not in ALLOWED_REPLY_SEMANTICS[kind]:
                errors.append(f"reply label {x.reply_id}: {x.expected_semantic.value} is not a possible answer "
                              f"to {kind.value}")

    return errors
