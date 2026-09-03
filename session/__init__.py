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
    render_ordered_context,
    render_system_context_record,
)
from .context import (
    ContextAppendResult,
    ContextBuffer,
    ContextBufferDiagnostic,
    ContextOnlyEvent,
    SystemContextBuffer,
    SystemContextEntry,
)
from .dedup import TtlDeduplicator
from .identity import (
    BotIdentity,
    BotIdentitySnapshot,
    CanonicalError,
    ChatKeyError,
    TempChatError,
    make_dedup_key,
    normalize_chat_key,
    validate_chat_key,
)

__all__ = [
    "AdmissionTicket",
    "BotIdentity",
    "BotIdentitySnapshot",
    "BufferAppendResult",
    "BufferDiagnostic",
    "CanonicalError",
    "ChatAdmissionCoordinator",
    "ChatKeyError",
    "ContextAppendResult",
    "ContextBuffer",
    "ContextBufferDiagnostic",
    "ContextOnlyEvent",
    "DetachedTriggerBatch",
    "HandoffFailureResult",
    "SystemContextBuffer",
    "SystemContextEntry",
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
    "render_ordered_context",
    "render_system_context_record",
    "validate_chat_key",
]
