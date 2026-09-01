"""Hermes 的 Milky directory plugin 唯一入口。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = str(Path(__file__).resolve().parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

PLATFORM_HINT = (
    "You are sending and receiving messages via Hermes's Milky QQ platform.\n"
    "Use `at` to explicitly notify a user, in the format [CQ:at,qq=<uid>]; use `reply` to reply to a specific message, "
    "in the format [CQ:reply,id=<msg_id>] (e.g. task-completion notices, answers to questions).\n"
    "When both are needed, place them at the very start of the message in the order reply, then at; otherwise, send plain text only.\n"
    "uid and msg_id must come only from real decimal fields in the current message or channel_context — never guess them or use qq=all.\n"
    "Load the plugin skill `hermes-plugin-milky:qq-reference` as needed for CQ code details, "
    "and `hermes-plugin-milky:qq-tools` as needed for QQ tool usage."
)


def _register_bundled_skill(ctx: Any) -> None:
    """登记存在的插件自带只读 skill，不写入用户全局目录。"""

    register_skill = getattr(ctx, "register_skill", None)
    if not callable(register_skill):
        return

    for skill_name in ("qq-reference", "qq-tools"):
        skill_path = Path(_PLUGIN_ROOT) / "skills" / skill_name / "SKILL.md"
        if skill_path.is_file():
            register_skill(skill_name, skill_path)


def register(ctx: Any) -> None:
    """向 Hermes 注册 Milky platform。

    只在 Hermes 提供平台注册接口时注册 platform；import 和 register 阶段不得建立
    网络连接或创建长期后台任务。
    """

    from outbound.standalone import make_standalone_sender

    from .config import load_config
    from .slash_commands import SlashCommandService
    from .tools import register_tools

    milky_config = load_config()
    command_service = SlashCommandService()
    _register_bundled_skill(ctx)
    register_tools(ctx)
    register_command = getattr(ctx, "register_command", None)
    if callable(register_command):
        register_command(
            "milky",
            command_service.handle,
            description="Show Milky implementation information",
            args_hint="",
        )
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
            slash_command_service=command_service,
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
        platform_hint=PLATFORM_HINT,
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
