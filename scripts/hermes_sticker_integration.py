"""在隔离的真实 Hermes 注册器中检查贴纸工具契约。"""

import asyncio
import base64
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


def main() -> None:
    """使用真实宿主组件和临时合成库验证工具发现与回执交付。"""

    plugin_root = Path(__file__).resolve().parents[1]
    hermes_root = Path(
        os.environ.get("HERMES_SOURCE_ROOT", "/Users/bytecolt/PythonProjects/hermes-agent")
    ).resolve()
    sys.path[:0] = [str(plugin_root), str(hermes_root)]
    with tempfile.TemporaryDirectory(prefix="milky-sticker-host-") as directory:
        os.environ["HERMES_HOME"] = directory
        os.environ["MILKY_BASE_URL"] = "https://localhost:5500/milky"
        os.environ["MILKY_ACCESS_TOKEN"] = "synthetic-token"
        from gateway.session_context import clear_session_vars, set_session_vars
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        from tools.registry import invalidate_check_fn_cache, registry

        manager = PluginManager(scope_key=registry.current_scope_key())
        manager._discovered = True
        context = PluginContext(
            PluginManifest(name="hermes-plugin-milky", key="hermes-plugin-milky", source="user"),
            manager,
        )
        spec = importlib.util.spec_from_file_location(
            "hermes_plugins.milky_sticker_probe",
            plugin_root / "__init__.py",
            submodule_search_locations=[str(plugin_root)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.register(context)
        search = registry.get_entry("sticker_search", scope=manager.scope_key)
        send = registry.get_entry("sticker_send", scope=manager.scope_key)
        assert search is not None and send is not None
        assert search.check_fn() is False
        root = Path(directory) / "plugin-data" / "hermes-plugin-milky"
        assert not root.exists()
        from stickers.maintenance import StickerMaintenanceService

        inbox = root / "stickers" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "one.png").write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        )

        def vision(*_args, **_kwargs):
            """返回合成视觉结果，不调用远端服务。"""
            return json.dumps(
                {
                    "success": True,
                    "analysis": json.dumps(
                        {
                            "emotion": "joy",
                            "tags": ["开心", "反应"],
                            "description": "表达开心",
                            "is_sticker": True,
                        }
                    ),
                }
            )

        maintenance = StickerMaintenanceService(data_dir=root, vision_analyzer=vision)
        maintenance_result = json.loads(asyncio.run(maintenance.handle("sticker add")))
        assert maintenance_result["created"] == 1
        from outbound.sender import MilkyOutboundSender
        from outbound.tools import bind_sender, unbind_sender

        class NoNetwork:
            """任何网络 Action 都使本地契约验证失败。"""

            async def call_action(self, *_args, **_kwargs):
                """阻止契约探针发送真实消息。"""
                raise AssertionError("搜索与无匹配不允许 Action")

        bind_sender(MilkyOutboundSender(NoNetwork()))
        for session in ("synthetic-first", "synthetic-new"):
            tokens = set_session_vars(
                platform="milky", chat_id="group:700000001", session_id=session
            )
            try:
                invalidate_check_fn_cache()
                definitions = registry.get_definitions({"sticker_search", "sticker_send"})
                assert len(definitions) == 2
                schema = next(
                    d["function"]["parameters"]
                    for d in definitions
                    if d["function"]["name"] == "sticker_search"
                )
                assert schema["properties"]["mode"]["enum"] == ["strict", "fallback", "browse"]
                results = []
                for args, mode in [
                    ({"intent": "unmatchedsynthetic", "emotion": "joy"}, "strict"),
                    (
                        {"mode": "fallback", "intent": "unmatchedsynthetic", "emotion": "joy"},
                        "fallback",
                    ),
                    ({}, "browse"),
                ]:
                    raw = asyncio.run(search.handler(args))
                    delivered = registry._normalize_handler_result("sticker_search", raw)
                    result = json.loads(delivered)
                    assert result["match_mode"] == mode
                    assert result["status"] == ("no_match" if mode == "strict" else "ok")
                    results.append(result)
                raw = asyncio.run(send.handler({"intent": "unmatchedsynthetic", "emotion": "joy"}))
                result = json.loads(registry._normalize_handler_result("sticker_send", raw))
                assert result == {"status": "no_match", "alternatives": results[1]["items"]}
            finally:
                clear_session_vars(tokens)
        unbind_sender()
        print(
            "real Hermes root registration, definitions in two sessions, three modes and no_match result delivery: passed; synthetic library, no network"
        )


if __name__ == "__main__":
    main()
