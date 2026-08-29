"""Milky 入站消息的领域处理。"""

from .canonical import (
    CanonicalError,
    CanonicalMessage,
    CanonicalResult,
    MediaReference,
    build_canonical,
    canonicalize_event,
    canonicalize_message,
    make_dedup_key,
    normalize_chat_key,
)

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
