"""결정적 텍스트 처리: 토큰화, 용어 그룹(동의어·영한 표기), 단서 어휘, 용어 통계.

여기의 어휘는 특정 Claim이나 Case가 아니라 '팀 프로젝트 기록에서 행위를 나타내는 일반 표현'이다.
LLM 기반 구현으로 교체할 때 이 모듈이 가장 먼저 대체될 대상이다.
"""

import math
import re
from dataclasses import dataclass, field

# 영한 표기·동의어 그룹 (일반 소프트웨어 프로젝트 용어)
GLOSSARY: list[frozenset[str]] = [frozenset(g) for g in [
    {"타임라인", "timeline"},
    {"ui", "화면", "뷰", "view"},
    {"대시보드", "dashboard"},
    {"일정", "일정표", "schedule"},
    {"발표", "발표자료", "슬라이드", "slides", "presentation"},
    {"보고서", "report"},
    {"데이터셋", "dataset"},
    {"전처리", "preprocess"},
    {"스크립트", "script"},
    {"배포", "deploy"},
    {"근거", "evidence"},
    {"에이전트", "agent"},
    {"테스트", "test"},
    {"설계", "design"},
    {"알림", "alert"},
    {"회의", "meeting"},
    {"검색", "search"},
]]

STOPWORDS = {
    "제가", "저는", "저도", "직접", "및", "등", "관련", "사이", "중", "위해", "통해", "대한", "것", "수", "모두",
    "함께", "같이", "부분", "작업", "맡았습니다", "했습니다", "합니다", "있습니다", "되었습니다", "그리고",
}

# 행위 단서 (Claim 문장 분류용)
IDEA_CUES = ("아이디어", "제안", "고안", "착안", "기획했")
EXECUTION_CUES = ("구현", "만들", "작성했", "개발했", "맡았", "맡아", "제작", "구축했", "정리했", "수행했", "담당")
REVIEW_FIND_CUES = ("발견", "찾아내", "찾았", "지적", "검토", "리뷰")
PROBLEM_CUES = ("누수", "오류", "에러", "버그", "결함", "문제점", "취약", "실수", "비정상", "확인 필요", "너무 높", "잘못")
SUPPORT_CUES = ("도왔", "도와", "지원했", "지원해", "도움")
COORDINATION_VERBS = ("조정", "조율", "재배치", "재분배", "앞당", "미뤘", "미루", "옮기", "옮겼")
COORDINATION_OBJECTS = ("일정", "순서", "역할", "분담", "우선순위", "마감")
OUTCOME_CUES = ("반영되", "반영됐", "수정되", "수정됐", "채택되", "적용되", "적용됐")

# Claim 문장에서 토픽 용어로 쓰지 않을 행위 단어(어간)
ACTION_STEMS = {
    "아이디어", "제안", "제시", "냈고", "구현", "만들", "작성", "개발", "맡았습니다", "발견", "발견해", "발견해서",
    "조정", "도왔습니다", "도왔", "도와", "반영", "수정", "고안", "착안", "기획", "담당", "정리했습니다", "구현했습니다",
}

# 기록(발언·메시지·리비전) 쪽 단서
PROPOSAL_CUES = ("제안", "어떨까요", "좋겠어요", "좋겠습니다", "하면 어때", "하는 게 어때", "어때요")
AGREEMENT_CUES = ("좋네요", "좋아요", "맞네요", "감사", "됐어요", "고칠게요", "수정했어요", "확인했어요", "좋습니다")
COMPLETION_CUES = ("완료", "올렸어요", "다 됐", "통과", "제출했", "끝냈", "업로드", "고쳤어요", "정상으로", "정상 동작",
                   "잘 돌아")
# 완료 단서가 있어도 아직 끝나지 않았음을 뜻하는 표현 (부정·예정·진행·막힘)
INCOMPLETE_CUES = ("아직", "예정", "거의", "중이에요", "중입니다", "할게요", "올릴게요", "진행할 수가 없", "막혀",
                   "못 하", "못 찾", "안 올렸", "안 됐", "기다리는")
# 상대방이 주장자의 도움·관여를 진술하는 표현 / 부인하는 표현
COLLABORATION_CUES = ("같이", "함께", "도와", "도움", "덕분", "리뷰해", "봐 주셔서", "봐주셔서")
DENIAL_CUES = ("아니요", "아닙니다", "관여하지", "혼자 해결", "혼자 했")
PROBLEM_REPORT_CUES = ("에러", "오류", "안 돼", "못 찾", "막혀", "0건", "실패", "안 나와", "이상하")
COORDINATION_CUE_GROUPS = (("일정", "schedule"), ("순서",), ("조정", "조율"), ("앞당",), ("미루", "옮기", "옮겼"))
ATTRIBUTION_PATTERN = re.compile(r"([가-힣]{1,3})님\s*(?:의\s*)?(?:아이디어|제안|의견)")
MENTION_PATTERN = re.compile(r"([가-힣]{1,3})님")

