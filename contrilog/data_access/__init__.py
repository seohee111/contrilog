"""Agent 입력 데이터 접근 계층.

이 패키지는 data/input/ 아래만 읽는다. 평가용 정답 데이터의 경로를 알지 못하며,
평가 패키지(contrilog.evaluation)를 import 하지 않는다.
"""

from .input_loader import load_project_input
from .snapshot import build_snapshot, get_project_snapshot

__all__ = ["build_snapshot", "get_project_snapshot", "load_project_input"]
