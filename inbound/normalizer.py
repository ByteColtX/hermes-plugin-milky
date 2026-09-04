"""Milky message_receive 的无网络规范化边界。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from milky.models import (
    Event,
    FriendEntity,
    GroupEntity,
    GroupMemberEntity,
    IncomingMessage,
    Segment,
)
from milky.parser import ParseError, parse_event, parse_incoming_message
from session.identity import CanonicalError, normalize_chat_key
from will.input import MentionKind, WillInput

from .extractor import (
    ExtractedSegments,
    FileAttachmentReference,
    ForwardReference,
    MediaResourceReference,
    ReplyReference,
    extract_segments,
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
class NormalizedMessage:
    """保存 T08 生成的有序正文、策略特征和延迟引用。"""

    platform: str
    event_type: str
    self_id: int
    scene: str
    chat_key: str
    peer_id: int
    sender_id: int
    message_id: str | None
    timestamp: int
    segments: tuple[Segment, ...]
    body: str
    strategy_text: str
    mention_kinds: tuple[MentionKind, ...]
    has_reply: bool
    reply_message_seq: int | None
    is_self_quote: bool
    has_image: bool
    media_resource_references: tuple[MediaResourceReference, ...]
    file_attachment_references: tuple[FileAttachmentReference, ...]
    forward_references: tuple[ForwardReference, ...]
    reply_references: tuple[ReplyReference, ...]
    raw: JsonObject
    metadata: JsonObject
    diagnostics: tuple[str, ...]
    will_input: WillInput
    friend: FriendEntity | None
    group: GroupEntity | None
    group_member: GroupMemberEntity | None
    quote_target_is_self: bool = False

    @property
    def time(self) -> int:
        """返回兼容协议命名的 Unix 秒时间戳。"""

        return self.timestamp

    @property
    def mention_kind(self) -> MentionKind:
        """返回兼容单值调用方的主要 mention 类型。"""

        return self.will_input.mention_kind

    @property
    def mention_signals(self) -> tuple[MentionKind, ...]:
        """返回所有独立 mention 信号。"""

        return self.mention_kinds

    @property
    def has_quote(self) -> bool:
        """返回是否存在 reply segment。"""

        return self.has_reply

    @property
    def self_quote(self) -> bool:
        """返回 reply 是否明确指向 Bot。"""

        return self.is_self_quote

    @property
    def has_self_quote(self) -> bool:
        """返回是否存在指向 Bot 的 reply。"""

        return self.is_self_quote

    @property
    def reply_message_id(self) -> str | None:
        """返回供字符串 ID 边界使用的引用序号。"""

        return None if self.reply_message_seq is None else str(self.reply_message_seq)

    @property
    def media_refs(self) -> tuple[MediaResourceReference, ...]:
        """返回待 trigger 阶段补全的媒体资源引用兼容名称。"""

        return self.media_resource_references

    @property
    def unknown_segments(self) -> tuple[JsonObject, ...]:
        """返回仅供诊断的未知 segment raw。"""

        value = self.metadata.get("unknown_segments", ())
        return value if isinstance(value, tuple) else ()


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """表示规范化接受、忽略、丢弃或 malformed 的结果。"""

    classification: str
    value: NormalizedMessage | None
    reason: str | None = None


def normalize_event(
    event: Event | object,
    *,
    expected_self_id: int | None = None,
) -> NormalizationResult:
    """解析并规范化一个 message_receive 事件，不执行任何外部操作。"""

    try:
        parsed_event = event if isinstance(event, Event) else parse_event(event)
        if parsed_event.event_type != "message_receive":
            return NormalizationResult("observe_only", None, "event is not message_receive")
        parsed = parse_incoming_message(parsed_event)
    except ParseError as error:
        return NormalizationResult(error.classification, None, error.reason)

    if parsed.classification == "ignored_temp":
        return NormalizationResult("ignored_temp", None, parsed.reason)
    if parsed.value is None:
        return NormalizationResult("malformed", None, "message parser returned no value")
    return normalize_message(
        parsed.value,
        expected_self_id=expected_self_id,
        parser_reason=parsed.reason,
    )


def normalize_message(
    message: IncomingMessage,
    *,
    expected_self_id: int | None = None,
    parser_reason: str | None = None,
) -> NormalizationResult:
    """规范化一个已由 T04 parser 生成的 typed 消息。"""

    try:
        _validate_message_header(message, expected_self_id)
        chat_key = normalize_chat_key(message.message_scene, message.peer_id)
    except (CanonicalError, TypeError) as error:
        reason = getattr(error, "reason", str(error))
        classification = getattr(error, "classification", "malformed")
        return NormalizationResult(classification, None, reason)

    extracted = extract_segments(message.segments, message.self_id)
    diagnostics = list(extracted.diagnostics)
    if parser_reason is not None:
        _append_once(diagnostics, parser_reason)
    if message.message_seq is None:
        _append_once(diagnostics, "no_stable_message_id")

    metadata = _safe_mapping(
        {
            "event_type": "message_receive",
            "scene": message.message_scene,
            "chat_key": chat_key,
            "diagnostics": tuple(diagnostics),
            **dict(extracted.metadata),
        }
    )
    normalized = NormalizedMessage(
        platform="milky",
        event_type="message_receive",
        self_id=message.self_id,
        scene=message.message_scene,
        chat_key=chat_key,
        peer_id=message.peer_id,
        sender_id=message.sender_id,
        message_id=None if message.message_seq is None else str(message.message_seq),
        timestamp=message.time,
        segments=message.segments,
        body=extracted.body,
        strategy_text=extracted.strategy_text,
        mention_kinds=_mention_kinds(extracted.mention_kinds),
        has_reply=extracted.has_reply,
        reply_message_seq=extracted.reply_message_seq,
        is_self_quote=extracted.is_self_quote,
        has_image=extracted.has_image,
        media_resource_references=extracted.media_resource_references,
        file_attachment_references=extracted.file_attachment_references,
        forward_references=extracted.forward_references,
        reply_references=extracted.reply_references,
        raw=_safe_mapping(message.raw),
        metadata=metadata,
        diagnostics=tuple(diagnostics),
        will_input=WillInput(
            event_type="message_receive",
            scene=message.message_scene,
            self_id=message.self_id,
            chat_key=chat_key,
            channel=chat_key,
            timestamp=message.time,
            segments=message.segments,
            text=extracted.strategy_text,
            mention_kinds=_mention_kinds(extracted.mention_kinds),
            has_reply=extracted.has_reply,
            reply_message_seq=extracted.reply_message_seq,
            has_image=extracted.has_image,
            is_self_quote=extracted.is_self_quote,
        ),
        friend=message.friend,
        group=message.group,
        group_member=message.group_member,
        quote_target_is_self=extracted.quote_target_is_self,
    )
    if not extracted.has_supported_content:
        return NormalizationResult("dropped", None, "no_supported_content")
    if "malformed_reply" in diagnostics:
        return NormalizationResult("malformed", normalized, "reply has missing required fields")
    return NormalizationResult("accepted", normalized)


def normalize_incoming_message(
    message: IncomingMessage,
    *,
    expected_self_id: int | None = None,
) -> NormalizationResult:
    """提供描述性别名，供入站 pipeline 调用。"""

    return normalize_message(message, expected_self_id=expected_self_id)


normalize = normalize_event


def _validate_message_header(message: IncomingMessage, expected_self_id: int | None) -> None:
    if not isinstance(message, IncomingMessage):
        raise TypeError("message must be an IncomingMessage")
    if message.message_scene == "temp":
        raise CanonicalError("temporary message scene", "ignored_temp")
    if message.message_scene not in {"friend", "group"}:
        raise CanonicalError("message scene is not friend or group")
    _require_nonnegative_int(message.self_id, "self_id")
    _require_nonnegative_int(message.peer_id, "peer_id")
    _require_nonnegative_int(message.sender_id, "sender_id")
    _require_nonnegative_int(message.time, "time")
    if message.message_seq is not None:
        _require_nonnegative_int(message.message_seq, "message_seq")
    if expected_self_id is not None and message.self_id != expected_self_id:
        raise CanonicalError("event self_id disagrees with configured self_id")


def _require_nonnegative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CanonicalError(f"{field_name} must be a non-negative integer")


def _mention_kinds(values: Sequence[str]) -> tuple[MentionKind, ...]:
    if not values:
        return ("none",)
    return tuple(values)  # type: ignore[return-value]


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _safe_mapping(value: Mapping[str, Any]) -> JsonObject:
    return MappingProxyType(
        {
            str(key): _safe_value(item)
            for key, item in value.items()
            if str(key).casefold() not in _SENSITIVE_KEYS
        }
    )


def _safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _safe_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_safe_value(item) for item in value)
    return value


__all__ = [
    "ExtractedSegments",
    "FileAttachmentReference",
    "ForwardReference",
    "MediaResourceReference",
    "NormalizationResult",
    "NormalizedMessage",
    "ReplyReference",
    "normalize",
    "normalize_event",
    "normalize_incoming_message",
    "normalize_message",
]
