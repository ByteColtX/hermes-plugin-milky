"""Milky 插件的会话身份和进程内状态边界。"""

from .admission import AdmissionTicket, ChatAdmissionCoordinator
from .buffer import (
    BufferAppendResult,
    BufferDiagnostic,
    DetachedTriggerBatch,
    HandoffFailureResult,
    WaitBuffer,
    WaitBufferEntry,
    format_channel_context,
    format_message_record,
    render_channel_context,
    render_message_record,
)
from .dedup import TtlDeduplicator
from .identity import (
    CanonicalError,
    ChatKeyError,
    TempChatError,
    make_dedup_key,
    normalize_chat_key,
    validate_chat_key,
)

__all__ = [
    "AdmissionTicket",
    "BufferAppendResult",
    "BufferDiagnostic",
    "CanonicalError",
    "ChatAdmissionCoordinator",
    "ChatKeyError",
    "DetachedTriggerBatch",
    "HandoffFailureResult",
    "TempChatError",
    "TtlDeduplicator",
    "WaitBuffer",
    "WaitBufferEntry",
    "format_channel_context",
    "format_message_record",
    "make_dedup_key",
    "normalize_chat_key",
    "render_channel_context",
    "render_message_record",
    "validate_chat_key",
]
