"""用本地真实 Hermes 分发器执行无网络白名单契约，全部设置位于临时目录。"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HERMES_ROOT = Path(
    os.environ.get("HERMES_SOURCE_ROOT", "/Users/bytecolt/PythonProjects/hermes-agent")
)


def main():
    """隔离宿主配置并禁止网络，执行真实注册与分发。"""
    sys.path[:0] = [str(PLUGIN_ROOT), str(HERMES_ROOT)]
    with tempfile.TemporaryDirectory(prefix="milky-allowlist-contract-") as directory:
        os.environ["HERMES_HOME"] = directory
        os.environ["MILKY_BASE_URL"] = "http://127.0.0.1:4000"
        os.environ["MILKY_ACCESS_TOKEN"] = "synthetic-token"
        asyncio.run(checks(Path(directory).resolve()))
    print("real Hermes allowlist dispatch contract: passed (no Milky network)")


async def checks(home):
    """复用 core 权限、别名、插件 handler 和会话作用域代码。"""
    from unittest.mock import patch

    from gateway.config import GatewayConfig, Platform, PlatformConfig
    from gateway.platforms.event import MessageEvent, MessageType
    from gateway.run import GatewayRunner
    from gateway.session import SessionSource
    from hermes_cli import plugins
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    from management.allowlist import AllowlistManager, current_invocation
    from management.profile import ProfileSettings
    from slash_commands import SlashCommandService
    from state.chat_policy import ChatPolicy

    def no_network(*_args, **_kwargs):
        raise AssertionError("contract attempted network")

    class Tracker:
        """只替换 Milky 状态查询边界，记录是否越过 core 拒绝。"""

        def __init__(self):
            self.calls = []

        async def prepare_group(self, group_id):
            self.calls.append(group_id)
            return True

        async def prepare_rules(self, rules):
            self.calls.append(rules)
            return True

        def gate_snapshot(self, _group_id):
            return "unmuted", "unknown"

        def is_muted(self, _group_id):
            return False

    token = set_hermes_home_override(home)
    try:
        manager = PluginManager(scope_key=str(home))
        manager._discovered = True
        context = PluginContext(
            PluginManifest(name="hermes-plugin-milky", key="hermes-plugin-milky", source="user"),
            manager,
        )
        service = SlashCommandService()
        context.register_command("milky", service.handle)
        context.register_platform("milky", "Milky", lambda _: None, lambda: True)
        plugins._plugin_managers_by_home[home.resolve()] = manager
        plugins._plugin_manager = manager
        policy, tracker, store = ChatPolicy(), Tracker(), ProfileSettings()
        control = AllowlistManager(policy, store, policy.publish)
        control.start()
        service.bind_manager(control)
        runner = object.__new__(GatewayRunner)
        runner.config = GatewayConfig()
        runner._draining = False
        runner.adapters = {}
        runner._session_key_for_source = lambda source: "contract:" + source.chat_id

        async def emit(*_args):
            return []

        runner.hooks = SimpleNamespace(emit_collect=emit)
        platform = Platform("milky")
        for chat_type, chat_id in [("dm", "dm:123"), ("group", "group:123")]:
            source = SessionSource(
                platform=platform,
                chat_id=chat_id,
                chat_type=chat_type,
                user_id="456",
                profile="default",
            )
            admin_key = "allow_admin_from" if chat_type == "dm" else "group_allow_admin_from"
            user_key = (
                "user_allowed_commands" if chat_type == "dm" else "group_user_allowed_commands"
            )
            for extra, allowed in [
                ({}, True),
                ({admin_key: ["999"]}, False),
                ({admin_key: ["999"], user_key: ["milky"]}, True),
            ]:
                runner.config.platforms[platform] = PlatformConfig(enabled=True, extra=extra)
                event = MessageEvent(
                    text="/milky allowlist add",
                    message_type=MessageType.COMMAND,
                    source=source,
                    allow_gateway_control=True,
                )
                before = (len(tracker.calls), store.read()["version"])
                invocation_token = current_invocation.set(control.invocation(chat_id))
                try:
                    with patch.object(socket.socket, "connect", no_network):
                        handled, result = await runner._hm_dispatch_idle_commands(
                            event, source, "contract:" + chat_id
                        )
                finally:
                    current_invocation.reset(invocation_token)
                assert handled
                if allowed:
                    assert result.startswith(("已添加白名单规则", "规则已存在")), result
                else:
                    assert "admin-only" in result
                    assert before == (len(tracker.calls), store.read()["version"])
            runner.config.quick_commands = {
                "acl": {"type": "alias", "target": "/milky allowlist list"}
            }
            event = MessageEvent(
                text="/acl",
                message_type=MessageType.COMMAND,
                source=source,
                allow_gateway_control=True,
            )
            invocation_token = current_invocation.set(control.invocation(chat_id))
            try:
                handled, result = await runner._hm_dispatch_idle_commands(
                    event, source, "contract:" + chat_id
                )
                assert handled and "白名单" in result, result
            finally:
                current_invocation.reset(invocation_token)
        assert store.allowed_chats() == {"dm:123", "group:123"}
        other = home / "other-profile"
        other.mkdir()
        other_token = set_hermes_home_override(other)
        try:
            assert not store.is_current()
            # 绑定读取器仍属于原 profile，而管理操作拒绝借用它。
            assert store.allowed_chats() == {"dm:123", "group:123"}
        finally:
            reset_hermes_home_override(other_token)

        await control.close()
    finally:
        reset_hermes_home_override(token)


if __name__ == "__main__":
    main()
