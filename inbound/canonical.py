"""将 Milky message_receive 建立为可审计的 canonical record。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from milky.models import (
    Event,
    FileSegment,
    ForwardSegment,
    ImageSegment,
    IncomingMessage,
    MarkdownSegment,
    MentionAllSegment,
    MentionSegment,
    RecordSegment,
    ReplySegment,
    Segment,
    TextSegment,
    UnknownSegment,
    VideoSegment,
)
from milky.parser import ParseError, parse_event, parse_incoming_message
from session.identity import (
    CanonicalError,
    make_dedup_key,
    normalize_chat_key,
)

JsonObject = Mapping[str, Any]
_SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "password",
    "token",
}


@dataclass(frozen=True, slots=True)
class MediaReference:
    """保存待后续 resolver 使用的协议资源引用。"""

    kind: str
    resource_id: str | None = None
    temp_url: str | None = None
    file_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    file_hash: str | None = None
    forward_id: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalMessage:
    """保存一条可进入后续本地策略边界的规范化消息。"""

    platform: str
    self_id: int
    scene: str
    chat_key: str
    peer_id: int
    sender_id: int
    message_id: str | None
    timestamp: int
    sender_name: str
    segments: tuple[Segment, ...]
    body: str
    mention_kind: str
    quote_message_id: str | None
    media_references: tuple[MediaReference, ...]
    raw: JsonObject
    metadata: JsonObject
    diagnostics: tuple[str, ...] = ()

    @property
    def time(self) -> int:
        """返回兼容协议命名的 Unix 秒时间戳。"""

        return self.timestamp

    @property
    def dedup_key(self) -> str | None:
        """返回稳定消息的去重 key；无序号时显式返回空值。"""

        if self.message_id is None:
            return None
        return make_dedup_key(self.self_id, self.chat_key, self.message_id)

    @property
    def has_quote(self) -> bool:
        """返回消息是否带有引用目标。"""

        return self.quote_message_id is not None

    @property
    def media_refs(self) -> tuple[MediaReference, ...]:
        """返回待补全媒体引用的兼容名称。"""

        return self.media_references


@dataclass(frozen=True, slots=True)
class CanonicalResult:
    """表示 canonical 接受、临时忽略或安全拒绝的结果。"""

    classification: str
    value: CanonicalMessage | None
    reason: str | None = None


def canonicalize_event(
    event: Event | object,
    *,
    expected_self_id: int | None = None,
) -> CanonicalResult:
    """解析并规范化一个事件，不为 temp 或系统事件建立 canonical。"""

    try:
        parsed_event = event if isinstance(event, Event) else parse_event(event)
        if parsed_event.event_type != "message_receive":
            return CanonicalResult("observe_only", None, "event is not message_receive")
        parsed = parse_incoming_message(parsed_event)
    except ParseError as error:
        return CanonicalResult(error.classification, None, error.reason)

    if parsed.classification == "ignored_temp":
        return CanonicalResult("ignored_temp", None, parsed.reason)
    if parsed.value is None:
        return CanonicalResult("malformed", None, "message parser returned no value")

    try:
        value = canonicalize_message(parsed.value, expected_self_id=expected_self_id)
    except CanonicalError as error:
        return CanonicalResult(error.classification, None, error.reason)
    if parsed.reason is not None:
        value = _with_diagnostics(value, (parsed.reason,))
    return CanonicalResult("accepted", value)


def canonicalize_message(
    message: IncomingMessage,
    *,
    expected_self_id: int | None = None,
) -> CanonicalMessage:
    """将已通过 Milky parser 的消息转换为 canonical record。"""

    if not isinstance(message, IncomingMessage):
        raise CanonicalError("message must be an IncomingMessage")
    if message.message_scene == "temp":
        raise CanonicalError("temporary message scene", "ignored_temp")
    if message.self_id is None:
        raise CanonicalError("self_id is required")
    _require_nonnegative_int(message.self_id, "self_id")
    _require_nonnegative_int(message.peer_id, "peer_id")
    _require_nonnegative_int(message.sender_id, "sender_id")
    _require_nonnegative_int(message.time, "time")
    if message.message_seq is not None:
        _require_nonnegative_int(message.message_seq, "message_seq")
    if expected_self_id is not None and message.self_id != expected_self_id:
        raise CanonicalError("event self_id disagrees with configured self_id")
    if message.message_scene not in {"friend", "group"}:
        raise CanonicalError("message scene is not friend or group")

    chat_key = normalize_chat_key(message.message_scene, message.peer_id)
    _validate_scene_entities(message)
    sender_name = _sender_name(message)
    message_id = None if message.message_seq is None else str(message.message_seq)
    diagnostics = ("no_stable_message_id",) if message_id is None else ()
    raw = _freeze_safe(message.raw)
    metadata = _freeze_safe(
        {
            "scene": message.message_scene,
            "chat_key": chat_key,
            "diagnostics": diagnostics,
        }
    )
    return CanonicalMessage(
        platform="milky",
        self_id=message.self_id,
        scene=message.message_scene,
        chat_key=chat_key,
        peer_id=message.peer_id,
        sender_id=message.sender_id,
        message_id=message_id,
        timestamp=message.time,
        sender_name=sender_name,
        segments=message.segments,
        body=_body_from_segments(message.segments),
        mention_kind=_mention_kind(message.segments, message.self_id),
        quote_message_id=_quote_message_id(message.segments),
        media_references=_media_references(message.segments),
        raw=raw,
        metadata=metadata,
        diagnostics=diagnostics,
    )


def build_canonical(
    message: IncomingMessage,
    *,
    expected_self_id: int | None = None,
) -> CanonicalMessage:
    """提供描述性名称的 canonical 构造入口。"""

    return canonicalize_message(message, expected_self_id=expected_self_id)


def _validate_scene_entities(message: IncomingMessage) -> None:
    if message.message_scene == "friend":
        if message.sender_id != message.peer_id:
            raise CanonicalError("friend sender_id disagrees with peer_id")
        if message.friend is not None and message.friend.user_id != message.peer_id:
            raise CanonicalError("friend.user_id disagrees with peer_id")
        return

    if message.group is not None and message.group.group_id != message.peer_id:
        raise CanonicalError("group.group_id disagrees with peer_id")
    if message.group_member is not None:
        if message.group_member.group_id != message.peer_id:
            raise CanonicalError("group_member.group_id disagrees with peer_id")
        if message.group_member.user_id != message.sender_id:
            raise CanonicalError("group_member.user_id disagrees with sender_id")


def _sender_name(message: IncomingMessage) -> str:
    if message.message_scene == "group":
        member = message.group_member
        if member is not None:
            candidate = _non_blank(member.card)
            if candidate is not None:
                return candidate
            candidate = _non_blank(member.nickname)
            if candidate is not None:
                return candidate
        return str(message.sender_id)

    friend = message.friend
    candidate = _non_blank(friend.nickname if friend is not None else None)
    return candidate if candidate is not None else str(message.sender_id)


def _non_blank(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _require_nonnegative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CanonicalError(f"{field_name} must be a non-negative integer")


def _mention_kind(segments: Sequence[Segment], self_id: int) -> str:
    if any(
        isinstance(segment, MentionSegment) and segment.user_id == self_id for segment in segments
    ):
        return "self"
    if any(isinstance(segment, MentionAllSegment) for segment in segments):
        return "all"
    return "none"


def _quote_message_id(segments: Sequence[Segment]) -> str | None:
    for segment in segments:
        if isinstance(segment, ReplySegment) and segment.message_seq is not None:
            return str(segment.message_seq)
    return None


def _body_from_segments(segments: Sequence[Segment]) -> str:
    parts: list[str] = []
    for segment in segments:
        if isinstance(segment, TextSegment):
            parts.append(segment.text)
        elif isinstance(segment, MarkdownSegment):
            parts.append(segment.content)
        elif isinstance(segment, MentionSegment):
            parts.append(f"@{segment.name or segment.user_id}")
        elif isinstance(segment, MentionAllSegment):
            parts.append("@全体")
        elif isinstance(segment, ReplySegment):
            parts.append("[引用]")
        elif isinstance(segment, UnknownSegment):
            continue
        else:
            parts.append(_structured_placeholder(segment))
    return "".join(parts)


def _structured_placeholder(segment: Segment) -> str:
    placeholders = {
        "face": "[表情]",
        "image": "[图片]",
        "record": "[语音]",
        "video": "[视频]",
        "file": "[文件]",
        "forward": "[转发]",
        "market_face": "[市场表情]",
        "light_app": "[小程序]",
        "xml": "[XML]",
    }
    return placeholders.get(segment.kind, "")


def _media_references(segments: Sequence[Segment]) -> tuple[MediaReference, ...]:
    references: list[MediaReference] = []
    for segment in segments:
        if isinstance(segment, ImageSegment):
            references.append(
                MediaReference("image", resource_id=segment.resource_id, temp_url=segment.temp_url)
            )
        elif isinstance(segment, RecordSegment):
            references.append(
                MediaReference("record", resource_id=segment.resource_id, temp_url=segment.temp_url)
            )
        elif isinstance(segment, VideoSegment):
            references.append(
                MediaReference("video", resource_id=segment.resource_id, temp_url=segment.temp_url)
            )
        elif isinstance(segment, FileSegment):
            references.append(
                MediaReference(
                    "file",
                    file_id=segment.file_id,
                    file_name=segment.file_name,
                    file_size=segment.file_size,
                    file_hash=segment.file_hash,
                )
            )
        elif isinstance(segment, ForwardSegment):
            references.append(MediaReference("forward", forward_id=segment.forward_id))
    return tuple(references)


def _with_diagnostics(message: CanonicalMessage, diagnostics: tuple[str, ...]) -> CanonicalMessage:
    merged = tuple(dict.fromkeys((*message.diagnostics, *diagnostics)))
    metadata = _freeze_safe(
        {
            **dict(message.metadata),
            "diagnostics": merged,
        }
    )
    return CanonicalMessage(
        platform=message.platform,
        self_id=message.self_id,
        scene=message.scene,
        chat_key=message.chat_key,
        peer_id=message.peer_id,
        sender_id=message.sender_id,
        message_id=message.message_id,
        timestamp=message.timestamp,
        sender_name=message.sender_name,
        segments=message.segments,
        body=message.body,
        mention_kind=message.mention_kind,
        quote_message_id=message.quote_message_id,
        media_references=message.media_references,
        raw=message.raw,
        metadata=metadata,
        diagnostics=merged,
    )


def _freeze_safe(value: object) -> Any:
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.casefold() in _SENSITIVE_KEYS:
                continue
            safe[key_text] = _freeze_safe(item)
        return MappingProxyType(safe)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_safe(item) for item in value)
    return value


__all__ = [
    "CanonicalError",
    "CanonicalMessage",
    "CanonicalResult",
    "MediaReference",
    "build_canonical",
    "canonicalize_event",
    "canonicalize_message",
    "make_dedup_key",
    "normalize_chat_key",
]
