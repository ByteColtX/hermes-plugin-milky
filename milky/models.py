"""Milky v1.3 协议 DTO。

这些模型只描述协议边界，不执行网络请求、策略判断或 Hermes 业务操作。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

JsonObject = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Segment:
    """保存一个已解析消息 segment 的安全原始内容。"""

    kind: str
    raw: JsonObject
    extras: JsonObject = field(default_factory=dict)

    @property
    def type(self) -> str:
        """返回 Milky segment 类型名。"""

        return self.kind


@dataclass(frozen=True, slots=True)
class TextSegment(Segment):
    """文本 segment。"""

    text: str = ""


@dataclass(frozen=True, slots=True)
class MentionSegment(Segment):
    """直接提及用户的 segment。"""

    user_id: int = 0
    name: str | None = None


@dataclass(frozen=True, slots=True)
class MentionAllSegment(Segment):
    """全体提及 segment。"""


@dataclass(frozen=True, slots=True)
class FaceSegment(Segment):
    """表情 segment。"""

    face_id: str | None = None
    is_large: bool | None = None


@dataclass(frozen=True, slots=True)
class ReplySegment(Segment):
    """带有内嵌原消息信息的引用 segment。"""

    message_seq: int | None = None
    sender_id: int | None = None
    sender_name: str | None = None
    time: int | None = None
    segments: tuple[Segment, ...] = ()


@dataclass(frozen=True, slots=True)
class ImageSegment(Segment):
    """图片资源引用 segment。"""

    resource_id: str | None = None
    temp_url: str | None = None
    width: int | None = None
    height: int | None = None
    summary: str | None = None
    sub_type: str | None = None


@dataclass(frozen=True, slots=True)
class RecordSegment(Segment):
    """语音资源引用 segment。"""

    resource_id: str | None = None
    temp_url: str | None = None
    duration: int | None = None


@dataclass(frozen=True, slots=True)
class VideoSegment(Segment):
    """视频资源引用 segment。"""

    resource_id: str | None = None
    temp_url: str | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None


@dataclass(frozen=True, slots=True)
class FileSegment(Segment):
    """入站文件远端引用 segment。"""

    file_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    file_hash: str | None = None


@dataclass(frozen=True, slots=True)
class ForwardSegment(Segment):
    """尚未展开的转发消息引用 segment。"""

    forward_id: str | None = None
    title: str | None = None
    preview: tuple[str, ...] = ()
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class MarketFaceSegment(Segment):
    """市场表情 segment。"""

    emoji_package_id: int | None = None
    emoji_id: str | None = None
    key: str | None = None
    summary: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class LightAppSegment(Segment):
    """小程序 segment。"""

    app_name: str | None = None
    json_payload: str | None = None


@dataclass(frozen=True, slots=True)
class XmlSegment(Segment):
    """XML segment。"""

    service_id: int | None = None
    xml_payload: str | None = None


@dataclass(frozen=True, slots=True)
class MarkdownSegment(Segment):
    """Markdown segment。"""

    content: str = ""


@dataclass(frozen=True, slots=True)
class UnknownSegment(Segment):
    """未知 segment，只保留安全 raw，不提供文本语义。"""

    data: Any = field(default_factory=dict)


SegmentValue = (
    TextSegment
    | MentionSegment
    | MentionAllSegment
    | FaceSegment
    | ReplySegment
    | ImageSegment
    | RecordSegment
    | VideoSegment
    | FileSegment
    | ForwardSegment
    | MarketFaceSegment
    | LightAppSegment
    | XmlSegment
    | MarkdownSegment
    | UnknownSegment
)


@dataclass(frozen=True, slots=True)
class FriendEntity:
    """好友实体。"""

    user_id: int
    nickname: str
    sex: str | None = None
    qid: str | None = None
    remark: str | None = None
    category: JsonObject | None = None
    extras: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GroupEntity:
    """群实体。"""

    group_id: int
    group_name: str | None = None
    member_count: int | None = None
    max_member_count: int | None = None
    remark: str | None = None
    created_time: int | None = None
    description: str | None = None
    question: str | None = None
    announcement: str | None = None
    extras: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GroupMemberEntity:
    """群成员实体，包括可省略或为空的禁言截止时间。"""

    user_id: int
    group_id: int
    nickname: str
    card: str | None = None
    sex: str | None = None
    title: str | None = None
    level: int | None = None
    role: str | None = None
    join_time: int | None = None
    last_sent_time: int | None = None
    shut_up_end_time: int | None = None
    extras: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IncomingForwardedMessage:
    """get_forwarded_messages 返回的单条转发消息。"""

    message_seq: int
    sender_name: str
    avatar_url: str
    time: int
    segments: tuple[Segment, ...]
    extras: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OutgoingForwardedMessage:
    """出站转发消息的协议 DTO，不包含文件 message segment。"""

    user_id: int
    sender_name: str
    segments: tuple[JsonObject, ...]
    time: int | None = None
    extras: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    """message_receive 的场景化消息 DTO。"""

    message_scene: str
    peer_id: int
    message_seq: int | None
    sender_id: int
    time: int
    segments: tuple[Segment, ...]
    friend: FriendEntity | None = None
    group: GroupEntity | None = None
    group_member: GroupMemberEntity | None = None
    raw: JsonObject = field(default_factory=dict)
    extras: JsonObject = field(default_factory=dict)
    self_id: int | None = None


@dataclass(frozen=True, slots=True)
class Event:
    """Milky 事件外层 DTO。"""

    event_type: str
    time: int
    self_id: int
    data: JsonObject
    raw: JsonObject = field(default_factory=dict)
    extras: JsonObject = field(default_factory=dict)
    outer_event_type: str | None = None

    @property
    def classification(self) -> str:
        """返回普通消息或观察事件的边界分类。"""

        return "accepted" if self.event_type == "message_receive" else "observe_only"


@dataclass(frozen=True, slots=True)
class MilkyEnvelope:
    """Milky Action 的通用响应 envelope。"""

    status: str
    retcode: int
    data: JsonObject | None
    message: str | None = None
    wording: str | None = None
    extras: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LoginInfo:
    """登录信息 Action 的最小结果。"""

    uin: int
    nickname: str
    extras: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GroupList:
    """群列表 Action 的最小结果。"""

    groups: tuple[GroupEntity, ...]
    extras: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GroupMemberList:
    """群成员列表 Action 的最小结果。"""

    members: tuple[GroupMemberEntity, ...]
    extras: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GroupMemberInfo:
    """群成员查询 Action 的最小结果。"""

    member: GroupMemberEntity
    extras: JsonObject = field(default_factory=dict)
