"""注册与 Milky operationId 对齐的 Hermes Agent 工具。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from typing import Any

from milky.client import ActionError
from milky.models import GroupEntity, GroupMemberInfo, GroupMemberList, MilkyEnvelope

from .sender import (
    MilkyOutboundSender,
)

_ACTIVE_SENDER: MilkyOutboundSender | None = None

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
    """向 Hermes 注册与 Milky operationId 对齐的九个异步 ToolSpec。"""

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
            lambda: sender.profile_like(values["user_id"], values["count"])
        )
    return await _execute_action(lambda: sender.profile_like(values["user_id"]))


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
        lambda: sender.nudge(
            f"dm:{values['user_id']}",
            is_self=values.get("is_self"),
        )
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
        lambda: sender.nudge(
            f"group:{values['group_id']}",
            user_id=values["user_id"],
        )
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
        lambda: sender.recall_group_message(f"group:{values['group_id']}", values["message_seq"])
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
        lambda: sender.get_group_info(values["group_id"], no_cache=values.get("no_cache", False))
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
        lambda: sender.get_group_member_list(
            values["group_id"], no_cache=values.get("no_cache", False)
        )
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
        lambda: sender.get_group_member_info(
            values["group_id"],
            values["user_id"],
            no_cache=values.get("no_cache", False),
        )
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
            lambda: sender.set_group_member_mute(
                values["group_id"], values["user_id"], values["duration"]
            )
        )
    return await _execute_action(
        lambda: sender.set_group_member_mute(values["group_id"], values["user_id"])
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
            lambda: sender.set_group_whole_mute(values["group_id"], values["is_mute"])
        )
    return await _execute_action(lambda: sender.set_group_whole_mute(values["group_id"]))


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


def _tool_optional_bool(value: object) -> bool:
    """校验允许显式为空的布尔参数。"""

    return value is None or isinstance(value, bool)


async def _execute_action(action: Callable[[], Any]) -> str:
    """执行固定 Action 并将异常转换为安全的工具结果。"""

    try:
        return _serialize_result(await action())
    except asyncio.CancelledError:
        raise
    except (ActionError, TypeError, ValueError) as error:
        return _tool_error(_action_classification(error))
    except Exception:  # noqa: BLE001 - 工具边界不回显底层异常
        return _tool_error("malformed")


def _serialize_result(result: object) -> str:
    """把 sender 结果转换为有限且不包含异常正文的 JSON。"""

    if isinstance(result, MilkyEnvelope):
        data: object = result.data if result.data is not None else {}
        return json.dumps(
            {"ok": True, "data": _json_value(data)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if isinstance(result, GroupEntity):
        data = {"group": result}
        return json.dumps(
            {"ok": True, "data": _json_value(data)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if isinstance(result, GroupMemberList):
        data = {"members": result.members}
        return json.dumps(
            {"ok": True, "data": _json_value(data)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if isinstance(result, GroupMemberInfo):
        data = {"member": result.member}
        return json.dumps(
            {"ok": True, "data": _json_value(data)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
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
    "GET_GROUP_INFO_SCHEMA",
    "GET_GROUP_MEMBER_INFO_SCHEMA",
    "GET_GROUP_MEMBER_LIST_SCHEMA",
    "RECALL_GROUP_MESSAGE_SCHEMA",
    "SEND_FRIEND_NUDGE_SCHEMA",
    "SEND_PROFILE_LIKE_SCHEMA",
    "SET_GROUP_MEMBER_MUTE_SCHEMA",
    "SET_GROUP_WHOLE_MUTE_SCHEMA",
    "TOOL_SPECS",
    "bind_sender",
    "register_tools",
    "unbind_sender",
]
