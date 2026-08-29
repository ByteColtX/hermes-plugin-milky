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

import pytest

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


def test_root_entry_exposes_only_hermes_register(monkeypatch) -> None:
    """根模块只暴露 Hermes 的 public register surface。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:
        assert entry.__all__ == ["register"]
        entry.register(object())
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_root_tools_entry_is_safe_to_discover(monkeypatch) -> None:
    """根工具发现入口不应在注册阶段产生外部副作用。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:
        entry.register(object())
        tools = sys.modules[f"{module_name}.tools"]
        assert tools.__all__ == ["register_tools"]
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
        assert entry.register(object()) is None
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_register_forwards_context_to_tools_without_implicit_actions(monkeypatch) -> None:
    """根入口应把同一个上下文交给显式工具发现边界。"""

    set_valid_environment(monkeypatch)
    entry, module_name = load_plugin_entry()
    try:
        entry.register(object())
        tools = sys.modules[f"{module_name}.tools"]
        context = object()
        received = []

        def capture_context(value) -> None:
            received.append(value)

        monkeypatch.setattr(tools, "register_tools", capture_context)
        assert entry.register(context) is None
        assert received == [context]
        assert tools.__all__ == ["register_tools"]
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_root_register_rejects_missing_startup_configuration(monkeypatch) -> None:
    """根注册入口应在启动阶段报告缺失配置。"""

    monkeypatch.delenv("MILKY_BASE_URL", raising=False)
    monkeypatch.delenv("MILKY_ACCESS_TOKEN", raising=False)
    entry, module_name = load_plugin_entry()
    try:
        with pytest.raises(ValueError, match="MILKY_BASE_URL"):
            entry.register(object())
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
    """目录插件使用根入口，不保留可被误发现的旧子包入口。"""

    manifest = (PROJECT_ROOT / "plugin.yaml").read_text(encoding="utf-8")
    assert (PROJECT_ROOT / "__init__.py").is_file()
    assert (PROJECT_ROOT / "tools.py").is_file()
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
module.register(object())
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
