"""Hermes Agent 工具发现入口。"""

from __future__ import annotations

from typing import Any


def register_tools(ctx: Any) -> None:
    """为 Hermes 保留显式 ToolSpec 注册入口。

    三个 Milky ToolSpec 及其参数校验属于后续出站任务；当前只保持注册阶段
    可安全导入且没有网络或长期后台任务。
    """

    del ctx


__all__ = ["register_tools"]
