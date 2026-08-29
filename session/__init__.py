"""Milky 插件的会话身份和进程内状态边界。"""

from .admission import AdmissionTicket, ChatAdmissionCoordinator
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
    "CanonicalError",
    "ChatAdmissionCoordinator",
    "ChatKeyError",
    "TempChatError",
    "TtlDeduplicator",
    "make_dedup_key",
    "normalize_chat_key",
    "validate_chat_key",
]
