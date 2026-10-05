"""Project / Member.

Member에는 역할(role) 외에 성격·근태·성실성 등 사람을 프로파일링하는 필드를 두지 않는다.
"""

from datetime import date

from .base import MemberId, MilestoneId, ProjectId, StrictModel


class Milestone(StrictModel):
    milestone_id: MilestoneId
    name: str
    due_date: date


class Project(StrictModel):
    project_id: ProjectId
    name: str
    organization: str  # 프로젝트를 수행하는 조직·팀 (예: 사내 TF)
    description: str
    start_date: date
    end_date: date
    member_ids: list[MemberId]
    milestones: list[Milestone]


class Member(StrictModel):
    member_id: MemberId
    project_id: ProjectId
    label: str  # 문서·테스트에서 부르는 짧은 이름 (A/B/C/D)
    name: str  # 회의록·메시지 본문에서 불리는 이름
    role: str  # 팀 내 담당 영역 (평가가 아니라 업무 분담 정보)
