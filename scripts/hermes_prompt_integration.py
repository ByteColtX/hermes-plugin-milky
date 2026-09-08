"""在真实 Hermes 源码环境中验证 Milky prompt section 的缓存边界。"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HERMES_ROOT = Path(
    os.environ.get("HERMES_SOURCE_ROOT", "/Users/bytecolt/PythonProjects/hermes-agent")
).resolve()


def _load_plugin() -> object:
    """按 Hermes directory plugin 的 namespaced 方式加载根入口。"""

    module_name = "hermes_plugins.hermes_plugin_milky_prompt_integration"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PLUGIN_ROOT / "__init__.py",
        submodule_search_locations=[str(PLUGIN_ROOT)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 Milky plugin 入口")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    """执行受控的真实 Hermes section、restore 和 rebuild 检查。"""

    if sys.version_info < (3, 13):  # noqa: UP036 - external host may use an older interpreter
        raise RuntimeError("真实集成需要 Python 3.13+")
    if not (HERMES_ROOT / "hermes_cli" / "plugins.py").is_file():
        raise RuntimeError(f"Hermes 源码目录不存在: {HERMES_ROOT}")
    sys.path.insert(0, str(HERMES_ROOT))
    sys.path.insert(0, str(PLUGIN_ROOT))
    with tempfile.TemporaryDirectory(prefix="milky-hermes-prompt-") as temp_dir:
        os.environ["HERMES_HOME"] = temp_dir
        os.environ.setdefault("MILKY_BASE_URL", "https://localhost:5500/milky")
        os.environ.setdefault("MILKY_ACCESS_TOKEN", "integration-fixture-token")
        _run_checks(Path(temp_dir))
    print("real Hermes prompt integration: passed")


def _run_checks(temp_dir: Path) -> None:
    """创建真实 PluginContext/AIAgent 并验证 prompt 生命周期。"""

    from agent import coding_context
    from agent.conversation_loop import _restore_or_build_system_prompt
    from agent.system_prompt import build_system_prompt, invalidate_system_prompt
    from gateway.session_context import clear_session_vars, set_session_vars
    from hermes_cli import plugins
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
    from hermes_state import SessionDB
    from run_agent import AIAgent

    from session import ChatMetadataSnapshotStore, GroupSessionMetadata

    coding_context.build_coding_workspace_block = lambda cwd=None: "Pinned workspace"  # type: ignore[assignment]
    manager = PluginManager(scope_key=str(temp_dir))
    manager._discovered = True
    context = PluginContext(
        PluginManifest(
            name="hermes-plugin-milky",
            key="hermes-plugin-milky",
            source="user",
        ),
        manager,
    )
    entry = _load_plugin()
    # This host checkout predates dynamic Platform enum members. Register the
    # same root-owned sections directly so the real Hermes section renderer,
    # prompt cache and persistence paths remain under test without depending
    # on the unrelated platform registry compatibility layer.
    store = ChatMetadataSnapshotStore()
    entry._register_platform_guidance(context, entry.BotIdentitySnapshot())
    entry._register_session_context(context, store)
    plugins._plugin_manager = manager

    section = manager._system_prompt_sections[entry.MILKY_SESSION_CONTEXT_SECTION_ID]

    tokens = set_session_vars(chat_id="group:700000001", session_id="prompt-integration")
    db_path = temp_dir / "state.db"
    db = SessionDB(db_path=db_path)
    session_id = "prompt-integration"
    db.ensure_session(session_id, source="milky", model="test/model")
    try:
        store.put(
            "group:700000001",
            GroupSessionMetadata(700000001, "初始群组", 3, "描述", "公告"),
        )
        agent = AIAgent(
            api_key="test-key",
            base_url="https://localhost:5500/v1",
            model="test/model",
            provider="openai",
            platform="milky",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            session_id=session_id,
            session_db=db,
        )
        first = build_system_prompt(agent)
        assert "group_name: 初始群组" in first
        assert section.content({}) in first

        store.put("group:700000001", GroupSessionMetadata(700000001, "后续群组"))
        assert build_system_prompt(agent) == first
        db.update_system_prompt(session_id, first)

        restored_agent = AIAgent(
            api_key="test-key",
            base_url="https://localhost:5500/v1",
            model="test/model",
            provider="openai",
            platform="milky",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            session_id=session_id,
            session_db=db,
        )
        _restore_or_build_system_prompt(
            restored_agent,
            None,
            [{"role": "user", "content": "persisted fixture"}],
        )
        assert restored_agent._cached_system_prompt == first
        assert "group_name: 后续群组" not in restored_agent._cached_system_prompt

        invalidate_system_prompt(agent)
        rebuilt = build_system_prompt(agent)
        assert "group_name: 后续群组" in rebuilt
        assert rebuilt != first
    finally:
        clear_session_vars(tokens)
        db.close()


if __name__ == "__main__":
    main()
