"""Milky 日志消息的普通文本渲染。"""

from __future__ import annotations

from collections.abc import Mapping


def render_event(event: str, fields: Mapping[str, object] | None = None, **kwargs: object) -> str:
    """把固定事件标签和调用方提供的低敏字段渲染成一条普通消息。

    这里不做 payload 脱敏、字段白名单、异常检查或日志后端管理；调用方负责只传入已经
    确认可以用于运维关联的值。Hermes logger 负责接收和路由这些字段，其他 Tool、模型
    上下文和 session 出口不由本函数统一清洗。
    """

    values = dict(fields or {})
    values.update(kwargs)
    parts = [f"event={event}"]
    parts.extend(f"{name}={value}" for name, value in values.items() if value is not None)
    return " ".join(parts)


__all__ = ["render_event"]
