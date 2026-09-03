"""注册与 Milky operationId 对齐的 Hermes Agent 工具。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from typing import Any

from milky.client import ActionError
from milky.models import MilkyEnvelope
from milky.observability import log_event

from .sender import (
    MilkyOutboundSender,
    OutboundSendResult,
)

_ACTIVE_SENDER: MilkyOutboundSender | None = None
_MISSING = object()
logger = logging.getLogger(__name__)
_SAFE_TOOL_OPAQUE = re.compile(r"^[A-Za-z0-9_.:-]+$")

SEND_PROFILE_LIKE_SCHEMA = {
    "name": "send_profile_like",
    "description": "给指定好友发送名片点赞；调用前必须提供合法 QQ 号。",
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "好友 QQ 号",
            },
            "count": {
                "type": "integer",
                "minimum": 0,
                "maximum": 9007199254740991,
                "nullable": True,
                "description": "可选点赞数量",
            },
        },
        "required": ["user_id"],
        "additionalProperties": False,
    },
}

SEND_FRIEND_NUDGE_SCHEMA = {
    "name": "send_friend_nudge",
    "description": "向指定好友发送戳一戳。",
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "好友 QQ 号",
            },
            "is_self": {
                "type": "boolean",
                "nullable": True,
                "description": "是否戳自己",
            },
        },
        "required": ["user_id"],
        "additionalProperties": False,
    },
}

GROUP_NUDGE_SCHEMA = {
    "name": "send_group_nudge",
    "description": "向指定群成员发送戳一戳。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "user_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "被戳的群成员 QQ 号",
            },
        },
        "required": ["group_id", "user_id"],
        "additionalProperties": False,
    },
}

RECALL_GROUP_MESSAGE_SCHEMA = {
    "name": "recall_group_message",
    "description": "撤回指定群消息；目标和远端消息序号必须明确提供。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "message_seq": {
                "type": "integer",
                "minimum": 0,
                "maximum": 9007199254740991,
                "description": "Milky 远端消息序号",
            },
        },
        "required": ["group_id", "message_seq"],
        "additionalProperties": False,
    },
}

GET_GROUP_INFO_SCHEMA = {
    "name": "get_group_info",
    "description": "获取指定群的信息。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "no_cache": {
                "type": "boolean",
                "nullable": True,
                "description": "是否强制不使用缓存",
            },
        },
        "required": ["group_id"],
        "additionalProperties": False,
    },
}

GET_GROUP_MEMBER_LIST_SCHEMA = {
    "name": "get_group_member_list",
    "description": "获取指定群的成员列表。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "no_cache": {
                "type": "boolean",
                "nullable": True,
                "description": "是否强制不使用缓存",
            },
        },
        "required": ["group_id"],
        "additionalProperties": False,
    },
}

GET_GROUP_MEMBER_INFO_SCHEMA = {
    "name": "get_group_member_info",
    "description": "获取指定群成员的信息。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "user_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群成员 QQ 号",
            },
            "no_cache": {
                "type": "boolean",
                "nullable": True,
                "description": "是否强制不使用缓存",
            },
        },
        "required": ["group_id", "user_id"],
        "additionalProperties": False,
    },
}

SET_GROUP_MEMBER_MUTE_SCHEMA = {
    "name": "set_group_member_mute",
    "description": "设置群成员禁言；duration 为 0 时取消禁言。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "user_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "被设置的 QQ 号",
            },
            "duration": {
                "type": "integer",
                "minimum": 0,
                "maximum": 9007199254740991,
                "nullable": True,
                "description": "禁言持续时间（秒）",
            },
        },
        "required": ["group_id", "user_id"],
        "additionalProperties": False,
    },
}

SET_GROUP_WHOLE_MUTE_SCHEMA = {
    "name": "set_group_whole_mute",
    "description": "设置群全员禁言；is_mute 为 false 时取消全员禁言。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "is_mute": {
                "type": "boolean",
                "nullable": True,
                "description": "是否开启全员禁言",
            },
        },
        "required": ["group_id"],
        "additionalProperties": False,
    },
}

GET_FORWARDED_MESSAGES_SCHEMA = {
    "name": "get_forwarded_messages",
    "description": "查询指定合并转发消息的完整 Milky 结果。",
    "parameters": {
        "type": "object",
        "properties": {
            "forward_id": {
                "type": "string",
                "minLength": 1,
                "description": "合并转发消息 ID",
            }
        },
        "required": ["forward_id"],
        "additionalProperties": False,
    },
}

GET_PRIVATE_FILE_DOWNLOAD_URL_SCHEMA = {
    "name": "get_private_file_download_url",
    "description": "查询私聊文件的下载链接；工具不会下载或缓存文件。",
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "私聊对象 QQ 号",
            },
            "file_id": {
                "type": "string",
                "minLength": 1,
                "description": "文件 ID",
            },
            "file_hash": {
                "type": "string",
                "minLength": 1,
                "description": "文件 hash",
            },
            "is_self_send": {
                "type": "boolean",
                "nullable": True,
                "description": "文件是否由自己发送",
            },
        },
        "required": ["user_id", "file_id", "file_hash"],
        "additionalProperties": False,
    },
}

KICK_GROUP_MEMBER_SCHEMA = {
    "name": "kick_group_member",
    "description": "将指定 QQ 移出群聊；仅在显式调用时执行。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "user_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "待移出成员 QQ 号",
            },
            "reject_add_request": {
                "type": "boolean",
                "nullable": True,
                "description": "是否拒绝该成员再次加群申请",
            },
        },
        "required": ["group_id", "user_id"],
        "additionalProperties": False,
    },
}

QUIT_GROUP_SCHEMA = {
    "name": "quit_group",
    "description": "退出指定群聊；仅在显式调用时执行。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            }
        },
        "required": ["group_id"],
        "additionalProperties": False,
    },
}

DELETE_FRIEND_SCHEMA = {
    "name": "delete_friend",
    "description": "删除指定好友关系；仅在显式调用时执行。",
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "好友 QQ 号",
            }
        },
        "required": ["user_id"],
        "additionalProperties": False,
    },
}

GET_FRIEND_REQUESTS_SCHEMA = {
    "name": "get_friend_requests",
    "description": "查询好友请求列表并保留完整 Milky 结果。",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "minimum": 0,
                "maximum": 9007199254740991,
                "nullable": True,
                "description": "最多返回的请求数量",
            },
            "is_filtered": {
                "type": "boolean",
                "nullable": True,
                "description": "是否只返回过滤后的请求",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}

ACCEPT_FRIEND_REQUEST_SCHEMA = {
    "name": "accept_friend_request",
    "description": "接受指定好友请求；仅在显式调用时执行。",
    "parameters": {
        "type": "object",
        "properties": {
            "initiator_uid": {
                "type": "string",
                "minLength": 1,
                "description": "好友请求发起者 UID",
            },
            "is_filtered": {
                "type": "boolean",
                "nullable": True,
                "description": "是否按过滤后的请求处理",
            },
        },
        "required": ["initiator_uid"],
        "additionalProperties": False,
    },
}

REJECT_FRIEND_REQUEST_SCHEMA = {
    "name": "reject_friend_request",
    "description": "拒绝指定好友请求；仅在显式调用时执行。",
    "parameters": {
        "type": "object",
        "properties": {
            "initiator_uid": {
                "type": "string",
                "minLength": 1,
                "description": "好友请求发起者 UID",
            },
            "is_filtered": {
                "type": "boolean",
                "nullable": True,
                "description": "是否按过滤后的请求处理",
            },
            "reason": {
                "type": "string",
                "nullable": True,
                "description": "拒绝理由",
            },
        },
        "required": ["initiator_uid"],
        "additionalProperties": False,
    },
}

GET_GROUP_FILE_DOWNLOAD_URL_SCHEMA = {
    "name": "get_group_file_download_url",
    "description": "查询群文件的下载链接；工具不会下载或缓存文件。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "file_id": {
                "type": "string",
                "minLength": 1,
                "description": "群文件 ID",
            },
        },
        "required": ["group_id", "file_id"],
        "additionalProperties": False,
    },
}

ACCEPT_GROUP_REQUEST_SCHEMA = {
    "name": "accept_group_request",
    "description": "接受指定入群请求；仅在显式调用时执行。",
    "parameters": {
        "type": "object",
        "properties": {
            "notification_seq": {
                "type": "integer",
                "minimum": 0,
                "maximum": 9007199254740991,
                "description": "入群请求通知序号",
            },
            "notification_type": {
                "type": "string",
                "enum": ["join_request", "invited_join_request"],
                "description": "入群请求类型",
            },
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "is_filtered": {
                "type": "boolean",
                "nullable": True,
                "description": "是否按过滤后的通知处理",
            },
        },
        "required": ["notification_seq", "notification_type", "group_id"],
        "additionalProperties": False,
    },
}

REJECT_GROUP_REQUEST_SCHEMA = {
    "name": "reject_group_request",
    "description": "拒绝指定入群请求；仅在显式调用时执行。",
    "parameters": {
        "type": "object",
        "properties": {
            "notification_seq": {
                "type": "integer",
                "minimum": 0,
                "maximum": 9007199254740991,
                "description": "入群请求通知序号",
            },
            "notification_type": {
                "type": "string",
                "enum": ["join_request", "invited_join_request"],
                "description": "入群请求类型",
            },
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "is_filtered": {
                "type": "boolean",
                "nullable": True,
                "description": "是否按过滤后的通知处理",
            },
            "reason": {
                "type": "string",
                "nullable": True,
                "minLength": 1,
                "description": "拒绝理由",
            },
        },
        "required": ["notification_seq", "notification_type", "group_id"],
        "additionalProperties": False,
    },
}

ACCEPT_GROUP_INVITATION_SCHEMA = {
    "name": "accept_group_invitation",
    "description": "接受邀请 Bot 入群的通知；仅在显式调用时执行。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "invitation_seq": {
                "type": "integer",
                "minimum": 0,
                "maximum": 9007199254740991,
                "description": "群邀请序号",
            },
        },
        "required": ["group_id", "invitation_seq"],
        "additionalProperties": False,
    },
}

REJECT_GROUP_INVITATION_SCHEMA = {
    "name": "reject_group_invitation",
    "description": "拒绝邀请 Bot 入群的通知；仅在显式调用时执行。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "invitation_seq": {
                "type": "integer",
                "minimum": 0,
                "maximum": 9007199254740991,
                "description": "群邀请序号",
            },
        },
        "required": ["group_id", "invitation_seq"],
        "additionalProperties": False,
    },
}

GET_GROUP_FILES_SCHEMA = {
    "name": "get_group_files",
    "description": "查询群文件和文件夹列表；工具不会下载或缓存文件。",
    "parameters": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群号",
            },
            "parent_folder_id": {
                "type": "string",
                "nullable": True,
                "minLength": 1,
                "description": "可选父文件夹 ID",
            },
        },
        "required": ["group_id"],
        "additionalProperties": False,
    },
}

TOOL_SPECS = (
    SEND_PROFILE_LIKE_SCHEMA,
    SEND_FRIEND_NUDGE_SCHEMA,
    GROUP_NUDGE_SCHEMA,
    RECALL_GROUP_MESSAGE_SCHEMA,
    GET_GROUP_INFO_SCHEMA,
    GET_GROUP_MEMBER_LIST_SCHEMA,
    GET_GROUP_MEMBER_INFO_SCHEMA,
    SET_GROUP_MEMBER_MUTE_SCHEMA,
    SET_GROUP_WHOLE_MUTE_SCHEMA,
    GET_FORWARDED_MESSAGES_SCHEMA,
    GET_PRIVATE_FILE_DOWNLOAD_URL_SCHEMA,
    KICK_GROUP_MEMBER_SCHEMA,
    QUIT_GROUP_SCHEMA,
    DELETE_FRIEND_SCHEMA,
    GET_FRIEND_REQUESTS_SCHEMA,
    ACCEPT_FRIEND_REQUEST_SCHEMA,
    REJECT_FRIEND_REQUEST_SCHEMA,
    GET_GROUP_FILE_DOWNLOAD_URL_SCHEMA,
    ACCEPT_GROUP_REQUEST_SCHEMA,
    REJECT_GROUP_REQUEST_SCHEMA,
    ACCEPT_GROUP_INVITATION_SCHEMA,
    REJECT_GROUP_INVITATION_SCHEMA,
    GET_GROUP_FILES_SCHEMA,
)


def bind_sender(sender: MilkyOutboundSender) -> None:
    """绑定生命周期创建的 sender；不在工具注册阶段建立连接。"""

    global _ACTIVE_SENDER
    if not isinstance(sender, MilkyOutboundSender):
        raise TypeError("sender must be a MilkyOutboundSender")
    _ACTIVE_SENDER = sender


def unbind_sender() -> None:
    """清理当前 sender，供断开生命周期使用。"""

    global _ACTIVE_SENDER
    _ACTIVE_SENDER = None


def register_tools(ctx: Any) -> None:
    """向 Hermes 注册与 Milky operationId 对齐的二十三个异步 ToolSpec。"""

    register_tool = getattr(ctx, "register_tool", None)
    if not callable(register_tool):
        return
    handlers: tuple[Callable[..., Any], ...] = (
        _handle_send_profile_like,
        _handle_send_friend_nudge,
        _handle_send_group_nudge,
        _handle_recall_group_message,
        _handle_get_group_info,
        _handle_get_group_member_list,
        _handle_get_group_member_info,
        _handle_set_group_member_mute,
        _handle_set_group_whole_mute,
        _handle_get_forwarded_messages,
        _handle_get_private_file_download_url,
        _handle_kick_group_member,
        _handle_quit_group,
        _handle_delete_friend,
        _handle_get_friend_requests,
        _handle_accept_friend_request,
        _handle_reject_friend_request,
        _handle_get_group_file_download_url,
        _handle_accept_group_request,
        _handle_reject_group_request,
        _handle_accept_group_invitation,
        _handle_reject_group_invitation,
        _handle_get_group_files,
    )
    for spec, handler in zip(TOOL_SPECS, handlers, strict=True):
        register_tool(
            name=spec["name"],
            toolset="milky",
            schema=spec,
            handler=handler,
            check_fn=_tools_available,
            is_async=True,
            description=spec["description"],
            emoji="🪶",
        )


async def _handle_send_profile_like(args: object, **kwargs: Any) -> str:
    """校验并执行名片点赞工具。"""

    del kwargs
    if not _valid_keys(args, {"user_id", "count"}):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values.get("user_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if "count" in values and not _tool_optional_integer(
        values["count"], minimum=0, maximum=9007199254740991
    ):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    if "count" in values:
        return await _execute_action(
            "send_profile_like",
            values,
            lambda: sender.profile_like(values["user_id"], values["count"]),
        )
    return await _execute_action(
        "send_profile_like", values, lambda: sender.profile_like(values["user_id"])
    )


async def _handle_send_friend_nudge(args: object, **kwargs: Any) -> str:
    """校验并执行好友戳一戳工具。"""

    del kwargs
    if not _valid_keys(args, {"user_id", "is_self"}):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values.get("user_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if "is_self" in values and not _tool_optional_bool(values["is_self"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "send_friend_nudge",
        values,
        lambda: sender.nudge(
            f"dm:{values['user_id']}",
            is_self=values.get("is_self"),
        ),
    )


async def _handle_send_group_nudge(args: object, **kwargs: Any) -> str:
    """校验并执行群戳一戳工具。"""

    del kwargs
    if not _valid_keys(args, {"group_id", "user_id"}):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values.get("group_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if not _tool_integer(values.get("user_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "send_group_nudge",
        values,
        lambda: sender.nudge(
            f"group:{values['group_id']}",
            user_id=values["user_id"],
        ),
    )


async def _handle_recall_group_message(args: object, **kwargs: Any) -> str:
    """校验并执行群消息撤回工具。"""

    del kwargs
    if not _valid_keys(args, {"group_id", "message_seq"}):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values.get("group_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if not _tool_integer(values.get("message_seq"), minimum=0, maximum=9007199254740991):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "recall_group_message",
        values,
        lambda: sender.recall_group_message(f"group:{values['group_id']}", values["message_seq"]),
    )


async def _handle_get_group_info(args: object, **kwargs: Any) -> str:
    """校验并执行群信息查询工具。"""

    del kwargs
    if not _valid_keys(args, {"group_id", "no_cache"}):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values.get("group_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if "no_cache" in values and not _tool_optional_bool(values["no_cache"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "get_group_info",
        values,
        lambda: sender.get_group_info(values["group_id"], no_cache=values.get("no_cache", False)),
    )


async def _handle_get_group_member_list(args: object, **kwargs: Any) -> str:
    """校验并执行群成员列表查询工具。"""

    del kwargs
    if not _valid_keys(args, {"group_id", "no_cache"}):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values.get("group_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if "no_cache" in values and not _tool_optional_bool(values["no_cache"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "get_group_member_list",
        values,
        lambda: sender.get_group_member_list(
            values["group_id"], no_cache=values.get("no_cache", False)
        ),
    )


async def _handle_get_group_member_info(args: object, **kwargs: Any) -> str:
    """校验并执行群成员信息查询工具。"""

    del kwargs
    if not _valid_keys(args, {"group_id", "user_id", "no_cache"}):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values.get("group_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if not _tool_integer(values.get("user_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if "no_cache" in values and not _tool_optional_bool(values["no_cache"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "get_group_member_info",
        values,
        lambda: sender.get_group_member_info(
            values["group_id"],
            values["user_id"],
            no_cache=values.get("no_cache", False),
        ),
    )


async def _handle_set_group_member_mute(args: object, **kwargs: Any) -> str:
    """校验并执行群成员禁言工具。"""

    del kwargs
    if not _valid_keys(args, {"group_id", "user_id", "duration"}):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values.get("group_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if not _tool_integer(values.get("user_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if "duration" in values and not _tool_optional_integer(
        values["duration"], minimum=0, maximum=9007199254740991
    ):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    if "duration" in values:
        return await _execute_action(
            "set_group_member_mute",
            values,
            lambda: sender.set_group_member_mute(
                values["group_id"], values["user_id"], values["duration"]
            ),
        )
    return await _execute_action(
        "set_group_member_mute",
        values,
        lambda: sender.set_group_member_mute(values["group_id"], values["user_id"]),
    )


async def _handle_set_group_whole_mute(args: object, **kwargs: Any) -> str:
    """校验并执行群全员禁言工具。"""

    del kwargs
    if not _valid_keys(args, {"group_id", "is_mute"}):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values.get("group_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if "is_mute" in values and not _tool_optional_bool(values["is_mute"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    if "is_mute" in values:
        return await _execute_action(
            "set_group_whole_mute",
            values,
            lambda: sender.set_group_whole_mute(values["group_id"], values["is_mute"]),
        )
    return await _execute_action(
        "set_group_whole_mute", values, lambda: sender.set_group_whole_mute(values["group_id"])
    )


async def _handle_get_forwarded_messages(args: object, **kwargs: Any) -> str:
    """校验并执行合并转发消息查询工具。"""

    del kwargs
    if not _valid_keys(args, {"forward_id"}) or "forward_id" not in args:
        return _tool_error("invalid_input")
    values = args
    if not _tool_string(values["forward_id"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "get_forwarded_messages",
        values,
        lambda: sender.get_forwarded_messages(values["forward_id"]),
    )


async def _handle_get_private_file_download_url(args: object, **kwargs: Any) -> str:
    """校验并执行私聊文件下载链接查询工具。"""

    del kwargs
    allowed = {"user_id", "file_id", "file_hash", "is_self_send"}
    required = {"user_id", "file_id", "file_hash"}
    if not _valid_keys(args, allowed) or not required.issubset(args):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values["user_id"], minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if not _tool_string(values["file_id"]) or not _tool_string(values["file_hash"]):
        return _tool_error("invalid_input")
    if "is_self_send" in values and not _tool_optional_bool(values["is_self_send"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    if "is_self_send" not in values:
        action = lambda: sender.get_private_file_download_url(
            values["user_id"], values["file_id"], values["file_hash"]
        )
    else:
        action = lambda: sender.get_private_file_download_url(
            values["user_id"],
            values["file_id"],
            values["file_hash"],
            is_self_send=values["is_self_send"],
        )
    return await _execute_action(
        "get_private_file_download_url",
        values,
        action,
    )


async def _handle_kick_group_member(args: object, **kwargs: Any) -> str:
    """校验并执行踢出群成员工具。"""

    del kwargs
    allowed = {"group_id", "user_id", "reject_add_request"}
    required = {"group_id", "user_id"}
    if not _valid_keys(args, allowed) or not required.issubset(args):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values["group_id"], minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if not _tool_integer(values["user_id"], minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if "reject_add_request" in values and not _tool_optional_bool(values["reject_add_request"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    if "reject_add_request" not in values:
        action = lambda: sender.kick_group_member(values["group_id"], values["user_id"])
    else:
        action = lambda: sender.kick_group_member(
            values["group_id"],
            values["user_id"],
            reject_add_request=values["reject_add_request"],
        )
    return await _execute_action(
        "kick_group_member",
        values,
        action,
    )


async def _handle_quit_group(args: object, **kwargs: Any) -> str:
    """校验并执行退出群聊工具。"""

    del kwargs
    if not _valid_keys(args, {"group_id"}) or "group_id" not in args:
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values["group_id"], minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "quit_group", values, lambda: sender.quit_group(values["group_id"])
    )


async def _handle_delete_friend(args: object, **kwargs: Any) -> str:
    """校验并执行删除好友工具。"""

    del kwargs
    if not _valid_keys(args, {"user_id"}) or "user_id" not in args:
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values["user_id"], minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "delete_friend", values, lambda: sender.delete_friend(values["user_id"])
    )


async def _handle_get_friend_requests(args: object, **kwargs: Any) -> str:
    """校验并执行好友请求查询工具。"""

    del kwargs
    allowed = {"limit", "is_filtered"}
    if not _valid_keys(args, allowed):
        return _tool_error("invalid_input")
    values = args
    if "limit" in values and not _tool_optional_integer(
        values["limit"], minimum=0, maximum=9007199254740991
    ):
        return _tool_error("invalid_input")
    if "is_filtered" in values and not _tool_optional_bool(values["is_filtered"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "get_friend_requests",
        values,
        lambda: sender.get_friend_requests(
            **{key: values[key] for key in ("limit", "is_filtered") if key in values}
        ),
    )


async def _handle_accept_friend_request(args: object, **kwargs: Any) -> str:
    """校验并执行接受好友请求工具。"""

    del kwargs
    allowed = {"initiator_uid", "is_filtered"}
    if not _valid_keys(args, allowed) or "initiator_uid" not in args:
        return _tool_error("invalid_input")
    values = args
    if not _tool_string(values["initiator_uid"]):
        return _tool_error("invalid_input")
    if "is_filtered" in values and not _tool_optional_bool(values["is_filtered"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "accept_friend_request",
        values,
        lambda: sender.accept_friend_request(
            values["initiator_uid"],
            **({"is_filtered": values["is_filtered"]} if "is_filtered" in values else {}),
        ),
    )


async def _handle_reject_friend_request(args: object, **kwargs: Any) -> str:
    """校验并执行拒绝好友请求工具。"""

    del kwargs
    allowed = {"initiator_uid", "is_filtered", "reason"}
    if not _valid_keys(args, allowed) or "initiator_uid" not in args:
        return _tool_error("invalid_input")
    values = args
    if not _tool_string(values["initiator_uid"]):
        return _tool_error("invalid_input")
    if "is_filtered" in values and not _tool_optional_bool(values["is_filtered"]):
        return _tool_error("invalid_input")
    if "reason" in values and not _tool_optional_string(values["reason"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "reject_friend_request",
        values,
        lambda: sender.reject_friend_request(
            values["initiator_uid"],
            **{key: values[key] for key in ("is_filtered", "reason") if key in values},
        ),
    )


async def _handle_get_group_file_download_url(args: object, **kwargs: Any) -> str:
    """校验并执行群文件下载链接查询工具。"""

    del kwargs
    required = {"group_id", "file_id"}
    if not _valid_keys(args, required) or not required.issubset(args):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values["group_id"], minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if not _tool_string(values["file_id"]):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "get_group_file_download_url",
        values,
        lambda: sender.get_group_file_download_url(values["group_id"], values["file_id"]),
    )


async def _handle_accept_group_request(args: object, **kwargs: Any) -> str:
    """校验并执行接受入群请求工具。"""

    del kwargs
    allowed = {"notification_seq", "notification_type", "group_id", "is_filtered"}
    required = {"notification_seq", "notification_type", "group_id"}
    if not _valid_keys(args, allowed) or not required.issubset(args):
        return _tool_error("invalid_input")
    values = args
    if not _valid_group_request_values(values, allow_reason=False):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "accept_group_request",
        values,
        lambda: sender.accept_group_request(
            values["notification_seq"],
            values["notification_type"],
            values["group_id"],
            **({"is_filtered": values["is_filtered"]} if "is_filtered" in values else {}),
        ),
    )


async def _handle_reject_group_request(args: object, **kwargs: Any) -> str:
    """校验并执行拒绝入群请求工具。"""

    del kwargs
    allowed = {"notification_seq", "notification_type", "group_id", "is_filtered", "reason"}
    required = {"notification_seq", "notification_type", "group_id"}
    if not _valid_keys(args, allowed) or not required.issubset(args):
        return _tool_error("invalid_input")
    values = args
    if not _valid_group_request_values(values, allow_reason=True):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "reject_group_request",
        values,
        lambda: sender.reject_group_request(
            values["notification_seq"],
            values["notification_type"],
            values["group_id"],
            **{key: values[key] for key in ("is_filtered", "reason") if key in values},
        ),
    )


async def _handle_accept_group_invitation(args: object, **kwargs: Any) -> str:
    """校验并执行接受群邀请工具。"""

    del kwargs
    required = {"group_id", "invitation_seq"}
    if not _valid_keys(args, required) or not required.issubset(args):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values["group_id"], minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if not _tool_integer(values["invitation_seq"], minimum=0, maximum=9007199254740991):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "accept_group_invitation",
        values,
        lambda: sender.accept_group_invitation(values["group_id"], values["invitation_seq"]),
    )


async def _handle_reject_group_invitation(args: object, **kwargs: Any) -> str:
    """校验并执行拒绝群邀请工具。"""

    del kwargs
    required = {"group_id", "invitation_seq"}
    if not _valid_keys(args, required) or not required.issubset(args):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values["group_id"], minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if not _tool_integer(values["invitation_seq"], minimum=0, maximum=9007199254740991):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "reject_group_invitation",
        values,
        lambda: sender.reject_group_invitation(values["group_id"], values["invitation_seq"]),
    )


async def _handle_get_group_files(args: object, **kwargs: Any) -> str:
    """校验并执行群文件列表查询工具。"""

    del kwargs
    allowed = {"group_id", "parent_folder_id"}
    if not _valid_keys(args, allowed) or "group_id" not in args:
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values["group_id"], minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if "parent_folder_id" in values and not _tool_optional_nonempty_string(
        values["parent_folder_id"]
    ):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    return await _execute_action(
        "get_group_files",
        values,
        lambda: sender.get_group_files(
            values["group_id"],
            **(
                {"parent_folder_id": values["parent_folder_id"]}
                if "parent_folder_id" in values
                else {}
            ),
        ),
    )


def _valid_group_request_values(values: Mapping[str, object], *, allow_reason: bool) -> bool:
    """校验群请求工具的公共字段。"""

    if not _tool_integer(values.get("notification_seq"), minimum=0, maximum=9007199254740991):
        return False
    if values.get("notification_type") not in ("join_request", "invited_join_request"):
        return False
    if not _tool_integer(values.get("group_id"), minimum=10001, maximum=4294967295):
        return False
    if "is_filtered" in values and not _tool_optional_bool(values["is_filtered"]):
        return False
    return not (
        allow_reason and "reason" in values and not _tool_optional_nonempty_string(values["reason"])
    )


def _tools_available() -> bool:
    """工具 schema 始终可发现，未绑定 sender 时由 handler 安全降级。"""

    return True


def _valid_keys(args: object, allowed: set[str]) -> bool:
    """校验工具参数是对象且没有未声明字段。"""

    return isinstance(args, Mapping) and set(args).issubset(allowed)


def _tool_integer(value: object, *, minimum: int, maximum: int) -> bool:
    """按 ToolSpec 的 integer 类型校验参数，不接受字符串伪装。"""

    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _tool_optional_integer(value: object, *, minimum: int, maximum: int) -> bool:
    """校验允许省略或显式为空的整数参数。"""

    return value is None or _tool_integer(value, minimum=minimum, maximum=maximum)


def _tool_string(value: object) -> bool:
    """校验 Tool 的非空字符串参数。"""

    return isinstance(value, str) and bool(value.strip())


def _tool_optional_string(value: object) -> bool:
    """校验 Tool 的可空字符串参数。"""

    return value is None or isinstance(value, str)


def _tool_optional_nonempty_string(value: object) -> bool:
    """校验允许显式 null 的非空字符串参数。"""

    return value is None or _tool_string(value)


def _tool_optional_bool(value: object) -> bool:
    """校验允许显式为空的布尔参数。"""

    return value is None or isinstance(value, bool)


async def _execute_action(
    tool_name: str, arguments: Mapping[str, object], action: Callable[[], Any]
) -> str:
    """执行固定 Tool，并记录原始业务入参与远端结果。"""

    try:
        result = await action()
        serialized = _serialize_result(result)
        _log_tool_call(tool_name, arguments, result)
        return serialized
    except asyncio.CancelledError:
        raise
    except (ActionError, TypeError, ValueError) as error:
        serialized = _tool_error(_action_classification(error))
        _log_tool_call(tool_name, arguments, serialized)
        return serialized
    except Exception:  # noqa: BLE001 - 工具边界不回显底层异常
        serialized = _tool_error("malformed")
        _log_tool_call(tool_name, arguments, serialized)
        return serialized


def _serialize_result(result: object) -> str:
    """把成功的 Milky envelope 原样转换为 JSON。"""

    if isinstance(result, MilkyEnvelope):
        payload: dict[str, object] = {
            "status": result.status,
            "retcode": result.retcode,
            "data": _json_value(result.data) if result.data is not None else None,
        }
        if result.message is not None:
            payload["message"] = result.message
        if result.wording is not None:
            payload["wording"] = result.wording
        payload.update(_json_value(result.extras))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    success = bool(getattr(result, "success", False))
    payload: dict[str, Any] = {"ok": success}
    if success:
        message_id = getattr(result, "message_id", None)
        if message_id is not None:
            payload["message_id"] = str(message_id)
    else:
        payload["classification"] = getattr(result, "error_kind", None) or "malformed"
        payload["error"] = "Milky tool operation failed"
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _log_tool_call(tool_name: str, arguments: Mapping[str, object], result: object) -> None:
    """记录 Tool 的安全投影，不记录原始结果、理由或认证上下文。"""

    log_event(
        logger,
        "milky_tool_call",
        logging.INFO,
        stage="action",
        tool=tool_name,
        tool_args=_safe_tool_arguments(arguments),
        tool_result=_safe_tool_result(result),
    )


def _safe_tool_arguments(arguments: Mapping[str, object]) -> dict[str, object]:
    """保留 Tool 入参中的可关联 ID、布尔值和数量，不记录自由文本。"""

    safe: dict[str, object] = {}
    id_fields = {
        "user_id",
        "group_id",
        "forward_id",
        "file_id",
        "file_hash",
        "initiator_uid",
        "parent_folder_id",
    }
    boolean_fields = {"is_self", "is_self_send", "reject_add_request", "is_filtered"}
    quantity_fields = {
        "count",
        "limit",
        "duration",
        "message_seq",
        "notification_seq",
        "invitation_seq",
    }
    enum_fields = {"notification_type"}
    for name, value in arguments.items():
        if (
            name in id_fields
            and (
                (isinstance(value, int) and not isinstance(value, bool))
                or (isinstance(value, str) and _SAFE_TOOL_OPAQUE.fullmatch(value))
            )
            or (
                name in boolean_fields
                and (value is None or isinstance(value, bool))
                or name in quantity_fields
                and isinstance(value, int)
                and not isinstance(value, bool)
                or name in enum_fields
                and value in ("join_request", "invited_join_request")
            )
        ):
            safe[name] = value
    return safe


def _safe_tool_result(result: object) -> dict[str, object]:
    """将 Tool 结果投影为只包含结构和数量的安全诊断。"""

    if isinstance(result, MilkyEnvelope):
        projection: dict[str, object] = {
            "status": result.status,
            "retcode": result.retcode,
        }
        data = result.data
        if isinstance(data, Mapping):
            safe_fields = tuple(
                sorted(
                    str(key)
                    for key in data
                    if isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_]+", key)
                )
            )
            projection["data_fields"] = safe_fields
            if isinstance(data.get("messages"), (list, tuple)):
                projection["message_count"] = len(data["messages"])
            if isinstance(data.get("requests"), (list, tuple)):
                projection["request_count"] = len(data["requests"])
            if "download_url" in data:
                projection["has_download_url"] = True
        projection["envelope_field_count"] = len(result.extras)
        return projection
    if isinstance(result, OutboundSendResult):
        return {
            "ok": result.success,
            "classification": result.error_kind or ("accepted" if result.success else "malformed"),
        }
    if isinstance(result, str):
        try:
            value = json.loads(result)
        except json.JSONDecodeError:
            return {"classification": "malformed"}
        if isinstance(value, Mapping):
            classification = value.get("classification")
            allowed_classifications = {
                "invalid_input",
                "unsupported",
                "rejected",
                "http_error",
                "malformed",
                "transport_unknown",
            }
            return {
                "ok": value.get("ok") is True,
                "classification": classification
                if classification in allowed_classifications
                else "accepted",
            }
    return {"classification": "malformed"}


def _json_value(value: object) -> object:
    """将 DTO 和只读映射转换为可安全编码的 JSON 值。"""

    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _action_classification(error: BaseException) -> str:
    """将 Action 异常收敛为工具允许的错误分类。"""

    classification = getattr(error, "classification", None)
    allowed = {
        "invalid_input",
        "rejected",
        "transport_unknown",
        "malformed",
        "unsupported",
        "http_error",
    }
    return classification if classification in allowed else "malformed"


def _tool_error(classification: str) -> str:
    """创建工具本地错误，不回显任何输入值。"""

    return json.dumps(
        {"ok": False, "classification": classification, "error": "tool input is invalid"},
        ensure_ascii=False,
        separators=(",", ":"),
    )


__all__ = [
    "ACCEPT_FRIEND_REQUEST_SCHEMA",
    "ACCEPT_GROUP_INVITATION_SCHEMA",
    "ACCEPT_GROUP_REQUEST_SCHEMA",
    "DELETE_FRIEND_SCHEMA",
    "GET_FORWARDED_MESSAGES_SCHEMA",
    "GET_FRIEND_REQUESTS_SCHEMA",
    "GET_GROUP_FILES_SCHEMA",
    "GET_GROUP_FILE_DOWNLOAD_URL_SCHEMA",
    "GET_GROUP_INFO_SCHEMA",
    "GET_GROUP_MEMBER_INFO_SCHEMA",
    "GET_GROUP_MEMBER_LIST_SCHEMA",
    "GET_PRIVATE_FILE_DOWNLOAD_URL_SCHEMA",
    "KICK_GROUP_MEMBER_SCHEMA",
    "QUIT_GROUP_SCHEMA",
    "RECALL_GROUP_MESSAGE_SCHEMA",
    "REJECT_FRIEND_REQUEST_SCHEMA",
    "REJECT_GROUP_INVITATION_SCHEMA",
    "REJECT_GROUP_REQUEST_SCHEMA",
    "SEND_FRIEND_NUDGE_SCHEMA",
    "SEND_PROFILE_LIKE_SCHEMA",
    "SET_GROUP_MEMBER_MUTE_SCHEMA",
    "SET_GROUP_WHOLE_MUTE_SCHEMA",
    "TOOL_SPECS",
    "bind_sender",
    "register_tools",
    "unbind_sender",
]
