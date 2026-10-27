"""验证 Hermes directory plugin 边界的 smoke test。"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from session import GroupSessionMetadata

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_plugin_entry():
    """按 Hermes 的 namespaced package 方式加载根目录入口。"""

    module_name = "hermes_plugins.hermes_plugin_milky_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module, module_name


def set_valid_environment(monkeypatch) -> None:
    """为调用真实注册入口提供不含真实凭证的测试配置。"""

    monkeypatch.setenv("MILKY_BASE_URL", "https://localhost:5500/milky")
    monkeypatch.setenv("MILKY_ACCESS_TOKEN", "test-token")
    gateway = ModuleType("gateway")
    gateway.__path__ = []  # type: ignore[attr-defined]
    platforms = ModuleType("gateway.platforms")
    platforms.__path__ = []  # type: ignore[attr-defined]
    shared = ModuleType("gateway.platforms._shared")
    shared.get_scoped_secret = (  # type: ignore[attr-defined]
        lambda name, default=None: os.environ.get(name, default)
    )
    hermes_cli = ModuleType("hermes_cli")
    hermes_cli.__path__ = []  # type: ignore[attr-defined]
    core_config = ModuleType("hermes_cli.config")
    core_config.load_config_readonly = dict  # type: ignore[attr-defined]
    profiles = ModuleType("hermes_cli.profiles")
    profiles.get_active_profile_name = (  # type: ignore[attr-defined]
        lambda: os.environ.get("MILKY_TEST_PROFILE", "default")
    )
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.platforms", platforms)
    monkeypatch.setitem(sys.modules, "gateway.platforms._shared", shared)
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", core_config)
    monkeypatch.setitem(sys.modules, "hermes_cli.profiles", profiles)


def test_root_entry_exposes_only_hermes_register(monkeypatch) -> None:
    """根模块只暴露 Hermes 的 public register surface。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:
        assert entry.__all__ == ["register"]
        assert callable(entry.register_tools)
        with pytest.raises(RuntimeError, match="platform unsupported"):
            entry.register(object())
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_import_and_register_do_not_start_network_or_background_work(monkeypatch) -> None:
    """导入和注册阶段不得打开网络或创建长期后台任务。"""

    def fail_network(*args, **kwargs):
        raise AssertionError("注册阶段不应创建网络 socket")

    def fail_background_task(*args, **kwargs):
        raise AssertionError("注册阶段不应创建后台任务")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(asyncio, "create_task", fail_background_task)
    monkeypatch.setattr(asyncio, "ensure_future", fail_background_task)
    monkeypatch.setattr(threading, "Thread", fail_background_task)
    set_valid_environment(monkeypatch)

    entry, module_name = load_plugin_entry()
    try:
        with pytest.raises(RuntimeError, match="platform unsupported"):
            entry.register(object())
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


class SkillAndPlatformContext:
    """捕获 bundled skill、platform 和旧工具入口注册，不执行外部动作。"""

    def __init__(self) -> None:
        self.skills: list[tuple[str, Path]] = []
        self.skill_descriptions: list[str] = []
        self.platforms: list[dict[str, Any]] = []
        self.system_prompt_sections: list[dict[str, Any]] = []
        self.tools: list[dict[str, Any]] = []
        self.hooks: list[tuple[str, Any]] = []

    def register_skill(self, name: str, path: Path, description: str = "") -> None:
        self.skills.append((name, path))
        self.skill_descriptions.append(description)

    def register_platform(self, **kwargs: Any) -> None:
        self.platforms.append(kwargs)

    def register_system_prompt_section(self, **kwargs: Any) -> None:
        """记录 system prompt section 注册，不执行 renderer。"""

        self.system_prompt_sections.append(kwargs)

    def register_tool(self, **kwargs: Any) -> None:
        """记录旧平台入口转交的固定工具注册。"""

        self.tools.append(kwargs)

    def register_hook(self, name: str, callback: Any) -> None:
        """记录根入口登记的观察 hook。"""

        self.hooks.append((name, callback))


