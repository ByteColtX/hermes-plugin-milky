"""从 typed Milky segment 提取正文、策略特征和延迟资源引用。"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from milky.models import (
    FaceSegment,
    FileSegment,
    ForwardSegment,
    ImageSegment,
    LightAppSegment,
    MarkdownSegment,
    MarketFaceSegment,
    MentionAllSegment,
    MentionSegment,
    RecordSegment,
    ReplySegment,
    Segment,
    TextSegment,
    UnknownSegment,
    VideoSegment,
    XmlSegment,
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
class MediaResourceReference:
    """保存 image、record 或 video 的 Milky 远端资源引用。"""

    kind: str
    resource_id: str | None = None
    temp_url: str | None = None
    name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    raw: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FileAttachmentReference:
    """保存入站 file segment 的远端附件引用。"""

    file_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    file_hash: str | None = None
    mime_type: str | None = None
    raw: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ForwardReference:
    """保存尚未展开的 forward 引用及其预览元数据。"""

    forward_id: str | None = None
    title: str | None = None
    preview: tuple[str, ...] = ()
    summary: str | None = None
    raw: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReplyReference:
    """保存 reply 目标及可选的内嵌原文。"""

    message_seq: int | None = None
    sender_id: int | None = None
    sender_name: str | None = None
    time: int | None = None
    segments: tuple[Segment, ...] = ()
    complete: bool = False
    raw: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtractedSegments:
    """表示一次无副作用的 segment 提取结果。"""

    body: str
    strategy_text: str
    mention_kinds: tuple[str, ...]
    has_reply: bool
    reply_message_seq: int | None
    has_image: bool
    media_resource_references: tuple[MediaResourceReference, ...]
    file_attachment_references: tuple[FileAttachmentReference, ...]
    forward_references: tuple[ForwardReference, ...]
    reply_references: tuple[ReplyReference, ...]
    unknown_segments: tuple[JsonObject, ...]
    diagnostics: tuple[str, ...] = ()
    has_supported_content: bool = False
    metadata: JsonObject = field(default_factory=dict)


def extract_segments(segments: Sequence[Segment], self_id: int) -> ExtractedSegments:
    """按原始顺序从 typed segments 生成稳定正文和策略特征。"""

    body_parts: list[str] = []
    strategy_parts: list[str] = []
    mention_kinds: list[str] = []
    media_resource_references: list[MediaResourceReference] = []
    file_attachment_references: list[FileAttachmentReference] = []
    forward_references: list[ForwardReference] = []
    reply_references: list[ReplyReference] = []
    unknown_segments: list[JsonObject] = []
    diagnostics: list[str] = []
    has_reply = False
    reply_message_seq: int | None = None
    has_image = False
    has_supported_content = False

    for segment in segments:
        if isinstance(segment, TextSegment):
            if segment.text:
                has_supported_content = True
            body_parts.append(segment.text)
            strategy_parts.append(segment.text)
            continue

        if isinstance(segment, MarkdownSegment):
            has_supported_content = True
            body_parts.append(segment.content)
            strategy_parts.append(segment.content)
            continue

        if isinstance(segment, MentionSegment):
            has_supported_content = True
            display = _mention_display(segment)
            body_parts.append(display)
            strategy_parts.append(display)
            if segment.user_id == self_id and "self" not in mention_kinds:
                mention_kinds.append("self")
            continue

        if isinstance(segment, MentionAllSegment):
            has_supported_content = True
            body_parts.append("@全体")
            strategy_parts.append("@全体")
            if "all" not in mention_kinds:
                mention_kinds.append("all")
            continue

        if isinstance(segment, ReplySegment):
            has_supported_content = True
            has_reply = True
            complete = _reply_is_complete(segment)
            reply_references.append(
                ReplyReference(
                    message_seq=segment.message_seq,
                    sender_id=segment.sender_id,
                    sender_name=segment.sender_name,
                    time=segment.time,
                    segments=segment.segments,
                    complete=complete,
                    raw=_safe_mapping(segment.raw),
                )
            )
            if complete:
                if reply_message_seq is None:
                    reply_message_seq = segment.message_seq
            else:
                body_parts.append("[reply:NOT SUPPORTED]")
                _append_once(diagnostics, "malformed_reply")
            continue

        if isinstance(segment, ImageSegment):
            has_supported_content = True
            has_image = True
            marker = _image_marker(segment)
            body_parts.append(marker)
            if marker == "[img:NOT SUPPORTED]":
                _append_once(diagnostics, "incomplete_media_reference")
            media_resource_references.append(
                MediaResourceReference(
                    kind="image",
                    resource_id=segment.resource_id,
                    temp_url=segment.temp_url,
                    name=segment.summary,
                    mime_type=_extra_text(segment, "mime_type"),
                    file_size=_extra_nonnegative_int(segment, "file_size"),
                    raw=_safe_mapping(segment.raw),
                )
            )
            continue

        if isinstance(segment, RecordSegment):
            has_supported_content = True
            body_parts.append("[record:NOT SUPPORTED]")
            if not (_has_text(segment.resource_id) or _has_text(segment.temp_url)):
                _append_once(diagnostics, "incomplete_media_reference")
            media_resource_references.append(
                MediaResourceReference(
                    kind="record",
                    resource_id=segment.resource_id,
                    temp_url=segment.temp_url,
                    mime_type=_extra_text(segment, "mime_type"),
                    file_size=_extra_nonnegative_int(segment, "file_size"),
                    raw=_safe_mapping(segment.raw),
                )
            )
            continue

        if isinstance(segment, VideoSegment):
            has_supported_content = True
            body_parts.append("[video:NOT SUPPORTED]")
            if not (_has_text(segment.resource_id) or _has_text(segment.temp_url)):
                _append_once(diagnostics, "incomplete_media_reference")
            media_resource_references.append(
                MediaResourceReference(
                    kind="video",
                    resource_id=segment.resource_id,
                    temp_url=segment.temp_url,
                    mime_type=_extra_text(segment, "mime_type"),
                    file_size=_extra_nonnegative_int(segment, "file_size"),
                    raw=_safe_mapping(segment.raw),
                )
            )
            continue

        if isinstance(segment, FileSegment):
            has_supported_content = True
            marker = _identifier_marker("file", segment.file_id)
            body_parts.append(marker)
            if marker == "[file:NOT SUPPORTED]":
                _append_once(diagnostics, "incomplete_media_reference")
            file_attachment_references.append(
                FileAttachmentReference(
                    file_id=segment.file_id,
                    file_name=segment.file_name,
                    file_size=segment.file_size,
                    file_hash=segment.file_hash,
                    mime_type=_extra_text(segment, "mime_type"),
                    raw=_safe_mapping(segment.raw),
                )
            )
            continue

        if isinstance(segment, ForwardSegment):
            has_supported_content = True
            marker = _identifier_marker("forward", segment.forward_id)
            body_parts.append(marker)
            if marker == "[forward:NOT SUPPORTED]":
                _append_once(diagnostics, "incomplete_media_reference")
            forward_references.append(
                ForwardReference(
                    forward_id=segment.forward_id,
                    title=segment.title,
                    preview=segment.preview,
                    summary=segment.summary,
                    raw=_safe_mapping(segment.raw),
                )
            )
            continue

        if isinstance(segment, FaceSegment):
            has_supported_content = True
            body_parts.append(_identifier_marker("face", segment.face_id))
            continue

        if isinstance(segment, MarketFaceSegment):
            has_supported_content = True
            body_parts.append("[market_face:NOT SUPPORTED]")
            continue

        if isinstance(segment, LightAppSegment):
            has_supported_content = True
            marker = _light_app_marker(segment.json_payload)
            body_parts.append(marker)
            if marker == "[light_app:NOT SUPPORTED]":
                _append_once(diagnostics, "malformed_light_app")
            continue

        if isinstance(segment, XmlSegment):
            has_supported_content = True
            body_parts.append("[xml:NOT SUPPORTED]")
            continue

        if isinstance(segment, UnknownSegment):
            unknown_segments.append(_safe_mapping(segment.raw))
            _append_once(diagnostics, "unknown_segment")
            continue

        _append_once(diagnostics, "unsupported_segment")

    if not mention_kinds:
        mention_kinds.append("none")
    metadata = _safe_mapping(
        {
            "unknown_segments": tuple(unknown_segments),
            "unknown_segment_types": tuple(
                str(segment.get("type", "")) for segment in unknown_segments
            ),
        }
    )
    return ExtractedSegments(
        body="".join(body_parts),
        strategy_text="".join(strategy_parts),
        mention_kinds=tuple(mention_kinds),
        has_reply=has_reply,
        reply_message_seq=reply_message_seq,
        has_image=has_image,
        media_resource_references=tuple(media_resource_references),
        file_attachment_references=tuple(file_attachment_references),
        forward_references=tuple(forward_references),
        reply_references=tuple(reply_references),
        unknown_segments=tuple(unknown_segments),
        diagnostics=tuple(diagnostics),
        has_supported_content=has_supported_content,
        metadata=metadata,
    )


extract_segment_features = extract_segments
extract_message_features = extract_segments


def _reply_is_complete(segment: ReplySegment) -> bool:
    """检查 reply 的协议必填字段，而不为缺失字段补默认值。"""

    if (
        segment.message_seq is None
        or segment.sender_id is None
        or segment.time is None
        or not isinstance(segment.segments, tuple)
    ):
        return False
    data = segment.raw.get("data")
    return isinstance(data, Mapping) and all(
        field in data for field in ("message_seq", "sender_id", "time", "segments")
    )


def _mention_display(segment: MentionSegment) -> str:
    name = segment.name.strip() if isinstance(segment.name, str) else ""
    return f"@{name or segment.user_id}"


def _identifier_marker(kind: str, value: object) -> str:
    """为带 ID 的 segment 生成稳定 placeholder。"""

    identifier = value.strip() if isinstance(value, str) else ""
    return f"[{kind}:{identifier or 'NOT SUPPORTED'}]"


def _image_marker(segment: ImageSegment) -> str:
    """按 summary、resource_id 顺序生成图片 placeholder。"""

    summary = segment.summary.strip() if isinstance(segment.summary, str) else ""
    if summary:
        return f"[img:{summary}]"
    return _identifier_marker("img", segment.resource_id)


def _light_app_marker(payload: str | None) -> str:
    """只投影 light app 顶层 meta，并保留其完整 JSON 值。"""

    if not isinstance(payload, str) or not payload.strip():
        return "[light_app:NOT SUPPORTED]"
    try:
        value = json.loads(payload)
    except (TypeError, ValueError):
        return "[light_app:NOT SUPPORTED]"
    if not isinstance(value, Mapping) or not isinstance(value.get("meta"), Mapping):
        return "[light_app:NOT SUPPORTED]"
    try:
        projected = json.dumps(
            {"meta": value["meta"]},
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return "[light_app:NOT SUPPORTED]"
    return f"[light_app:{projected}]"


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _extra_text(segment: Segment, field_name: str) -> str | None:
    value = segment.extras.get(field_name)
    return value if isinstance(value, str) else None


def _extra_nonnegative_int(segment: Segment, field_name: str) -> int | None:
    value = segment.extras.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


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
    "ReplyReference",
    "extract_message_features",
    "extract_segment_features",
    "extract_segments",
]
