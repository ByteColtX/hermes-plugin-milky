"""Hermes Agent 工具发现入口。"""

from __future__ import annotations

from typing import Any


def register_tools(ctx: Any) -> None:
    """注册三个明确的 Milky ToolSpec，不在注册阶段创建网络连接。"""

    try:
        from outbound.tools import register_tools as register_outbound_tools
    except ImportError:
        from .outbound.tools import register_tools as register_outbound_tools

    register_outbound_tools(ctx)


__all__ = ["register_tools"]
