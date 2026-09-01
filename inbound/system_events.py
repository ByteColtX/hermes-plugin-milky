"""将可注入的 Milky 系统事件转换为安全 context-only 记录。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from milky.models import Event
from session.context import ContextOnlyEvent
from session.identity import CanonicalError, normalize_chat_key

_CONTEXT_EVENT_TYPES = frozenset(
    {
        "group_nudge",
        "friend_nudge",
        "group_member_increase",
        "group_member_decrease",
    }
)
_MISSING = object()


@dataclass(frozen=True, slots=True)
class ContextEventResult:
    """表示系统事件是否可以登记为 context-only。"""

    classification: str
    value: ContextOnlyEvent | None
    reason: str | None = None


def parse_context_event(event: Event) -> ContextEventResult:
    """校验并渲染允许注入的系统事件，不执行网络或 Agent 操作。"""

    if not isinstance(event, Event):
        raise TypeError("event must be an Event")
    if event.event_type not in _CONTEXT_EVENT_TYPES:
        return ContextEventResult("observe_only", None, "event is not context-only")
    try:
        if event.event_type == "group_nudge":
            group_id = _required_id(event.data, "group_id")
            sender_id = _required_id(event.data, "sender_id")
            receiver_id = _required_id(event.data, "receiver_id")
            chat_key = normalize_chat_key("group", group_id)
            body = f"uid {sender_id} 戳了 uid {receiver_id}"
        elif event.event_type == "friend_nudge":
            user_id = _required_id(event.data, "user_id")
            chat_key = normalize_chat_key("friend", user_id)
            body = f"uid {user_id} 戳了一下"
        elif event.event_type == "group_member_increase":
            group_id = _required_id(event.data, "group_id")
            user_id = _required_id(event.data, "user_id")
            details = _details(event.data, ("group_id", "user_id", "operator_id", "invitor_id"))
            chat_key = normalize_chat_key("group", group_id)
            body = f"uid {user_id} 加入了群聊 Details: {_dump_details(details)}"
        else:
            group_id = _required_id(event.data, "group_id")
            user_id = _required_id(event.data, "user_id")
            details = _details(event.data, ("group_id", "user_id", "operator_id"))
            chat_key = normalize_chat_key("group", group_id)
            body = f"uid {user_id} 退出了群聊 Details: {_dump_details(details)}"
    except (CanonicalError, TypeError, ValueError) as error:
        return ContextEventResult("malformed", None, _safe_reason(error))

    return ContextEventResult(
        "accepted",
        ContextOnlyEvent(chat_key=chat_key, event_type=event.event_type, body=body),
    )


def is_context_event(event_type: object) -> bool:
    """返回事件类型是否属于 context-only 注入范围。"""

    return event_type in _CONTEXT_EVENT_TYPES


def _required_id(data: Mapping[str, Any], field_name: str) -> int:
    value = data.get(field_name, _MISSING)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} is invalid")
    return value


def _details(data: Mapping[str, Any], names: tuple[str, ...]) -> dict[str, int]:
    details: dict[str, int] = {}
    for name in names:
        value = data.get(name, _MISSING)
        if value is _MISSING or value is None:
            continue
        details[name] = _required_id(data, name)
    return details


def _dump_details(details: Mapping[str, int]) -> str:
    return json.dumps(details, ensure_ascii=False)


def _safe_reason(error: Exception) -> str:
    reason = str(error)
    return reason if reason and len(reason) <= 80 and "<" not in reason else "invalid_context_event"


__all__ = ["ContextEventResult", "is_context_event", "parse_context_event"]
