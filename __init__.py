"""Hermes 的 Milky directory plugin 唯一入口。"""

from __future__ import annotations

from typing import Any


def register(ctx: Any) -> None:
    """向 Hermes 注册 Milky platform。

    当前先解析启动配置并建立安全的工具发现边界。Milky Adapter 的依赖组装会在后续
    任务中补充；import 和 register 阶段不得建立网络连接或创建长期后台任务。
    """

    from .config import load_config
    from .tools import register_tools

    load_config()
    register_tools(ctx)


__all__ = ["register"]
