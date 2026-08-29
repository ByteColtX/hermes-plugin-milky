"""Milky chat key 和稳定去重 key 的本地身份边界。"""

from __future__ import annotations

import re
from typing import Final

_MISSING: Final = object()
_DECIMAL_PATTERN = re.compile(r"^(0|[1-9][0-9]*)$")
_CHAT_KEY_PATTERN = re.compile(r"^(group|dm):(0|[1-9][0-9]*)$")
_SCENE_PREFIXES = {"friend": "dm", "group": "group"}


class CanonicalError(ValueError):
    """表示身份无法安全规范化。"""

    def __init__(self, reason: str, classification: str = "malformed") -> None:
        self.classification = classification
        self.reason = reason
        super().__init__(f"{classification}: {reason}")


class ChatKeyError(CanonicalError):
    """表示输入不是允许的 group/dm chat key。"""


class TempChatError(CanonicalError):
    """表示临时会话不能创建 chat key。"""

    def __init__(self) -> None:
        super().__init__("temporary message scene", "ignored_temp")


def normalize_chat_key(scene_or_key: object, peer_id: object = _MISSING) -> str:
    """将场景和 ID，或已有 chat key，规范化为唯一命名空间。"""

    if peer_id is _MISSING:
        if not isinstance(scene_or_key, str):
            raise ChatKeyError("chat key must be text")
        match = _CHAT_KEY_PATTERN.fullmatch(scene_or_key)
        if match is None:
            raise ChatKeyError("chat key must be group:<id> or dm:<id>")
        return f"{match.group(1)}:{_normalize_decimal(match.group(2), 'chat id')}"

    if scene_or_key == "temp":
        raise TempChatError()
    if not isinstance(scene_or_key, str) or scene_or_key not in _SCENE_PREFIXES:
        raise ChatKeyError("message scene is not friend or group")
    prefix = _SCENE_PREFIXES[scene_or_key]
    return f"{prefix}:{_normalize_decimal(peer_id, 'peer_id')}"


def validate_chat_key(value: object) -> str:
    """校验调用方提供的内部 chat key，并返回其规范形式。"""

    return normalize_chat_key(value)


def make_dedup_key(self_id: object, chat_key: object, message_id: object) -> str:
    """生成带 Bot 和 chat 命名空间的稳定去重 key。"""

    if message_id is None:
        raise CanonicalError("message_id is not stable")
    normalized_self_id = _normalize_decimal(self_id, "self_id")
    normalized_chat_key = validate_chat_key(chat_key)
    normalized_message_id = _normalize_decimal(message_id, "message_id")
    return f"milky:{normalized_self_id}:{normalized_chat_key}:{normalized_message_id}"


def _normalize_decimal(value: object, field_name: str) -> str:
    if isinstance(value, bool):
        raise ChatKeyError(f"{field_name} must be a non-negative decimal integer")
    if isinstance(value, int):
        if value < 0:
            raise ChatKeyError(f"{field_name} must be a non-negative decimal integer")
        return str(value)
    if isinstance(value, str) and _DECIMAL_PATTERN.fullmatch(value):
        return value
    raise ChatKeyError(f"{field_name} must be a non-negative decimal integer")


__all__ = [
    "CanonicalError",
    "ChatKeyError",
    "TempChatError",
    "make_dedup_key",
    "normalize_chat_key",
    "validate_chat_key",
]
