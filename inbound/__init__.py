"""Milky 入站消息的领域处理。

导出使用惰性解析，避免 ``milky.resources`` 通过 ``inbound.extractor`` 导入时，
在资源 DTO 尚未完成初始化前再次导入 Hermes mapper 形成循环依赖。
"""

from __future__ import annotations

import importlib
from typing import Final

_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "CanonicalError": ("inbound.canonical", "CanonicalError"),
    "CanonicalMessage": ("inbound.canonical", "CanonicalMessage"),
    "CanonicalResult": ("inbound.canonical", "CanonicalResult"),
    "FileAttachmentReference": ("inbound.canonical", "FileAttachmentReference"),
    "ForwardReference": ("inbound.canonical", "ForwardReference"),
    "MediaResourceReference": ("inbound.canonical", "MediaResourceReference"),
    "ReplyReference": ("inbound.canonical", "ReplyReference"),
    "build_canonical": ("inbound.canonical", "build_canonical"),
    "canonicalize_event": ("inbound.canonical", "canonicalize_event"),
    "canonicalize_message": ("inbound.canonical", "canonicalize_message"),
    "make_dedup_key": ("inbound.canonical", "make_dedup_key"),
    "normalize_chat_key": ("inbound.canonical", "normalize_chat_key"),
    "ExtractedSegments": ("inbound.extractor", "ExtractedSegments"),
    "extract_message_features": ("inbound.extractor", "extract_message_features"),
    "extract_segment_features": ("inbound.extractor", "extract_segment_features"),
    "extract_segments": ("inbound.extractor", "extract_segments"),
    "build_source": ("inbound.hermes_mapper", "build_source"),
    "map_command_event": ("inbound.hermes_mapper", "map_command_event"),
    "map_message_event": ("inbound.hermes_mapper", "map_message_event"),
    "SlashCommand": ("inbound.commands", "SlashCommand"),
    "is_slash_command": ("inbound.commands", "is_slash_command"),
    "recognize_slash_command": ("inbound.commands", "recognize_slash_command"),
    "NormalizationResult": ("inbound.normalizer", "NormalizationResult"),
    "NormalizedMessage": ("inbound.normalizer", "NormalizedMessage"),
    "normalize": ("inbound.normalizer", "normalize"),
    "normalize_event": ("inbound.normalizer", "normalize_event"),
    "normalize_incoming_message": ("inbound.normalizer", "normalize_incoming_message"),
    "normalize_message": ("inbound.normalizer", "normalize_message"),
    "InboundPipeline": ("inbound.pipeline", "InboundPipeline"),
    "PipelineResult": ("inbound.pipeline", "PipelineResult"),
    "ContextEventResult": ("inbound.system_events", "ContextEventResult"),
    "is_context_event": ("inbound.system_events", "is_context_event"),
    "parse_context_event": ("inbound.system_events", "parse_context_event"),
}

__all__ = [
    "CanonicalError",
    "CanonicalMessage",
    "CanonicalResult",
    "ContextEventResult",
    "ExtractedSegments",
    "FileAttachmentReference",
    "ForwardReference",
    "InboundPipeline",
    "MediaResourceReference",
    "NormalizationResult",
    "NormalizedMessage",
    "PipelineResult",
    "ReplyReference",
    "SlashCommand",
    "build_canonical",
    "build_source",
    "canonicalize_event",
    "canonicalize_message",
    "extract_message_features",
    "extract_segment_features",
    "extract_segments",
    "is_context_event",
    "is_slash_command",
    "make_dedup_key",
    "map_command_event",
    "map_message_event",
    "normalize",
    "normalize_chat_key",
    "normalize_event",
    "normalize_incoming_message",
    "normalize_message",
    "parse_context_event",
    "recognize_slash_command",
]


def __getattr__(name: str) -> object:
    """按需解析入站导出，避免包初始化阶段加载所有业务层。"""

    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(target[0])
    value = getattr(module, target[1])
    globals()[name] = value
    return value
