"""Milky 入站消息的领域处理。"""

from .canonical import (
    CanonicalError,
    CanonicalMessage,
    CanonicalResult,
    FileAttachmentReference,
    ForwardReference,
    MediaResourceReference,
    ReplyReference,
    build_canonical,
    canonicalize_event,
    canonicalize_message,
    make_dedup_key,
    normalize_chat_key,
)
from .extractor import (
    ExtractedSegments,
    extract_message_features,
    extract_segment_features,
    extract_segments,
)
from .hermes_mapper import build_source, map_message_event
from .normalizer import (
    NormalizationResult,
    NormalizedMessage,
    normalize,
    normalize_event,
    normalize_incoming_message,
    normalize_message,
)
from .pipeline import InboundPipeline, PipelineResult

__all__ = [
    "CanonicalError",
    "CanonicalMessage",
    "CanonicalResult",
    "ExtractedSegments",
    "FileAttachmentReference",
    "ForwardReference",
    "InboundPipeline",
    "MediaResourceReference",
    "NormalizationResult",
    "NormalizedMessage",
    "PipelineResult",
    "ReplyReference",
    "build_canonical",
    "build_source",
    "canonicalize_event",
    "canonicalize_message",
    "extract_message_features",
    "extract_segment_features",
    "extract_segments",
    "make_dedup_key",
    "map_message_event",
    "normalize",
    "normalize_chat_key",
    "normalize_event",
    "normalize_incoming_message",
    "normalize_message",
]
