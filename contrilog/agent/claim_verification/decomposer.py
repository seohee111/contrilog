"""DeterministicClaimDecomposer — Claim 문장을 (주장자, 기여 유형, 대상) 단위 atomic claim으로 나눈다.

규칙:
1. 연결 어미(-하고, -했고, -냈고, -해서, -하며 …) 뒤에서 절을 나눈다.
2. 각 절의 행위 단서로 기여 유형을 정한다 (예: '아이디어/제안' → IDEA, '구현/만들' → EXECUTION).
3. 유형 단서가 없는 절은 이웃 절의 대상 설명으로 합친다. 단 '반영되었다/수정되었다' 같은 결과 서술은
   expects_outcome 표시로 남긴다.
4. 같은 유형의 절은 하나의 atomic claim으로 합친다.
5. 문장 앞 'X는/은' 주제어는 모든 atomic claim의 대상에 포함한다.
"""

import re

from contrilog.schemas import ContributionType as CT

from . import text as T
from .protocols import AtomicDraft, MemberRef, SubmittedClaim

_CONNECTIVE = re.compile(r"((?:했으며|하며|했고|하고|냈고|내고|해서|하여|되었고|됐고),?\s+)")
_TOPIC = re.compile(r"^\s*((?:\S+\s){0,2}\S+?)(?:은|는)\s")


def split_clauses(sentence: str) -> list[str]:
    parts = _CONNECTIVE.split(sentence)
    clauses, buf = [], ""
    for i, p in enumerate(parts):
        buf += p
        if i % 2 == 1:  # 연결 어미까지 포함해 한 절로 끝낸다
            clauses.append(buf.strip())
            buf = ""
    if buf.strip():
        clauses.append(buf.strip())
    return clauses


def classify_clause(clause: str) -> list[CT]:
    types = []
    if T.has_any(clause, T.IDEA_CUES):
        types.append(CT.IDEA)
    if T.has_any(clause, T.REVIEW_FIND_CUES) and (T.has_any(clause, T.PROBLEM_CUES) or T.has_any(clause, ("검토", "리뷰"))):
        types.append(CT.REVIEW)
    if T.has_any(clause, T.SUPPORT_CUES):
        types.append(CT.SUPPORT)
    if T.has_any(clause, T.COORDINATION_VERBS) and T.has_any(clause, T.COORDINATION_OBJECTS):
        types.append(CT.COORDINATION)
    if T.has_any(clause, T.EXECUTION_CUES):
        types.append(CT.EXECUTION)
    return types


def topic_tokens(text: str, members: dict[str, MemberRef]) -> list[str]:
    names = {m.given_name for m in members.values()} | {m.name for m in members.values()}
    return T.content_terms(text, names)


def mentioned_members(text: str, members: dict[str, MemberRef], exclude: str) -> tuple[str, ...]:
    found = []
    for name in T.MENTION_PATTERN.findall(text):
        for m in members.values():
            if name in (m.given_name, m.name) and m.member_id != exclude and m.member_id not in found:
                found.append(m.member_id)
    return tuple(found)


class DeterministicClaimDecomposer:
    def decompose(self, claim: SubmittedClaim, members: dict[str, MemberRef]) -> list[AtomicDraft]:
        drafts: list[AtomicDraft] = []
        for sentence in [s for s in re.split(r"(?<=[.!?])\s+", claim.text.strip()) if s]:
            drafts.extend(self._sentence(sentence, claim, members))
        merged: dict[CT, AtomicDraft] = {}
        for d in drafts:  # 문장이 여러 개여도 같은 유형은 하나로
            if d.contribution_type in merged:
                prev = merged[d.contribution_type]
                d = AtomicDraft(d.contribution_type, f"{prev.text} {d.text}",
                                tuple(dict.fromkeys(prev.topic_terms + d.topic_terms)),
                                tuple(dict.fromkeys(prev.mentioned_member_ids + d.mentioned_member_ids)),
                                prev.expects_outcome or d.expects_outcome)
            merged[d.contribution_type] = d
        return list(merged.values())

    def _sentence(self, sentence: str, claim: SubmittedClaim, members) -> list[AtomicDraft]:
        clauses = split_clauses(sentence)
        typed = [(c, classify_clause(c)) for c in clauses]
        topic_match = _TOPIC.match(sentence)
        sentence_topic = topic_tokens(topic_match.group(1), members) if topic_match else []
        all_terms = topic_tokens(sentence, members)
        outcome = any(not types and T.has_any(c, T.OUTCOME_CUES) for c, types in typed)

        groups: dict[CT, list[str]] = {}
        pending_untyped: list[str] = []
        last_type = None
        for clause, types in typed:
            if not types:
                if last_type is None:
                    pending_untyped.append(clause)  # 다음 유형 절의 대상 설명
                else:
                    groups[last_type].append(clause)
                continue
            for t in types:
                groups.setdefault(t, []).extend(pending_untyped + [clause])
            pending_untyped = []
            last_type = types[-1]

        drafts = []
        for t, parts in groups.items():
            text = " ".join(parts)
            own = topic_tokens(text, members)
            terms = tuple(dict.fromkeys(sentence_topic + (own or all_terms)))
            drafts.append(AtomicDraft(
                contribution_type=t, text=text, topic_terms=terms,
                mentioned_member_ids=mentioned_members(text, members, claim.member_id),
                expects_outcome=outcome))
        return drafts
