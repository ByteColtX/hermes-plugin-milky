"""Hermes 原生 Milky 平台 adapter 的注册入口。"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from typing import Any

_PLUGIN_ROOT = str(Path(__file__).resolve().parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from session import BotIdentitySnapshot, ChatMetadataSnapshotStore, render_current_session_context

PLATFORM_HINT = "You are chatting on QQ through Hermes's Milky platform."

PLATFORM_GUIDANCE = """
* To send a local image, audio, video, or document, put `MEDIA:/absolute/path/to/file` in your reply or in the `message` argument of `send_message`.
* A bare local path is sent as text. Try native sending before declaring media unsupported.
* If no final reply is needed, return only `[SILENT]` with no extra content.
* To send a reply as separate chat messages, place `[SPLIT]` between text sections, inline or on its own line. Use at most 2 markers for up to 3 messages; the markers are removed before sending.
* Mention a user with `[CQ:at,qq=<uid>]`. Literal `@sender_name` is not parsed as a valid mention.
* Quote a message with `[CQ:reply,id=<msg_seq>]`. Use `id=`, never `id:`.
* Use real `uid` and `msg_seq` values from the conversation for mentions and quotes; omit the tag if the required ID is unavailable.
* Incoming message headers are metadata; do not copy them into replies.
* For CQ syntax details, view skill `hermes-plugin-milky:milky-qq-cq-reference`.
* For QQ action tools, view skill `hermes-plugin-milky:milky-qq-action-tools`.
"""

MILKY_PROMPT_SECTION_ID = "hermes-plugin-milky.qq-platform-guidance"
MILKY_SESSION_CONTEXT_SECTION_ID = "hermes-plugin-milky.qq-session-context"


def _render_platform_guidance(profile_snapshots: _ProfileSnapshots, session_info: object) -> str:
    """只读取当前 session 所属 profile 的身份快照。"""
    if not isinstance(session_info, Mapping):
        return ""
    profile_name = session_info.get("profile_name")
    if not isinstance(profile_name, str):
        return ""
    identity_snapshot, _session_context_store = profile_snapshots.get(profile_name)
    if identity_snapshot is None:
        return ""
    identity = identity_snapshot.read()
    if identity is None:
        return ""
    return (
        f"- Your QQ uid is {identity.self_id}, and your nickname is {identity.nickname}.\n"
        f"{PLATFORM_GUIDANCE}"
    )


def _register_platform_guidance(ctx: Any, profile_snapshots: _ProfileSnapshots) -> None:
    """登记连接后渲染的 Milky system prompt section。"""

    ctx.register_system_prompt_section(
        id=MILKY_PROMPT_SECTION_ID,
        content=lambda session_info: _render_platform_guidance(profile_snapshots, session_info),
        position="after_memory",
    )


def _render_session_context(profile_snapshots: _ProfileSnapshots, session_info: object) -> str:
    """只从当前 session 所属 profile 的本地快照渲染 QQ 会话介绍。"""

    if not isinstance(session_info, Mapping):
        return ""
    profile_name = session_info.get("profile_name")
    if not isinstance(profile_name, str):
        return ""
    _identity_snapshot, session_context_store = profile_snapshots.get(profile_name)
    if session_context_store is None:
        return ""
    return render_current_session_context(session_context_store)


def _register_session_context(ctx: Any, profile_snapshots: _ProfileSnapshots) -> None:
    """登记无网络的 QQ 会话介绍 section。"""

    ctx.register_system_prompt_section(
        id=MILKY_SESSION_CONTEXT_SECTION_ID,
        content=lambda session_info: _render_session_context(profile_snapshots, session_info),
        position="after_memory",
    )


class _ProfileSnapshots:
    """保留每个 Hermes profile 独立的 adapter 提示快照。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._stores: dict[str, tuple[BotIdentitySnapshot, ChatMetadataSnapshotStore]] = {}

    def for_active_profile(self) -> tuple[BotIdentitySnapshot, ChatMetadataSnapshotStore]:
        """按 Hermes 当前作用域取得 profile 的快照，不能退回注册 profile。"""
        try:
            from hermes_cli.profiles import get_active_profile_name

            profile_name = get_active_profile_name()
        except Exception:  # noqa: BLE001 - profile 无法确认时拒绝创建 adapter
            raise RuntimeError("Milky profile scope is unavailable") from None
        if not isinstance(profile_name, str) or not profile_name:
            raise RuntimeError("Milky profile scope is unavailable")
        with self._lock:
            stores = self._stores.get(profile_name)
            if stores is None:
                stores = (BotIdentitySnapshot(), ChatMetadataSnapshotStore())
                self._stores[profile_name] = stores
            return stores

    def get(
        self, profile_name: str
    ) -> tuple[BotIdentitySnapshot | None, ChatMetadataSnapshotStore | None]:
        """只查已创建的 profile 快照，不根据缺失 session 信息猜测。"""
        with self._lock:
            return self._stores.get(profile_name, (None, None))


def _register_bundled_skill(ctx: Any) -> None:
    """登记存在的插件自带只读 skill，不写入用户全局目录。"""

    register_skill = getattr(ctx, "register_skill", None)
    if not callable(register_skill):
        return

    for skill_name in ("milky-qq-cq-reference", "milky-qq-action-tools"):
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

    必需的平台与 prompt 注册 API 缺失时明确失败；import 和 register 阶段不得建立
    网络连接或创建长期后台任务。
    """

    required_apis = ("register_platform", "register_system_prompt_section")
    missing_apis = [name for name in required_apis if not callable(getattr(ctx, name, None))]
    if missing_apis:
        missing = ", ".join(missing_apis)
        raise RuntimeError(
            "Milky platform unsupported: Hermes plugin context is missing required API(s): "
            f"{missing}"
        )

    from management.profile import ProfileSettings
    from outbound.standalone import make_standalone_sender

    from .config import load_config
    from .slash_commands import SlashCommandService
    from .stickers import StickerMaintenanceService

    profile_settings = ProfileSettings()
    command_service = SlashCommandService(StickerMaintenanceService(plugin_context=ctx))
    _register_bundled_skill(ctx)
    register_tools(ctx)
    register_command = getattr(ctx, "register_command", None)
    if callable(register_command):
        register_command(
            "milky",
            command_service.handle,
            description="Milky 实现信息、运行状态、贴纸维护与白名单管理；help 查看帮助",
            args_hint="[command] [args...]",
        )
    standalone_sender = make_standalone_sender()

    from .adapter import MilkyAdapter

    profile_snapshots = _ProfileSnapshots()
    _register_platform_guidance(ctx, profile_snapshots)
    _register_session_context(ctx, profile_snapshots)

    def adapter_factory(platform_config: object) -> object:
        """在目标 adapter 的活动 profile 中构造依赖。"""
        identity_snapshot, session_context_store = profile_snapshots.for_active_profile()
        return MilkyAdapter(
            platform_config,
            milky_config=load_config(),
            allowed_chats_reader=profile_settings.allowed_chats,
            profile_settings=profile_settings,
            plugin_context=ctx,
            slash_command_service=command_service,
            identity_snapshot=identity_snapshot,
            session_context_store=session_context_store,
        )

    ctx.register_platform(
        name="milky",
        label="Milky",
        adapter_factory=adapter_factory,
        check_fn=lambda: True,
        validate_config=lambda _platform_config: True,
        required_env=[],
        env_enablement_fn=lambda: _home_channel_enablement(load_config()),
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
