"""특정 시각(as_of)에 Agent가 알 수 있었던 프로젝트 상태."""

from pydantic import AwareDatetime

from .input_bundle import ProjectInput


class ProjectSnapshot(ProjectInput):
    """ProjectInput과 같은 구조에 관찰 시각을 더한 것.

    - 모든 기록의 시각은 as_of 이하다.
    - Task의 status / status_history는 as_of 시점으로 재구성되어 있다.
    """

    as_of: AwareDatetime
