"""将已解析的 Milky trigger 映射为 Hermes MessageEvent。

本模块只处理 detached batch 的 Hermes 边界：资源 resolver 已经完成后，才构造
MessageEvent。远端 URL、file ID 和插件内部引用不会直接进入 Hermes media 字段。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from milky.models import (
    FileSegment,
    ImageSegment,
    MarkdownSegment,
    MentionAllSegment,
    MentionSegment,
    RecordSegment,
    TextSegment,
    VideoSegment,
)
from milky.resources import (
    HermesAttachmentMaterialization,
    ResolvedMessage,
    ResourceDiagnostic,
)
from session.buffer import render_message_record

from .commands import recognize_slash_command


@dataclass(frozen=True, slots=True)
class _MappedRecord:
    """提供 buffer renderer 所需的规范化消息视图。"""

    chat_key: str
    sender_name: str
    sender_id: int
    body: str
    message_id: str | None
    quote_message_id: str | None


def map_message_event(
    message: object,
    resolved: ResolvedMessage,
    *,
    channel_context: str | None = None,
    context_image_materializations: Sequence[HermesAttachmentMaterialization] = (),
    source: object,
    message_event_cls: type | None = None,
    message_type_cls: type | None = None,
) -> object:
    """将一条 canonical 消息和 resolved 内容映射为 Hermes MessageEvent。

    ``message_event_cls`` 和 ``message_type_cls`` 可由测试或宿主显式注入；未注入时才
    延迟导入 Hermes，避免插件在未安装宿主时的导入阶段产生副作用。
    """

    if not isinstance(resolved, ResolvedMessage):
        raise TypeError("resolved must be a ResolvedMessage")
    event_cls, type_cls = _resolve_hermes_types(message_event_cls, message_type_cls)
    sender_name = _required_text(message, "sender_name")
    sender_id = _required_int(message, "sender_id")
    chat_key = _required_text(message, "chat_key")
    body = _required_text_value(resolved.body, "resolved body")
    message_id = _optional_text(message, "message_id")
    quote_id = _optional_text(message, "quote_message_id")
    current_materializations = tuple(resolved.hermes_attachment_materializations)
    materializations = _merge_media_materializations(
        context_image_materializations,
        current_materializations,
    )
    media_urls = [item.path for item in materializations if _is_local_path(item.path)]
    media_types = [
        item.mime_type
        for item in materializations
        if _is_local_path(item.path) and isinstance(item.mime_type, str) and item.mime_type
    ]
    if len(media_types) != len(media_urls):
        raise ValueError("materialized attachment MIME does not match local paths")

    reply = resolved.replies[0] if resolved.replies else None
    reply_text = reply.body if reply is not None else None
    reply_author_id = None if reply is None or reply.sender_id is None else str(reply.sender_id)
    reply_author_name = _optional_text(reply, "sender_name") if reply is not None else None
    metadata = _event_metadata(message, resolved, media_urls)
    return event_cls(
        text=render_message_record(
            _MappedRecord(chat_key, sender_name, sender_id, body, message_id, quote_id)
        ),
        message_type=_message_type(message, current_materializations, type_cls),
        user_id=str(sender_id),
        user_name=sender_name,
        source=source,
        raw_message=getattr(message, "raw", None),
        message_id=message_id,
        media_urls=media_urls,
        media_types=media_types,
        reply_to_message_id=quote_id,
        reply_to_text=reply_text,
        reply_to_author_id=reply_author_id,
        reply_to_author_name=reply_author_name,
        reply_to_is_own_message=reply is not None
        and reply.sender_id == _required_int(message, "self_id"),
        channel_context=channel_context,
        metadata=metadata,
        timestamp=datetime.fromtimestamp(_required_int(message, "timestamp"), tz=UTC),
        allow_gateway_control=False,
    )


def map_command_event(
    message: object,
    *,
    source: object,
    message_event_cls: type | None = None,
    message_type_cls: type | None = None,
) -> object:
    """将纯文本斜杠命令映射为允许 Hermes gateway control 的事件。"""

    command = recognize_slash_command(message)
    if command is None:
        raise ValueError("message is not a pure text slash command")
    event_cls, type_cls = _resolve_hermes_types(message_event_cls, message_type_cls)
    sender_name = _required_text(message, "sender_name")
    sender_id = _required_int(message, "sender_id")
    chat_key = _required_text(message, "chat_key")
    return event_cls(
        text=command.text,
        message_type=getattr(type_cls, "COMMAND", "command"),
        user_id=str(sender_id),
        user_name=sender_name,
        source=source,
        raw_message=getattr(message, "raw", None),
        message_id=_optional_text(message, "message_id"),
        media_urls=[],
        media_types=[],
        reply_to_message_id=None,
        reply_to_text=None,
        reply_to_author_id=None,
        reply_to_author_name=None,
        reply_to_is_own_message=False,
        channel_context=None,
        metadata={
            "source": "milky",
            "scene": _required_text(message, "scene"),
            "chat_key": chat_key,
            "command": command.name,
        },
        timestamp=datetime.fromtimestamp(_required_int(message, "timestamp"), tz=UTC),
        allow_gateway_control=True,
    )


def build_source(
    message: object,
    source_builder: Callable[..., object],
) -> object:
    """按 canonical 场景调用 Hermes 的 source builder。"""

    scene = _required_text(message, "scene")
    if scene not in {"friend", "group"}:
        raise ValueError("message scene is unsupported")
    group = getattr(message, "group", None)
    friend = getattr(message, "friend", None)
    chat_name = None
    if scene == "group" and group is not None:
        chat_name = _optional_text(group, "group_name")
    elif scene == "friend" and friend is not None:
        chat_name = _optional_text(friend, "nickname")
    return source_builder(
        chat_id=_required_text(message, "chat_key"),
        chat_name=chat_name,
        chat_type="group" if scene == "group" else "dm",
        user_id=str(_required_int(message, "sender_id")),
        user_name=_required_text(message, "sender_name"),
        message_id=_optional_text(message, "message_id"),
    )


def _resolve_hermes_types(
    message_event_cls: type | None,
    message_type_cls: type | None,
) -> tuple[type, type]:
    if message_event_cls is not None and message_type_cls is not None:
        return message_event_cls, message_type_cls
    try:
        from gateway.platforms.base import MessageEvent, MessageType
    except ImportError as error:
        raise RuntimeError(
            "Hermes MessageEvent types are unavailable; inject them at the host boundary"
        ) from error
    return message_event_cls or MessageEvent, message_type_cls or MessageType


def _message_type(message: object, materializations: tuple[object, ...], type_cls: type) -> object:
    """依据规范化 segment 和已 materialize 附件选择 Hermes 消息类型。"""

    if any(
        isinstance(segment, (TextSegment, MarkdownSegment, MentionSegment, MentionAllSegment))
        for segment in getattr(message, "segments", ())
    ):
        return type_cls.TEXT
    kinds = {getattr(item, "kind", None) for item in materializations}
    if not kinds:
        segments = getattr(message, "segments", ())
        if any(isinstance(segment, FileSegment) for segment in segments):
            return type_cls.DOCUMENT
        if any(isinstance(segment, ImageSegment) for segment in segments):
            return type_cls.PHOTO
        if any(isinstance(segment, (RecordSegment,)) for segment in segments):
            return type_cls.AUDIO
        if any(isinstance(segment, VideoSegment) for segment in segments):
            return type_cls.VIDEO
        return type_cls.TEXT
    if kinds == {"image"}:
        return type_cls.PHOTO
    if kinds == {"audio"}:
        return type_cls.AUDIO
    if kinds == {"video"}:
        return type_cls.VIDEO
    if kinds == {"document"}:
        return type_cls.DOCUMENT
    return type_cls.TEXT


def _event_metadata(
    message: object,
    resolved: ResolvedMessage,
    media_urls: list[str],
) -> dict[str, object]:
    """构造只含安全字段的 MessageEvent metadata。"""

    diagnostics = tuple(
        {
            "classification": diagnostic.classification,
            "reference_kind": diagnostic.reference_kind,
            "reason": diagnostic.reason,
            "reference_id": diagnostic.reference_id,
        }
        for diagnostic in resolved.diagnostics
        if isinstance(diagnostic, ResourceDiagnostic)
    )
    return {
        "source": "milky",
        "scene": _required_text(message, "scene"),
        "chat_key": _required_text(message, "chat_key"),
        "mention_kinds": tuple(getattr(message, "mention_kinds", ())),
        "has_reply": bool(getattr(message, "has_quote", False)),
        "has_image": bool(getattr(message, "has_image", False)),
        "resource_diagnostics": diagnostics,
        "materialized_media_count": len(media_urls),
    }


def _merge_media_materializations(
    context_image_materializations: Sequence[HermesAttachmentMaterialization],
    current_materializations: Sequence[HermesAttachmentMaterialization],
) -> tuple[HermesAttachmentMaterialization, ...]:
    """按历史 context 到当前消息的顺序合并并去重本地附件。"""

    merged: list[HermesAttachmentMaterialization] = []
    seen_paths: set[str] = set()
    for materialization in (*context_image_materializations, *current_materializations):
        path = materialization.path
        if not _is_local_path(path) or path in seen_paths:
            continue
        seen_paths.add(path)
        merged.append(materialization)
    return tuple(merged)


def _is_local_path(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "://" not in value


def _required_text(value: object, field_name: str) -> str:
    result = getattr(value, field_name, None)
    return _required_text_value(result, field_name)


def _required_text_value(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is missing")
    return value.strip()


def _optional_text(value: object, field_name: str) -> str | None:
    result = getattr(value, field_name, None)
    if not isinstance(result, str) or not result.strip():
        return None
    return result.strip()


def _required_int(value: object, field_name: str) -> int:
    result = getattr(value, field_name, None)
    if isinstance(result, bool) or not isinstance(result, int) or result < 0:
        raise ValueError(f"{field_name} is invalid")
    return result


__all__ = ["build_source", "map_command_event", "map_message_event"]
