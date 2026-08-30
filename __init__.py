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

    from outbound.standalone import make_standalone_sender

    from .config import load_config
    from .tools import register_tools

    milky_config = load_config()
    register_tools(ctx)
    standalone_sender = make_standalone_sender(milky_config)

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
        env_enablement_fn=lambda: _home_channel_enablement(milky_config),
        cron_deliver_env_var="MILKY_HOME_CHANNEL",
        standalone_sender_fn=standalone_sender,
        max_message_length=4096,
        emoji="🪶",
        pii_safe=True,
        platform_hint="你正在通过 Hermes 的 Milky QQ 平台通信。",
    )


def _home_channel_enablement(config: object) -> dict[str, object] | None:
    """向 Hermes 提供启动时固定的 home channel 元数据。"""

    home_channel = getattr(config, "home_channel", None)
    if not isinstance(home_channel, str) or not home_channel:
        return None
    return {
        "home_channel": {
            "chat_id": home_channel,
            "name": "Milky Home",
        }
    }


__all__ = ["register"]
