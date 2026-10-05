"""Agent 접근 정책 (MVP 개인정보 원칙).

"ContriLog는 프로젝트 참여자가 공유 프로젝트 공간에 제공한 기록만 분석하며 개인 DM은 열람하지 않는다."

- 원본 데이터(data/input)와 시간 필터(build_snapshot)는 그대로 둔다.
- Agent에게 주는 snapshot에만 이 정책을 적용한다. 그래서 검색 Tool뿐 아니라
  ProjectStatusTool의 '마지막 메시지' 같은 파생 정보에도 DM이 나타나지 않는다.
- 공유 채널 메시지(ChannelType.CHANNEL)만 허용한다. 현재 데이터에는 DM을 프로젝트에
  '명시적으로 공유'했다는 기록 필드가 없으므로 모든 DM을 차단한다.
- 허용된 메시지가 차단된 메시지에 답장한 경우, 답장 대상 ID를 지워 DM의 존재를 드러내지 않는다.
"""

from contrilog.schemas import ChannelType, Message, ProjectSnapshot


def is_agent_accessible_message(message: Message) -> bool:
    return message.channel_type == ChannelType.CHANNEL


def apply_access_policy(snapshot: ProjectSnapshot) -> ProjectSnapshot:
    allowed = [m for m in snapshot.messages if is_agent_accessible_message(m)]
    allowed_ids = {m.message_id for m in allowed}
    messages = [
        m if m.reply_to_message_id is None or m.reply_to_message_id in allowed_ids
        else m.model_copy(update={"reply_to_message_id": None})
        for m in allowed
    ]
    return snapshot.model_copy(update={"messages": messages})
