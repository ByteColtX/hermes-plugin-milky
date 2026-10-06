"""固定 Milky Tool Action 的目录与网络前参数校验。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _error(classification: str, action: str, reason: str) -> Exception:
    """延迟导入 ActionError，避免协议客户端循环导入。"""
    from .client import ActionError

    return ActionError(classification, action, reason)


TOOL_ACTIONS = frozenset(
    {
        "send_profile_like",
        "send_friend_nudge",
        "send_group_nudge",
        "recall_group_message",
        "get_group_info",
        "get_group_member_list",
        "get_group_member_info",
        "set_group_member_mute",
        "set_group_whole_mute",
        "get_resource_temp_url",
        "get_forwarded_messages",
        "get_group_file_download_url",
        "get_group_files",
        "get_private_file_download_url",
        "accept_group_request",
        "reject_group_request",
        "accept_group_invitation",
        "reject_group_invitation",
        "kick_group_member",
        "quit_group",
        "delete_friend",
        "get_friend_requests",
        "get_friend_info",
        "accept_friend_request",
        "reject_friend_request",
        "set_group_member_special_title",
    }
)

_MIN_QQ_ID = 10001
_MAX_QQ_ID = 4294967295
_MAX_SAFE_INTEGER = 9007199254740991


def is_tool_action(action: object) -> bool:
    """返回 operation 是否属于固定 Tool 目录。"""
    return isinstance(action, str) and action in TOOL_ACTIONS


def validate_tool_params(action: str, params: Mapping[str, Any] | None) -> None:
    """在固定 Tool Action 进入 HTTP 前校验完整参数集合。"""
    if action not in TOOL_ACTIONS:
        raise _error("unsupported", action, "Action is not registered as a Tool")
    if params is None:
        values: Mapping[str, Any] = {}
    elif isinstance(params, Mapping):
        values = params
    else:
        raise _error("invalid_input", action, "parameters must be an object")
    schemas: dict[str, tuple[set[str], set[str]]] = {
        "send_profile_like": ({"user_id", "count"}, {"user_id"}),
        "send_friend_nudge": ({"user_id", "is_self"}, {"user_id"}),
        "send_group_nudge": ({"group_id", "user_id"}, {"group_id", "user_id"}),
        "recall_group_message": ({"group_id", "message_seq"}, {"group_id", "message_seq"}),
        "get_group_info": ({"group_id", "no_cache"}, {"group_id"}),
        "get_group_member_list": ({"group_id", "no_cache"}, {"group_id"}),
        "get_group_member_info": ({"group_id", "user_id", "no_cache"}, {"group_id", "user_id"}),
        "set_group_member_mute": ({"group_id", "user_id", "duration"}, {"group_id", "user_id"}),
        "set_group_whole_mute": ({"group_id", "is_mute"}, {"group_id"}),
        "get_resource_temp_url": ({"resource_id"}, {"resource_id"}),
        "get_forwarded_messages": ({"forward_id"}, {"forward_id"}),
        "get_private_file_download_url": (
            {"user_id", "file_id", "file_hash", "is_self_send"},
            {"user_id", "file_id", "file_hash"},
        ),
        "get_group_file_download_url": ({"group_id", "file_id"}, {"group_id", "file_id"}),
        "accept_group_request": (
            {"notification_seq", "notification_type", "group_id", "is_filtered"},
            {"notification_seq", "notification_type", "group_id"},
        ),
        "reject_group_request": (
            {"notification_seq", "notification_type", "group_id", "is_filtered", "reason"},
            {"notification_seq", "notification_type", "group_id"},
        ),
        "accept_group_invitation": ({"group_id", "invitation_seq"}, {"group_id", "invitation_seq"}),
        "reject_group_invitation": ({"group_id", "invitation_seq"}, {"group_id", "invitation_seq"}),
        "get_group_files": ({"group_id", "parent_folder_id"}, {"group_id"}),
        "kick_group_member": (
            {"group_id", "user_id", "reject_add_request"},
            {"group_id", "user_id"},
        ),
        "quit_group": ({"group_id"}, {"group_id"}),
        "delete_friend": ({"user_id"}, {"user_id"}),
        "get_friend_requests": ({"limit", "is_filtered"}, set()),
        "get_friend_info": ({"user_id"}, {"user_id"}),
        "accept_friend_request": ({"initiator_uid", "is_filtered"}, {"initiator_uid"}),
        "reject_friend_request": ({"initiator_uid", "is_filtered", "reason"}, {"initiator_uid"}),
        "set_group_member_special_title": (
            {"group_id", "user_id", "special_title"},
            {"group_id", "user_id", "special_title"},
        ),
    }
    allowed, required = schemas[action]
    if set(values) - allowed or not required.issubset(values):
        raise _error("invalid_input", action, "parameters are invalid")
    for field in {"user_id", "group_id"} & set(values):
        _integer(values[field], field, action, minimum=_MIN_QQ_ID, maximum=_MAX_QQ_ID)
    for field in ("message_seq", "count", "duration", "limit"):
        if field in values and values[field] is not None:
            _integer(values[field], field, action)
    for field in ("notification_seq", "invitation_seq"):
        if field in values:
            _integer(values[field], field, action)
    for field in (
        "is_self",
        "no_cache",
        "is_mute",
        "is_self_send",
        "reject_add_request",
        "is_filtered",
    ):
        if field in values and values[field] is not None and not isinstance(values[field], bool):
            raise _error("invalid_input", action, f"{field} is invalid")
    for field in ("forward_id", "file_id", "file_hash", "initiator_uid", "resource_id"):
        if field in values:
            _text(values[field], field, action)
    if "special_title" in values and not isinstance(values["special_title"], str):
        raise _error("invalid_input", action, "special_title is invalid")
    if "notification_type" in values and (
        not isinstance(values["notification_type"], str)
        or values["notification_type"] not in {"join_request", "invited_join_request"}
    ):
        raise _error("invalid_input", action, "notification_type is invalid")
    if "parent_folder_id" in values and values["parent_folder_id"] is not None:
        _text(values["parent_folder_id"], "parent_folder_id", action)
    if "reason" in values and values["reason"] is not None:
        if action == "reject_group_request":
            _text(values["reason"], "reason", action)
        elif not isinstance(values["reason"], str):
            raise _error("invalid_input", action, "reason is invalid")


def _integer(
    value: object, field: str, action: str, *, minimum: int = 0, maximum: int = _MAX_SAFE_INTEGER
) -> None:
    """校验固定 Tool 的严格整数范围。"""
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise _error("invalid_input", action, f"{field} is invalid")


def _text(value: object, field: str, action: str) -> None:
    """校验固定 Tool 的非空文本。"""
    if not isinstance(value, str) or not value.strip():
        raise _error("invalid_input", action, f"{field} is invalid")


__all__ = ["TOOL_ACTIONS", "is_tool_action", "validate_tool_params"]