_SUFFIXES = sorted([
    "되었습니다", "했습니다", "었습니다", "았습니다", "습니다", "했고", "하고", "하는", "자는", "으로", "에서", "에게",
    "까지", "부터", "이나", "로", "을", "를", "이", "가", "은", "는", "의", "에", "와", "과", "도", "만", "께",
], key=len, reverse=True)
_COUNTER = re.compile(r"^\d+(월|일|시|분|개|명|인|회|차|건|행|절)$")


def has_any(text: str, cues) -> bool:
    return any(c in text for c in cues)


def completion_state(text: str) -> str | None:
    """'complete' / 'incomplete' / None. 미완료 표현이 있으면 완료 단서보다 우선한다."""
    if has_any(text, INCOMPLETE_CUES):
        return "incomplete"
    if has_any(text, COMPLETION_CUES):
        return "complete"
    return None


def normalize(text: str) -> str:
    """매칭용 정규화: camelCase 분리, 구분자 공백화, 소문자."""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"[_/.\-·()\[\]'\"‘’“”→,:;#+=<>{}|]", " ", text)
    return text.casefold()


def stem(token: str) -> str:
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    out = []
    for raw in re.findall(r"[a-z][a-z0-9]*|[가-힣]+|\d+[가-힣]+", normalize(text)):
        if _COUNTER.match(raw):
            continue
        token = raw if raw[0].isascii() else stem(raw)
        if len(token) >= 2 and token not in STOPWORDS and raw not in STOPWORDS:
            out.append(token)
    return out


@dataclass(frozen=True)
class TermGroup:
    forms: frozenset[str]

    @property
    def label(self) -> str:
        return sorted(self.forms, key=lambda f: (not f.isascii(), f))[0]

    def matches(self, normalized_text: str) -> bool:
        for f in self.forms:
            if f.isascii():
                if re.search(rf"\b{re.escape(f)}\b", normalized_text):
                    return True
            # 한국어는 단어 시작에서만 일치 (조사·어미가 뒤에 붙는 것은 허용, '발표자료' 속 '자료'는 불일치)
            elif re.search(rf"(?<![가-힣]){re.escape(f)}", normalized_text):
                return True
        return False


def term_group(token: str) -> TermGroup:
    for g in GLOSSARY:
        if token in g:
            return TermGroup(g)
    return TermGroup(frozenset({token}))


def term_groups(tokens) -> list[TermGroup]:
    seen, out = set(), []
    for t in tokens:
        g = term_group(t)
        if g.forms not in seen:
            seen.add(g.forms)
            out.append(g)
    return out


def content_terms(text: str, names: set[str]) -> list[str]:
    """행위 단어·사람 이름을 뺀 대상(주제) 용어."""
    return [t for t in tokenize(text) if t not in ACTION_STEMS and not t.endswith("님") and t not in names]


# 관련성 규칙: 주제어 가중치의 절반 이상이 일치하거나, 드문 주제어가 2개 이상 일치하면 관련 기록이다.
COVERAGE_MIN = 0.5
DISTINCTIVE_MIN = 2
DISTINCTIVE_DF_RATIO = 0.10  # 관찰 가능한 기록의 10% 이하에만 나오는 용어 = 드문 용어


@dataclass
class TermStatistics:
    """as_of 시점 관찰 가능한 기록 전체에서 계산한 용어 문서 빈도(df).

    흔한 용어(예: '문서', '정체')보다 드문 용어(예: '후보', '4단')에 더 큰 비중을 둔다.
    계산 대상은 '기록과 Claim 주제의 관련성'이지 사람이 아니다.
    """

    texts: list[str]
    _df: dict = field(default_factory=dict)

    def df(self, group: TermGroup) -> int:
        if group.forms not in self._df:
            self._df[group.forms] = sum(1 for t in self.texts if group.matches(t))
        return self._df[group.forms]

    def weight(self, group: TermGroup) -> float:
        df = self.df(group)
        return 0.0 if df == 0 else math.log((len(self.texts) + 1) / (df + 1)) + 0.1

    def distinctive(self, group: TermGroup) -> bool:
        return 0 < self.df(group) <= DISTINCTIVE_DF_RATIO * len(self.texts)

    def coverage(self, groups: list[TermGroup], normalized_text: str) -> float:
        total = sum(self.weight(g) for g in groups)
        if total == 0:
            return 0.0
        return sum(self.weight(g) for g in groups if g.matches(normalized_text)) / total

    def is_relevant(self, groups: list[TermGroup], normalized_text: str) -> bool:
        if self.coverage(groups, normalized_text) >= COVERAGE_MIN:
            return True
        hits = sum(1 for g in groups if self.distinctive(g) and g.matches(normalized_text))
        return hits >= DISTINCTIVE_MIN
