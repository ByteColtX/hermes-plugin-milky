"""将 Milky message_receive 建立为可审计的 canonical record。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from inbound.normalizer import (
    FileAttachmentReference,
    ForwardReference,
    MediaResourceReference,
    NormalizedMessage,
    ReplyReference,
    normalize_event,
    normalize_message,
)
from milky.models import Event, IncomingMessage, Segment
from session.identity import (
    CanonicalError,
    make_dedup_key,
    normalize_chat_key,
)
from will.input import MentionKind, WillInput

JsonObject = Mapping[str, Any]
_SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "password",
    "token",
}


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
    mention_kinds: tuple[MentionKind, ...]
    quote_message_id: str | None
    media_resource_references: tuple[MediaResourceReference, ...]
    file_attachment_references: tuple[FileAttachmentReference, ...]
    forward_references: tuple[ForwardReference, ...]
    reply_references: tuple[ReplyReference, ...]
    raw: JsonObject
    metadata: JsonObject
    diagnostics: tuple[str, ...] = ()
    will_input: WillInput | None = None

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
    def mention_kind(self) -> MentionKind:
        """返回兼容单值调用方的主要 mention 类型。"""

        for kind in ("self", "all", "here"):
            if kind in self.mention_kinds:
                return kind  # type: ignore[return-value]
        return "none"

    @property
    def mention_signals(self) -> tuple[MentionKind, ...]:
        """返回 canonical 保留的全部独立 mention 信号。"""

        return self.mention_kinds

    @property
    def media_refs(self) -> tuple[MediaResourceReference, ...]:
        """返回待补全媒体资源引用的兼容名称。"""

        return self.media_resource_references


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

    normalized_result = normalize_event(event, expected_self_id=expected_self_id)
    if normalized_result.value is None:
        return CanonicalResult(
            normalized_result.classification,
            None,
            normalized_result.reason,
        )
    if normalized_result.classification != "accepted":
        return CanonicalResult(
            normalized_result.classification,
            None,
            normalized_result.reason,
        )

    try:
        value = _canonicalize_normalized(
            normalized_result.value,
            expected_self_id=expected_self_id,
        )
    except CanonicalError as error:
        return CanonicalResult(error.classification, None, error.reason)
    return CanonicalResult("accepted", value)


def canonicalize_message(
    message: IncomingMessage,
    *,
    expected_self_id: int | None = None,
) -> CanonicalMessage:
    """将已通过 Milky parser 的消息转换为 canonical record。"""

    normalized_result = normalize_message(message, expected_self_id=expected_self_id)
    if normalized_result.value is None or normalized_result.classification != "accepted":
        raise CanonicalError(
            normalized_result.reason or "message cannot be normalized",
            normalized_result.classification,
        )
    return _canonicalize_normalized(normalized_result.value, expected_self_id=expected_self_id)


def _canonicalize_normalized(
    normalized: NormalizedMessage,
    *,
    expected_self_id: int | None = None,
) -> CanonicalMessage:
    """只从 T08 结果构造 canonical 身份外壳。"""

    if expected_self_id is not None and normalized.self_id != expected_self_id:
        raise CanonicalError("event self_id disagrees with configured self_id")
    chat_key = normalize_chat_key(normalized.scene, normalized.peer_id)
    if normalized.scene not in {"friend", "group"}:
        raise CanonicalError("message scene is not friend or group")
    if not isinstance(normalized.segments, tuple):
        raise CanonicalError("segments must be a tuple")

    message = _message_from_normalized(normalized)
    _validate_scene_entities(message)
    sender_name = _sender_name(message)
    diagnostics = normalized.diagnostics
    metadata = _freeze_safe(
        {
            **dict(normalized.metadata),
            "scene": normalized.scene,
            "chat_key": chat_key,
            "diagnostics": diagnostics,
        }
    )
    return CanonicalMessage(
        platform="milky",
        self_id=normalized.self_id,
        scene=normalized.scene,
        chat_key=chat_key,
        peer_id=normalized.peer_id,
        sender_id=normalized.sender_id,
        message_id=normalized.message_id,
        timestamp=normalized.timestamp,
        sender_name=sender_name,
        segments=normalized.segments,
        body=normalized.body,
        mention_kinds=normalized.mention_kinds,
        quote_message_id=normalized.reply_message_id,
        media_resource_references=normalized.media_resource_references,
        file_attachment_references=normalized.file_attachment_references,
        forward_references=normalized.forward_references,
        reply_references=normalized.reply_references,
        raw=normalized.raw,
        metadata=metadata,
        diagnostics=diagnostics,
        will_input=normalized.will_input,
    )


def _message_from_normalized(normalized: NormalizedMessage) -> IncomingMessage:
    """为 T07 的场景实体校验提供 typed 消息视图。"""

    return IncomingMessage(
        message_scene=normalized.scene,
        peer_id=normalized.peer_id,
        message_seq=None if normalized.message_id is None else int(normalized.message_id),
        sender_id=normalized.sender_id,
        time=normalized.timestamp,
        segments=normalized.segments,
        friend=normalized.friend,
        group=normalized.group,
        group_member=normalized.group_member,
        raw=normalized.raw,
        self_id=normalized.self_id,
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


def _freeze_safe(value: object) -> Any:
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.casefold() in _SENSITIVE_KEYS:
                continue
            safe[key_text] = _freeze_safe(item)
        return MappingProxyType(safe)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_safe(item) for item in value)
    return value


__all__ = [
    "CanonicalError",
    "CanonicalMessage",
    "CanonicalResult",
    "FileAttachmentReference",
    "ForwardReference",
    "MediaResourceReference",
    "ReplyReference",
    "build_canonical",
    "canonicalize_event",
    "canonicalize_message",
    "make_dedup_key",
    "normalize_chat_key",
]
