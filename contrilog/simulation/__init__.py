"""시뮬레이션 환경 (팀원 응답 재생).

Agent가 check-in이나 지원 요청을 했을 때만 tool을 통해 응답을 돌려주기 위한 데이터.
Agent 입력 로더는 이 데이터를 읽지 않는다.
"""

from .loader import load_simulated_replies

__all__ = ["load_simulated_replies"]
