"""Hermes 的 Milky directory plugin 唯一入口。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = str(Path(__file__).resolve().parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from session.identity import BotIdentitySnapshot

PLATFORM_HINT = "You are communicating via Hermes's Milky QQ platform."
PLATFORM_GUIDANCE = (
    "You can send files natively: write MEDIA:/absolute/path/to/file in your response. "
    "For Hermes `send_message`, put the same directive in its `message` argument; images, audio, video, and documents use Milky's native media/file upload. "
    "MEDIA: is separate from the fixed QQ ToolSpec list. "
    "Use [CQ:at,qq=<uid>] to mention users and [CQ:reply,id=<msg_id>] to quote to messages; use only real IDs from the current message or channel context. "
    "Never send a raw local path as chat text or report media as unsupported before the send entry point fails. "
    "Load `hermes-plugin-milky:qq-reference` for CQ details or `hermes-plugin-milky:qq-tools` for QQ tools."
)
MILKY_PROMPT_SECTION_ID = "hermes-plugin-milky.qq-platform-guidance"


def _render_platform_guidance(identity_snapshot: BotIdentitySnapshot, _session_info: object) -> str:
    """只从注册级身份快照渲染 Milky system prompt section。"""

    identity = identity_snapshot.read()
    if identity is None:
        return ""
    return (
        f"Your QQ uid is {identity.self_id}, and your nickname is {identity.nickname}.\n"
        f"{PLATFORM_GUIDANCE}"
    )


def _register_platform_guidance(ctx: Any, identity_snapshot: BotIdentitySnapshot) -> None:
    """在宿主支持时登记连接后渲染的 Milky system prompt section。"""

    register_section = getattr(ctx, "register_system_prompt_section", None)
    if not callable(register_section):
        return
    register_section(
        id=MILKY_PROMPT_SECTION_ID,
        content=lambda session_info: _render_platform_guidance(identity_snapshot, session_info),
        position="after_memory",
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


def register_tools(ctx: Any) -> None:
    """注册明确的 Milky ToolSpec，不在注册阶段创建网络连接。"""

    try:
        from outbound.tools import register_tools as register_outbound_tools
    except ImportError:
        from .outbound.tools import register_tools as register_outbound_tools

    register_outbound_tools(ctx)


def register(ctx: Any) -> None:
    """向 Hermes 注册 Milky platform。

    只在 Hermes 提供平台注册接口时注册 platform；import 和 register 阶段不得建立
    网络连接或创建长期后台任务。
    """

    from outbound.standalone import make_standalone_sender

    from .config import load_config
    from .slash_commands import SlashCommandService

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

    identity_snapshot = BotIdentitySnapshot()
    _register_platform_guidance(ctx, identity_snapshot)

    register_platform(
        name="milky",
        label="Milky",
        adapter_factory=lambda platform_config: MilkyAdapter(
            platform_config,
            milky_config=milky_config,
            slash_command_service=command_service,
            identity_snapshot=identity_snapshot,
        ),
        check_fn=lambda: True,
        validate_config=lambda _platform_config: True,
        required_env=["MILKY_BASE_URL", "MILKY_ACCESS_TOKEN"],
        env_enablement_fn=lambda: _home_channel_enablement(milky_config),
        cron_deliver_env_var="MILKY_HOME_CHANNEL",
        standalone_sender_fn=standalone_sender,
        max_message_length=4096,
        emoji="🐧",
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