def test_root_registers_split_qq_skills_and_milky_prompt_section(monkeypatch) -> None:
    """根入口应拆分静态首句和连接后渲染的 Milky 指引。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:
        context = SkillAndPlatformContext()
        entry.register(context)

        assert [name for name, _callback in context.hooks] == ["post_tool_call"]
        assert callable(context.hooks[0][1])

        assert dict(context.skills) == {
            "milky-qq-cq-reference": PROJECT_ROOT / "skills" / "milky-qq-cq-reference" / "SKILL.md",
            "milky-qq-action-tools": PROJECT_ROOT / "skills" / "milky-qq-action-tools" / "SKILL.md",
        }
        assert all(skill_path.is_file() for _, skill_path in context.skills)
        assert len(context.skill_descriptions) == 2
        for (skill_name, _skill_path), description in zip(
            context.skills, context.skill_descriptions, strict=True
        ):
            frontmatter_line = next(
                line
                for line in (PROJECT_ROOT / "skills" / skill_name / "SKILL.md")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.startswith("description:")
            )
            assert description == frontmatter_line.partition(":")[2].strip()
        assert all(context.skill_descriptions)

        hint = context.platforms[0]["platform_hint"]
        assert hint == "You are chatting on QQ through Hermes's Milky platform."
        assert hint == entry.PLATFORM_HINT
        assert len(context.system_prompt_sections) == 2
        section = context.system_prompt_sections[0]
        assert section["id"] == "hermes-plugin-milky.qq-platform-guidance"
        assert section["position"] == "after_memory"
        assert callable(section["content"])
        assert section["content"]({}) == ""
        assert entry.PLATFORM_GUIDANCE not in hint
        guidance_snapshot = (
            (PROJECT_ROOT / "tests" / "fixtures" / "prompts" / "milky_platform_guidance.txt")
            .read_text(encoding="utf-8")
            .strip()
        )
        assert entry.PLATFORM_GUIDANCE.strip() == guidance_snapshot
        assert "NO_REPLY" not in entry.PLATFORM_GUIDANCE
        assert "[SILENT]" in entry.PLATFORM_GUIDANCE
        assert "[SPLIT]" in entry.PLATFORM_GUIDANCE
        assert "with no extra content" in entry.PLATFORM_GUIDANCE
        assert "between text sections" in entry.PLATFORM_GUIDANCE
        assert "up to 3 messages" in entry.PLATFORM_GUIDANCE
        assert "markers are removed before sending" in entry.PLATFORM_GUIDANCE
        assert "[CQ:at,qq=<uid>]" in entry.PLATFORM_GUIDANCE
        assert "[CQ:reply,id=<msg_seq>]" in entry.PLATFORM_GUIDANCE
        assert "Use `id=`, never `id:`." not in entry.PLATFORM_GUIDANCE
        assert "Use real `uid` and `msg_seq` values" in entry.PLATFORM_GUIDANCE
        assert "101" not in hint
        assert "9001" not in hint
        assert "MILKY_ACCESS_TOKEN" not in hint
        assert "https://" not in hint
        session_section = context.system_prompt_sections[1]
        assert session_section["id"] == "hermes-plugin-milky.qq-session-context"
        assert session_section["position"] == "after_memory"
        assert callable(session_section["content"])
        assert session_section["content"]({}) == ""
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_milky_prompt_section_isolates_identity_snapshots_by_profile(monkeypatch) -> None:
    """提示 section 只读取对应 profile 的 adapter 身份快照。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    guidance_snapshot = (
        (PROJECT_ROOT / "tests" / "fixtures" / "prompts" / "milky_platform_guidance.txt")
        .read_text(encoding="utf-8")
        .strip()
    )
    try:
        context = SkillAndPlatformContext()
        entry.register(context)
        registration = context.platforms[0]

        monkeypatch.setenv("MILKY_TEST_PROFILE", "a")
        adapter = registration["adapter_factory"](object())
        adapter_a = adapter
        snapshot_a = adapter_a.identity_snapshot

        monkeypatch.setenv("MILKY_TEST_PROFILE", "b")
        adapter_b = registration["adapter_factory"](object())
        snapshot_b = adapter_b.identity_snapshot

        assert snapshot_a is not snapshot_b
        assert snapshot_a.read() is None
        callback = context.system_prompt_sections[0]["content"]
        assert callback({"profile_name": "a"}) == ""

        assert snapshot_a.publish(900000001, "合成机器人 A") is True
        assert snapshot_b.publish(900000002, "合成机器人 B") is True
        rendered_a = callback({"profile_name": "a"})
        rendered_b = callback({"profile_name": "b"})
        assert rendered_a.startswith(
            "- Your QQ uid is 900000001, and your nickname is 合成机器人 A.\n"
        )
        assert rendered_b.startswith(
            "- Your QQ uid is 900000002, and your nickname is 合成机器人 B.\n"
        )
        assert rendered_a.split("\n", 1)[1] == entry.PLATFORM_GUIDANCE
        assert rendered_b.split("\n", 1)[1] == entry.PLATFORM_GUIDANCE
        assert rendered_a.strip() == (
            "- Your QQ uid is 900000001, and your nickname is 合成机器人 A.\n"
            + "\n"
            + guidance_snapshot
        )
        assert "合成机器人 B" not in rendered_a
        assert "合成机器人 A" not in rendered_b
        assert callback({}) == ""
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_platform_factory_resolves_settings_for_each_active_profile(monkeypatch) -> None:
    """adapter factory 每次都在当前 profile 中重新解析普通设置。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:
        config_module = importlib.import_module(f"{module_name}.config")
        adapter_module = importlib.import_module(f"{module_name}.adapter")
        resolve = config_module.load_config
        profiles = {
            "a": {
                "settings": {
                    "base_url": "https://profile-a.invalid/milky",
                    "session_buffer_size": 11,
                    "home_channel": "group:700000011",
                },
                "environment": {"MILKY_ACCESS_TOKEN": "synthetic-token-a"},
            },
            "b": {
                "settings": {
                    "base_url": "https://profile-b.invalid/milky",
                    "session_buffer_size": 22,
                    "home_channel": "group:700000022",
                },
                "environment": {"MILKY_ACCESS_TOKEN": "synthetic-token-b"},
            },
        }
        active_profile: dict[str, str] = {}

        def load_active_profile_config():
            """模拟 Gateway 在各 profile 作用域内调用 adapter factory。"""

            profile = profiles[active_profile["name"]]
            return resolve(**profile)

        class CapturedAdapter:
            """捕获 factory 解析结果，不创建连接资源。"""

            def __init__(self, platform_config, **kwargs):
                self.platform_config = platform_config
                self.milky_config = kwargs["milky_config"]

        monkeypatch.setattr(config_module, "load_config", load_active_profile_config)
        monkeypatch.setattr(adapter_module, "MilkyAdapter", CapturedAdapter)

        context = SkillAndPlatformContext()
        entry.register(context)
        factory = context.platforms[0]["adapter_factory"]

        active_profile["name"] = "a"
        monkeypatch.setenv("MILKY_TEST_PROFILE", "a")
        adapter_a = factory(object())
        active_profile["name"] = "b"
        monkeypatch.setenv("MILKY_TEST_PROFILE", "b")
        adapter_b = factory(object())

        assert adapter_a.milky_config.base_url == "https://profile-a.invalid/milky"
        assert adapter_a.milky_config.session_buffer_size == 11
        assert adapter_a.milky_config.home_channel == "group:700000011"
        assert adapter_b.milky_config.base_url == "https://profile-b.invalid/milky"
        assert adapter_b.milky_config.session_buffer_size == 22
        assert adapter_b.milky_config.home_channel == "group:700000022"
        assert context.platforms[0]["env_enablement_fn"]() == {
            "home_channel": {"chat_id": "group:700000022", "name": "Milky Home"}
        }
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_milky_session_section_isolates_adapter_snapshots_by_profile(monkeypatch) -> None:
    """会话 section 从当前 profile 的 adapter store 读取资料。"""

    set_valid_environment(monkeypatch)
    gateway = ModuleType("gateway")
    session_context = ModuleType("gateway.session_context")
    session_context.get_session_env = lambda name, default="": (  # type: ignore[attr-defined]
        "group:700000001" if name == "HERMES_SESSION_CHAT_ID" else default
    )
    gateway.session_context = session_context  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.session_context", session_context)
    entry, module_name = load_plugin_entry()
    try:
        context = SkillAndPlatformContext()
        entry.register(context)
        factory = context.platforms[0]["adapter_factory"]
        monkeypatch.setenv("MILKY_TEST_PROFILE", "a")
        adapter_a = factory(object())
        monkeypatch.setenv("MILKY_TEST_PROFILE", "b")
        adapter_b = factory(object())
        assert adapter_a.session_context_store is not adapter_b.session_context_store
        adapter_a.session_context_store.put(
            "group:700000001",
            GroupSessionMetadata(700000001, "合成群组 A", 3, "描述 A", "公告 A"),
        )
        adapter_b.session_context_store.put(
            "group:700000001",
            GroupSessionMetadata(700000001, "合成群组 B", 4, "描述 B", "公告 B"),
        )

        callback = context.system_prompt_sections[1]["content"]
        rendered_a = callback({"profile_name": "a", "chat_id": "dm:untrusted"})
        rendered_b = callback({"profile_name": "b", "chat_id": "dm:untrusted"})

        assert "group_id: 700000001" in rendered_a
        assert "group_name: 合成群组 A" in rendered_a
        assert "group_name: 合成群组 B" not in rendered_a
        assert "group_name: 合成群组 B" in rendered_b
        assert "group_name: 合成群组 A" not in rendered_b
        assert "dm:untrusted" not in rendered_a + rendered_b
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_milky_prompt_renderer_sanitizes_abnormal_nickname(monkeypatch) -> None:
    """section 身份首行保持单行且不接受空昵称或控制字符。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:
        profile_snapshots = entry._ProfileSnapshots()
        stored_identity, _session_store = profile_snapshots.for_active_profile()
        assert stored_identity.publish(900000001, "  合成\n机器人\t  ") is True
        rendered = entry._render_platform_guidance(
            profile_snapshots, {"profile_name": "default", "nickname": "untrusted"}
        )
        assert (
            rendered.splitlines()[0]
            == "- Your QQ uid is 900000001, and your nickname is 合成 机器人."
        )
        assert "\n" not in rendered.splitlines()[0]

        assert stored_identity.publish(900000001, "\x00") is False
        assert stored_identity.publish(900000001, "   ") is False
        assert stored_identity.read().nickname == "合成 机器人"
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_missing_prompt_api_fails_before_platform_registration(monkeypatch) -> None:
    """缺少必需 section API 时明确失败，不留下部分平台注册。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:

        class MissingPromptContext:
            """只提供平台注册接口的旧上下文。"""

            def __init__(self) -> None:
                self.platforms: list[dict[str, Any]] = []

            def register_platform(self, **kwargs: Any) -> None:
                self.platforms.append(kwargs)

        context = MissingPromptContext()
        with pytest.raises(RuntimeError, match="register_system_prompt_section"):
            entry.register(context)
        assert context.platforms == []
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_milky_prompt_registration_isolated_from_other_platform_entries(monkeypatch) -> None:
    """Milky section 只影响自身注册项，不改动其他平台的提示和 section。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:
        context = SkillAndPlatformContext()
        other_section = {"id": "other-platform.guidance", "content": "Other guidance"}
        context.platforms.append(
            {
                "name": "other",
                "platform_hint": "Other platform hint",
            }
        )
        context.system_prompt_sections.append(other_section)

        entry.register(context)

        assert context.platforms[0] == {
            "name": "other",
            "platform_hint": "Other platform hint",
        }
        assert context.system_prompt_sections[0] is other_section
        assert len(context.system_prompt_sections) == 3
        milky_section = context.system_prompt_sections[1]
        assert milky_section["id"] == "hermes-plugin-milky.qq-platform-guidance"
        assert entry.PLATFORM_GUIDANCE not in other_section["content"]
        assert context.system_prompt_sections[2]["id"] == "hermes-plugin-milky.qq-session-context"
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_bundled_skill_registration_is_optional_when_host_has_no_api(
    monkeypatch, tmp_path: Path
) -> None:
    """缺失任一 skill 文件或旧宿主 API 不应阻止平台注册。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:
        monkeypatch.setattr(entry, "_PLUGIN_ROOT", str(tmp_path))
        context = SkillAndPlatformContext()
        entry._register_bundled_skill(context)
        assert context.skills == []

        class LegacyContext:
            """没有 register_skill 的旧宿主上下文。"""

        entry._register_bundled_skill(LegacyContext())
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_bundled_skill_uses_host_namespace_and_does_not_overwrite_siblings() -> None:
    """skill 注册只提交裸名，由宿主生成插件命名空间并隔离同名项。"""

    class NamespacedSkillContext:
        """模拟宿主命名空间注册边界，不写入用户 skill 目录。"""

        def __init__(self, namespace: str) -> None:
            self.namespace = namespace
            self.plugin_skills: dict[str, Path] = {}
            self.user_skills: dict[str, Path] = {}

        def register_skill(self, name: str, path: Path, description: str = "") -> None:
            qualified_name = f"{self.namespace}:{name}"
            self.plugin_skills.setdefault(qualified_name, path)

    milky = NamespacedSkillContext("hermes-plugin-milky")
    sibling = NamespacedSkillContext("another-plugin")
    for skill_name in ("milky-qq-cq-reference", "milky-qq-action-tools"):
        skill_path = PROJECT_ROOT / "skills" / skill_name / "SKILL.md"
        milky.register_skill(skill_name, skill_path)
        sibling.register_skill(skill_name, skill_path)

    assert set(milky.plugin_skills) == {
        "hermes-plugin-milky:milky-qq-cq-reference",
        "hermes-plugin-milky:milky-qq-action-tools",
    }
    assert set(sibling.plugin_skills) == {
        "another-plugin:milky-qq-cq-reference",
        "another-plugin:milky-qq-action-tools",
    }
    assert milky.user_skills == {}
    assert sibling.user_skills == {}


def test_qq_skills_are_split_and_do_not_add_tools() -> None:
    """CQ 和工具说明应拆分，实际工具仍只有 manifest 中的明确项。"""

    cq_skill = (PROJECT_ROOT / "skills" / "milky-qq-cq-reference" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    face_reference = (
        PROJECT_ROOT
        / "skills"
        / "milky-qq-cq-reference"
        / "references"
        / "face-id-to-chinese-name.md"
    ).read_text(encoding="utf-8")
    tools_skill = (PROJECT_ROOT / "skills" / "milky-qq-action-tools" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "[CQ:at,qq=<uid>]" in cq_skill
    assert "[CQ:reply,id=<message_seq>]" in cq_skill
    assert "[CQ:face,id=<face_id>]" in cq_skill
    assert "[CQ:face,id=<超级表情face_id>,large=1]" in cq_skill
    assert "只有“超级表情”条目的 `face_id` 才能使用 `large=1`" in cq_skill
    assert "478 /对的对的" in cq_skill
    assert "9007199254740991" not in cq_skill
    assert "10001..4294967295" not in cq_skill
    assert "[CQ:image,file=file:///path/to/sticker.ext,type=sticker]" in cq_skill
    assert "| face ID | 中文名称 | 备注 |" in cq_skill
    assert "| 14 | /微笑 | 现代聊天中常用于阴阳、讽刺或表达不满" in cq_skill
    assert "| face ID (`qSid`) | 中文名称 (`qDes`) | 备注 |" in face_reference
    assert "| 14 | /微笑 | 现代聊天中常用于阴阳、讽刺或表达不满" in face_reference
    assert "Unicode emoji 不纳入本表。" in face_reference
    assert "## emoji 表情（运行时不参与映射）" not in face_reference
    for removed_type in (
        "record",
        "video",
        "rps",
        "dice",
        "shake",
        "poke",
        "share",
        "contact",
        "location",
        "music",
        "forward",
        "node",
        "json",
        "mface",
        "file",
        "markdown",
        "lightapp",
        "anonymous",
        "redbag",
        "gift",
        "cardimage",
        "tts",
        "xml",
    ):
        assert f"[CQ:{removed_type}" not in cq_skill
    for tool_name in (
        "send_profile_like",
        "send_friend_nudge",
        "send_group_nudge",
        "recall_group_message",
        "get_group_info",
        "get_group_member_list",
        "get_group_member_info",
        "set_group_member_mute",
        "set_group_whole_mute",
        "get_forwarded_messages",
        "get_private_file_download_url",
        "kick_group_member",
        "quit_group",
        "delete_friend",
        "get_friend_requests",
        "accept_friend_request",
        "reject_friend_request",
    ):
        assert tool_name not in cq_skill

    assert "MEDIA:<local_path>" in tools_skill
    assert "send_message" in tools_skill
    assert "不含媒体发送" in tools_skill
    assert "在回复中包含" in tools_skill

    assert "[CQ:" not in tools_skill
    assert "文字说明不注册" in tools_skill
    assert "不执行也不扩大工具能力" in tools_skill
    for tool_name in (
        "send_profile_like",
        "send_friend_nudge",
        "send_group_nudge",
        "recall_group_message",
        "get_group_info",
        "get_group_member_list",
        "get_group_member_info",
        "set_group_member_mute",
        "set_group_whole_mute",
        "get_forwarded_messages",
        "get_private_file_download_url",
        "kick_group_member",
        "quit_group",
        "delete_friend",
        "get_friend_requests",
        "accept_friend_request",
        "reject_friend_request",
    ):
        assert tool_name in tools_skill


def test_register_forwards_context_to_tool_registration(monkeypatch) -> None:
    """根 platform entry 将同一个 context 转交给固定工具注册入口。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:
        context = SkillAndPlatformContext()
        received: list[object] = []

        def capture_context(value: object) -> None:
            received.append(value)

        monkeypatch.setattr(entry, "register_tools", capture_context)
        assert entry.register(context) is None
        assert context.platforms
        assert received == [context]
        assert entry.__all__ == ["register"]
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_root_register_defers_missing_configuration_until_adapter_creation(monkeypatch) -> None:
    """普通配置在创建 adapter 时校验，不绑定注册时的默认 profile。"""

    set_valid_environment(monkeypatch)
    monkeypatch.delenv("MILKY_BASE_URL", raising=False)
    monkeypatch.delenv("MILKY_ACCESS_TOKEN", raising=False)
    entry, module_name = load_plugin_entry()
    try:
        context = SkillAndPlatformContext()
        entry.register(context)
        with pytest.raises(ValueError, match="MILKY_BASE_URL"):
            context.platforms[0]["adapter_factory"](object())
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_adapter_creation_rejects_removed_routing_before_network_access(monkeypatch) -> None:
    """旧 routing 字段应在 adapter 创建网络资源前被拒绝。"""

    def fail_network(*args, **kwargs):
        raise AssertionError("配置拒绝前不应创建网络 socket")

    monkeypatch.setattr(socket, "socket", fail_network)
    set_valid_environment(monkeypatch)
    monkeypatch.setenv(
        "MILKY_WILL_POLICY",
        '{"engine":"routing","routing":{"group":"wait"}}',
    )
    entry, module_name = load_plugin_entry()
    try:
        context = SkillAndPlatformContext()
        entry.register(context)
        with pytest.raises(ValueError, match="unsupported fields"):
            context.platforms[0]["adapter_factory"](object())
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_target_source_package_layout_is_present() -> None:
    """目标源码包目录都应存在独立的 Python package 边界。"""

    package_names = (
        "config",
        "milky",
        "inbound",
        "gates",
        "will",
        "session",
        "state",
        "outbound",
    )
    for package_name in package_names:
        package_dir = PROJECT_ROOT / package_name
        assert package_dir.is_dir()
        assert (package_dir / "__init__.py").is_file()


