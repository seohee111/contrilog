"""Anti-overfitting: Claim ID·Case 번호를 외운 구현이 아닌지 새 synthetic 기록으로 검증한다."""

import copy

import pytest

from contrilog.schemas import ClaimStatus as CS
from contrilog.schemas import ContributionType as CT
from tests.claim_fixtures import claim, load_raw, run_claims, summary, write_data_root
from tests.timeline_helpers import kst

AS_OF = kst(10, 16)
ORIGINAL = [f"CLM-0{i}" for i in range(1, 10)]


@pytest.fixture(scope="module")
def baseline():
    return run_claims(AS_OF, ORIGINAL)


def _status(run):
    return {r.predicted_contribution_type: r.predicted_status for r in run.atomic_results}


# ---------------------------------------------------------------- 1. Claim ID를 바꿔도 같은 판단
def test_renamed_claim_ids_give_identical_judgments(tmp_path, baseline):
    raw = load_raw()
    mapping = {old: f"CLM-{90 - i:02d}" for i, old in enumerate(ORIGINAL)}  # 순서도 뒤섞인 새 ID
    for c in raw["claims"]:
        c["claim_id"] = mapping[c["claim_id"]]
    raw["claims"].reverse()
    runs = run_claims(AS_OF, mapping.values(), write_data_root(tmp_path, raw))
    for old, new in mapping.items():
        assert summary(runs[new]) == summary(baseline[old]), old


# ---------------------------------------------------------------- 2. 같은 의미의 새 Claim (다른 표현)
PARAPHRASES = [
    ("M_D", "대시보드 첫 화면의 타임라인 뷰 아이디어를 제가 처음 제안했습니다.", {CT.IDEA: CS.VERIFIED}),
    ("M_A", "타임라인 화면 구현을 맡았습니다.", {CT.EXECUTION: CS.VERIFIED}),
    ("M_B", "발표를 문제, 접근, 데모, 한계 4단으로 나누는 구성은 제 아이디어였습니다.", {CT.IDEA: CS.INSUFFICIENT_EVIDENCE}),
    ("M_A", "전처리 코드의 라벨 기준일 이후 데이터가 피처에 들어가는 누수를 발견했습니다.", {CT.REVIEW: CS.VERIFIED}),
    ("M_C", "평가용 샘플 데이터셋 생성 스크립트를 만들었습니다.", {CT.EXECUTION: CS.INSUFFICIENT_EVIDENCE}),
    ("M_C", "GitHub 연동 API를 구현했습니다.", {CT.EXECUTION: CS.PENDING_VERIFICATION}),  # 진행 중, 완료 미확인
]


@pytest.mark.parametrize("member,text,expected", PARAPHRASES, ids=[p[1][:20] for p in PARAPHRASES])
def test_paraphrased_new_claims(tmp_path, member, text, expected):
    raw = load_raw()
    raw["claims"].append(claim("CLM-77", member, "2026-10-15T23:00:00+09:00", text))
    run = run_claims(AS_OF, ["CLM-77"], write_data_root(tmp_path, raw))["CLM-77"]
    assert _status(run) == expected, [(r.predicted_contribution_type, r.predicted_status, r.rationale)
                                      for r in run.atomic_results]


# ---------------------------------------------------------------- 3. 처음 보는 주제의 새 기록 + Claim
def _dark_mode(raw):
    raw["messages"] += [
        {"message_id": "MSG-901", "project_id": "P001", "channel": "#general", "channel_type": "CHANNEL",
         "sender_id": "M_C", "recipient_ids": [], "sent_at": "2026-10-03T10:00:00+09:00",
         "text": "로그인 화면에 다크 모드 토글을 넣으면 어떨까요? 야간 데모 때 눈이 덜 피곤할 것 같아요.",
         "reply_to_message_id": None},
        {"message_id": "MSG-902", "project_id": "P001", "channel": "#general", "channel_type": "CHANNEL",
         "sender_id": "M_A", "recipient_ids": [], "sent_at": "2026-10-03T10:20:00+09:00",
         "text": "좋네요, 다크 모드 색상표는 제가 정리해 볼게요.", "reply_to_message_id": "MSG-901"},
    ]
    raw["document_history"].append({
        "revision_id": "REV-901", "project_id": "P001", "document_id": "DOC-DESIGN", "document_title": "TeamLens 설계 문서",
        "document_type": "DESIGN_DOC", "author_id": "M_A", "edited_at": "2026-10-04T15:00:00+09:00",
        "change_summary": "4.4 다크 모드 색상표 추가",
        "diff_excerpt": "+ 4.4 다크 모드 (작성: 윤서진)\n+ 배경 #121212, 강조색 #4F8EF7, 로그인 화면 토글 위치",
        "chars_added": 640, "chars_deleted": 0})
    return raw


