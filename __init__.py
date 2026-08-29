"""Hermes 的 Milky directory plugin 唯一入口。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = str(Path(__file__).resolve().parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)


def register(ctx: Any) -> None:
    """向 Hermes 注册 Milky platform。

    只在 Hermes 提供平台注册接口时注册 platform；import 和 register 阶段不得建立
    网络连接或创建长期后台任务。
    """

    from .config import load_config
    from .tools import register_tools

    milky_config = load_config()
    register_tools(ctx)

    register_platform = getattr(ctx, "register_platform", None)
    if not callable(register_platform):
        return

    from .adapter import MilkyAdapter

    register_platform(
        name="milky",
        label="Milky",
        adapter_factory=lambda platform_config: MilkyAdapter(
            platform_config,
            milky_config=milky_config,
        ),
        check_fn=lambda: True,
        validate_config=lambda _platform_config: True,
        required_env=["MILKY_BASE_URL", "MILKY_ACCESS_TOKEN"],
        max_message_length=4096,
        emoji="🪶",
        pii_safe=True,
        platform_hint="你正在通过 Hermes 的 Milky QQ 平台通信。",
    )


__all__ = ["register"]