def test_directory_plugin_uses_root_entry_only() -> None:
    """当前目录插件使用根入口登记平台和固定工具。"""

    manifest = (PROJECT_ROOT / "plugin.yaml").read_text(encoding="utf-8")
    assert (PROJECT_ROOT / "__init__.py").is_file()
    assert not (PROJECT_ROOT / "tools.py").exists()
    assert "provides_tools:" in manifest
    assert not (PROJECT_ROOT / "hermes_plugin_milky" / "__init__.py").exists()


def test_namespaced_directory_entry_bootstraps_internal_imports(tmp_path: Path) -> None:
    """Hermes namespaced 加载目录插件时应能解析插件自己的顶层模块。"""

    script = """
import importlib.util
import sys

project_root = sys.argv[1]
module_name = "hermes_plugins.hermes_plugin_milky_isolated"
spec = importlib.util.spec_from_file_location(
    module_name,
    project_root + "/__init__.py",
    submodule_search_locations=[project_root],
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
spec.loader.exec_module(module)
assert callable(module.register)
importlib.import_module(f"{module_name}.config")
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["MILKY_BASE_URL"] = "https://localhost:5500/milky"
    environment["MILKY_ACCESS_TOKEN"] = "test-token"
    result = subprocess.run(
        [sys.executable, "-c", script, str(PROJECT_ROOT)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_yaml_startup_keeps_one_snapshot_without_web_dependencies(monkeypatch):
    """Gateway 注册不捕获设置快照，adapter 创建时读取 profile 配置且不导入 Web。"""
    import builtins

    monkeypatch.delenv("MILKY_BASE_URL", raising=False)
    core = ModuleType("hermes_cli.config")
    selected = {"base_url": "http://127.0.0.1:4000", "home_channel": "group:123"}
    core.load_config_readonly = lambda: {
        "plugins": {"entries": {"hermes-plugin-milky": {"settings": selected}}}
    }
    hermes_cli = ModuleType("hermes_cli")
    hermes_cli.__path__ = []  # type: ignore[attr-defined]
    profiles = ModuleType("hermes_cli.profiles")
    profiles.get_active_profile_name = lambda: "default"  # type: ignore[attr-defined]
    gateway = ModuleType("gateway")
    gateway.__path__ = []  # type: ignore[attr-defined]
    platforms = ModuleType("gateway.platforms")
    platforms.__path__ = []  # type: ignore[attr-defined]
    shared = ModuleType("gateway.platforms._shared")
    shared.get_scoped_secret = (  # type: ignore[attr-defined]
        lambda key, default=None: "synthetic-secret" if key == "MILKY_ACCESS_TOKEN" else default
    )
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", core)
    monkeypatch.setitem(sys.modules, "hermes_cli.profiles", profiles)
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.platforms", platforms)
    monkeypatch.setitem(sys.modules, "gateway.platforms._shared", shared)
    imported = builtins.__import__

    def require_no_web(name, *args, **kwargs):
        assert name.split(".")[0] not in {"fastapi", "starlette", "python_multipart", "dashboard"}
        return imported(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", require_no_web)
    captured = []
    monkeypatch.setattr(
        "outbound.standalone.make_standalone_sender",
        lambda config=None: captured.append(config) or object(),
    )
    entry, module_name = load_plugin_entry()
    try:
        context = SkillAndPlatformContext()
        entry.register(context)
        registration = context.platforms[0]
        selected["base_url"] = "http://127.0.0.1:5000"
        adapter = registration["adapter_factory"](object())
        assert captured == [None]
        assert adapter._config.base_url == "http://127.0.0.1:5000"
        assert adapter._config.home_channel == "group:123"
        assert registration["required_env"] == []
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_register_once_factory_and_same_adapter_read_fresh_profile(monkeypatch):
    """一次注册后的原工厂和同实例重连都读取当前 profile 的单项设置。"""
    import copy
    from contextvars import ContextVar
    from types import SimpleNamespace

    from management import settings
    from tests.test_adapter_lifecycle import (
        FakeClient,
        FakeEventStream,
        FakeMuteTracker,
        FakePipeline,
        FakeSender,
    )

    set_valid_environment(monkeypatch)
    scope = ContextVar("synthetic-profile", default="alpha")
    current = {"alpha": {"allowed_chats": ["group:123"]}, "beta": {"allowed_chats": ["dm:999"]}}
    constants = ModuleType("hermes_constants")
    constants.get_hermes_home = lambda: Path("/synthetic") / scope.get()
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)

    def inputs():
        native = copy.deepcopy(current[scope.get()])
        return native, {}, native, {"MILKY_ALLOWED_CHATS": "dm:*"}, "synthetic"

    monkeypatch.setattr(settings, "_inputs", inputs)
    entry, module_name = load_plugin_entry()
    context = SkillAndPlatformContext()
    entry.register(context)
    factory = context.platforms[0]["adapter_factory"]

    def make():
        adapter = factory(SimpleNamespace())
        injected = {
            "client": FakeClient(),
            "event_stream": FakeEventStream(),
            "mute_tracker": FakeMuteTracker(),
            "pipeline": FakePipeline(),
            "outbound_sender": FakeSender(),
        }
        adapter._injected.update(injected)
        adapter._closed = True
        return adapter

    async def scenario():
        first = make()
        assert await first.connect()
        assert first._chat_policy.rules == {"group:123"}
        await first.disconnect()
        current["alpha"]["allowed_chats"] = []
        token = scope.set("beta")
        try:
            assert await first.connect()
            assert not first._chat_policy.rules
            await first.disconnect()
            second = make()
            assert await second.connect()
            assert not second._chat_policy.rules
            await second.disconnect()
        finally:
            scope.reset(token)
        current["alpha"]["allowed_chats"] = ["temp:123"]
        third = make()
        assert not await third.connect()
        await third.disconnect()

    try:
        asyncio.run(scenario())
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(module_name + "."):
                sys.modules.pop(name, None)
