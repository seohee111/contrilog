"""Agent 판단 로직 (다음 단계에서 구현).

규칙:
- 입력은 contrilog.data_access(= data/input)와 contrilog.tools를 통해서만 얻는다.
- contrilog.evaluation / contrilog.schemas.ground_truth 를 import 하지 않는다.
- 판단 결과는 contrilog.schemas.AgentDecision / ContributionEvidence로 남긴다.
- 사람의 기여를 점수화하거나 순위를 매기지 않는다.
"""