@pytest.mark.parametrize("member,text,expected", [
    ("M_C", "로그인 화면 다크 모드 토글 아이디어를 제안했습니다.", {CT.IDEA: CS.VERIFIED}),
    ("M_A", "다크 모드 아이디어를 제가 냈습니다.", {CT.IDEA: CS.CONFLICTING_EVIDENCE}),
    ("M_A", "다크 모드 색상표를 작성했습니다.", {CT.EXECUTION: CS.PENDING_VERIFICATION}),  # 완료 근거 없음
    ("M_A", "다크 모드 아이디어를 제안하고 색상표를 작성했습니다.",
     {CT.IDEA: CS.CONFLICTING_EVIDENCE, CT.EXECUTION: CS.PENDING_VERIFICATION}),
])
def test_unseen_topic_records(tmp_path, member, text, expected):
    raw = _dark_mode(load_raw())
    raw["claims"].append(claim("CLM-78", member, "2026-10-15T23:00:00+09:00", text))
    run = run_claims(AS_OF, ["CLM-78"], write_data_root(tmp_path, raw))["CLM-78"]
    assert _status(run) == expected
    idea = [r for r in run.atomic_results if r.predicted_contribution_type == CT.IDEA]
    if member == "M_A" and idea:
        assert "MSG-901" in idea[0].contradicting_source_ids


# ---------------------------------------------------------------- 4. 무관한 기록을 추가해도 판단 불변
def _noise(raw, n=40):
    topics = ["점심 메뉴는 학식으로 할까요?", "스터디룸 예약 연장했어요.", "주말에 비 온대요 우산 챙기세요.",
              "프린터 토너 교체 요청 넣었어요.", "도서관 휴관일 확인해 보세요."]
    members = ["M_A", "M_B", "M_C", "M_D"]
    for i in range(n):
        raw["messages"].append({
            "message_id": f"MSG-{500 + i}", "project_id": "P001", "channel": "#random", "channel_type": "CHANNEL",
            "sender_id": members[i % 4], "recipient_ids": [], "sent_at": f"2026-09-{10 + i % 18:02d}T12:{i:02d}:00+09:00",
            "text": topics[i % len(topics)], "reply_to_message_id": None})
        raw["document_history"].append({
            "revision_id": f"REV-{500 + i}", "project_id": "P001", "document_id": "DOC-MISC",
            "document_title": "개인 메모", "document_type": "REPORT", "author_id": members[(i + 1) % 4],
            "edited_at": f"2026-09-{10 + i % 18:02d}T15:{i:02d}:00+09:00", "change_summary": "메모 정리",
            "diff_excerpt": topics[(i + 2) % len(topics)], "chars_added": 50, "chars_deleted": 0})
    return raw


def test_unrelated_records_do_not_change_judgments(tmp_path, baseline):
    runs = run_claims(AS_OF, ORIGINAL, write_data_root(tmp_path, _noise(load_raw())))
    for cid in ORIGINAL:
        assert _status(runs[cid]) == _status(baseline[cid]), cid
        used = {e.source_id for e in runs[cid].evidence}
        assert not {s for s in used if s.startswith(("MSG-5", "REV-5"))}, cid


# ---------------------------------------------------------------- 5. 활동량만 늘려도 유형·판단 불변
def _inflate(raw, member, n=30):
    base = copy.deepcopy(raw)
    for i in range(n):
        base["document_history"].append({
            "revision_id": f"REV-{700 + i}", "project_id": "P001", "document_id": "DOC-MIDREPORT",
            "document_title": "중간보고서", "document_type": "REPORT", "author_id": member,
            "edited_at": f"2026-10-0{3 + i % 6}T0{i % 10}:30:00+09:00", "change_summary": "서식 미세 조정",
            "diff_excerpt": "줄간격·여백 재조정", "chars_added": 9000, "chars_deleted": 8800})
        base["document_history"].append({
            "revision_id": f"REV-{800 + i}", "project_id": "P001", "document_id": "DOC-SLIDES",
            "document_title": "최종 발표자료", "document_type": "SLIDES", "author_id": member,
            "edited_at": f"2026-10-0{3 + i % 6}T1{i % 10}:30:00+09:00",
            "change_summary": "4단 구성 슬라이드 다듬기", "diff_excerpt": "문제·접근·데모·한계 슬라이드 정렬",
            "chars_added": 7000, "chars_deleted": 6900})
        base["messages"].append({
            "message_id": f"MSG-{700 + i}", "project_id": "P001", "channel": "#docs", "channel_type": "CHANNEL",
            "sender_id": member, "recipient_ids": [], "sent_at": f"2026-10-0{3 + i % 6}T2{i % 4}:0{i % 10}:00+09:00",
            "text": "슬라이드랑 보고서 서식 계속 맞추는 중이에요.", "reply_to_message_id": None})
    return base


@pytest.mark.parametrize("member", ["M_B", "M_A"])
def test_activity_volume_does_not_change_type_or_judgment(tmp_path, baseline, member):
    runs = run_claims(AS_OF, ORIGINAL, write_data_root(tmp_path, _inflate(load_raw(), member)))
    for cid in ORIGINAL:
        before = {(r.predicted_contribution_type, r.predicted_status, r.confidence) for r in baseline[cid].atomic_results}
        after = {(r.predicted_contribution_type, r.predicted_status, r.confidence) for r in runs[cid].atomic_results}
        assert after == before, cid
    # 대량의 슬라이드 작업(실행)은 B의 '발표 구성 아이디어' 근거가 되지 않는다
    r = runs["CLM-02"].atomic_results[0]
    assert r.predicted_status == CS.INSUFFICIENT_EVIDENCE and not r.supporting_source_ids
