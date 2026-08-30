"""Hermes 的 Milky directory plugin 唯一入口。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = str(Path(__file__).resolve().parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

PLATFORM_HINT = (
    "你正在通过 Hermes 的 Milky QQ 平台通信。\n"
    "发送消息时，默认不要自动 @ 用户，也不要自动引用当前消息。只有确实需要时，使用以下 CQ 码：\n"
    "[CQ:at,qq=<uid>]：@指定用户。uid 必须取自当前消息或 channel_context 消息头中的 uid。\n"
    "[CQ:reply,id=<msg_id>]：引用指定消息。msg_id 必须取自当前消息或 channel_context 消息头中的 msg_id。\n"
    "同时 @ 和引用时，将两个 CQ 码连续放在正文前。\n"
    "不要从昵称、正文或记忆猜测 uid/msg_id；没有对应真实字段时不要生成该 CQ 码。\n"
    "需要完整 CQ 码或 QQ 工具说明时，可按需加载插件 skill `hermes-plugin-milky:qq-reference`。"
)


def _register_bundled_skill(ctx: Any) -> None:
    """登记存在的插件自带只读 skill，不写入用户全局目录。"""

    register_skill = getattr(ctx, "register_skill", None)
    skill_path = Path(_PLUGIN_ROOT) / "skills" / "qq-reference" / "SKILL.md"
    if callable(register_skill) and skill_path.is_file():
        register_skill("qq-reference", skill_path)


def register(ctx: Any) -> None:
    """向 Hermes 注册 Milky platform。

    只在 Hermes 提供平台注册接口时注册 platform；import 和 register 阶段不得建立
    网络连接或创建长期后台任务。
    """

    from .config import load_config
    from .tools import register_tools

    milky_config = load_config()
    _register_bundled_skill(ctx)
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
        platform_hint=PLATFORM_HINT,
    )


__all__ = ["register"]
