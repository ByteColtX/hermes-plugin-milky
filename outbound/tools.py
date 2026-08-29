"""注册 Milky v0.1 明确允许的三个 Hermes Agent 工具。"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from .formatter import OutboundFormatError
from .sender import (
    MilkyOutboundSender,
    OutboundSendResult,
    parse_outbound_target,
)

_ACTIVE_SENDER: MilkyOutboundSender | None = None

PROFILE_LIKE_SCHEMA = {
    "name": "milky_profile_like",
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
                "description": "可选点赞数量",
            },
        },
        "required": ["user_id"],
        "additionalProperties": False,
    },
}

NUDGE_SCHEMA = {
    "name": "milky_nudge",
    "description": "向 dm:<QQ号> 或 group:<群号> 目标发送戳一戳。",
    "parameters": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "pattern": "^(dm|group):[0-9]+$",
                "description": "完整目标 chat key",
            },
            "user_id": {
                "type": "integer",
                "minimum": 10001,
                "maximum": 4294967295,
                "description": "群目标中的被戳成员 QQ 号；dm 目标省略",
            },
            "is_self": {
                "type": "boolean",
                "description": "dm 目标是否戳自己",
            },
        },
        "required": ["target"],
        "additionalProperties": False,
    },
}

RECALL_SCHEMA = {
    "name": "milky_recall_group_message",
    "description": "撤回指定群消息；目标和远端消息序号必须明确提供。",
    "parameters": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "pattern": "^group:[0-9]+$",
                "description": "群目标 chat key",
            },
            "message_seq": {
                "type": "integer",
                "minimum": 0,
                "maximum": 9007199254740991,
                "description": "Milky 远端消息序号",
            },
        },
        "required": ["target", "message_seq"],
        "additionalProperties": False,
    },
}

TOOL_SPECS = (PROFILE_LIKE_SCHEMA, NUDGE_SCHEMA, RECALL_SCHEMA)


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
    """向 Hermes 注册固定的三个异步 ToolSpec。"""

    register_tool = getattr(ctx, "register_tool", None)
    if not callable(register_tool):
        return
    handlers: tuple[Callable[..., Any], ...] = (
        _handle_profile_like,
        _handle_nudge,
        _handle_recall,
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


async def _handle_profile_like(args: object, **kwargs: Any) -> str:
    """校验并执行名片点赞工具。"""

    del kwargs
    if not _valid_keys(args, {"user_id", "count"}):
        return _tool_error("invalid_input")
    values = args
    if not _tool_integer(values.get("user_id"), minimum=10001, maximum=4294967295):
        return _tool_error("invalid_input")
    if "count" in values and not _tool_integer(
        values["count"], minimum=0, maximum=9007199254740991
    ):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    if "count" in values:
        result = await sender.profile_like(values.get("user_id"), values["count"])
    else:
        result = await sender.profile_like(values.get("user_id"))
    return _serialize_result(result)


async def _handle_nudge(args: object, **kwargs: Any) -> str:
    """校验并执行好友或群戳一戳工具。"""

    del kwargs
    if not _valid_keys(args, {"target", "user_id", "is_self"}):
        return _tool_error("invalid_input")
    values = args
    try:
        target = parse_outbound_target(values.get("target"))
    except OutboundFormatError as error:
        return _tool_error(error.classification)
    if "user_id" in values and not _tool_integer(
        values["user_id"], minimum=10001, maximum=4294967295
    ):
        return _tool_error("invalid_input")
    if "is_self" in values and not isinstance(values["is_self"], bool):
        return _tool_error("invalid_input")
    if target.scene == "group" and "user_id" not in values:
        return _tool_error("invalid_input")
    if target.scene == "dm" and "user_id" in values:
        return _tool_error("invalid_input")
    if target.scene == "group" and "is_self" in values:
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    result = await sender.nudge(
        values.get("target"),
        user_id=values.get("user_id"),
        is_self=values.get("is_self"),
    )
    return _serialize_result(result)


async def _handle_recall(args: object, **kwargs: Any) -> str:
    """校验并执行群消息撤回工具。"""

    del kwargs
    if not _valid_keys(args, {"target", "message_seq"}):
        return _tool_error("invalid_input")
    values = args
    try:
        target = parse_outbound_target(values.get("target"))
    except OutboundFormatError as error:
        return _tool_error(error.classification)
    if target.scene != "group" or not _tool_integer(
        values.get("message_seq"), minimum=0, maximum=9007199254740991
    ):
        return _tool_error("invalid_input")
    sender = _ACTIVE_SENDER
    if sender is None:
        return _tool_error("unsupported")
    result = await sender.recall_group_message(values.get("target"), values.get("message_seq"))
    return _serialize_result(result)


def _tools_available() -> bool:
    """工具 schema 始终可发现，未绑定 sender 时由 handler 安全降级。"""

    return True


def _valid_keys(args: object, allowed: set[str]) -> bool:
    """校验工具参数是对象且没有未声明字段。"""

    return isinstance(args, Mapping) and set(args).issubset(allowed)


def _tool_integer(value: object, *, minimum: int, maximum: int) -> bool:
    """按 ToolSpec 的 integer 类型校验参数，不接受字符串伪装。"""

    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _serialize_result(result: OutboundSendResult) -> str:
    """把 sender 结果转换为有限且不包含异常正文的 JSON。"""

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


def _tool_error(classification: str) -> str:
    """创建工具本地错误，不回显任何输入值。"""

    return json.dumps(
        {"ok": False, "classification": classification, "error": "tool input is invalid"},
        ensure_ascii=False,
        separators=(",", ":"),
    )


__all__ = [
    "NUDGE_SCHEMA",
    "PROFILE_LIKE_SCHEMA",
    "RECALL_SCHEMA",
    "TOOL_SPECS",
    "bind_sender",
    "register_tools",
    "unbind_sender",
]
