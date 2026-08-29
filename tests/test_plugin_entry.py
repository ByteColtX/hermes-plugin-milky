"""验证 Hermes directory plugin 边界的 smoke test。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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


def test_root_entry_exposes_only_hermes_register() -> None:
    """根模块只暴露 Hermes 的 public register surface。"""

    entry, module_name = load_plugin_entry()
    try:
        assert entry.__all__ == ["register"]
        entry.register(object())
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_root_tools_entry_is_safe_to_discover() -> None:
    """根工具发现入口不应在注册阶段产生外部副作用。"""

    entry, module_name = load_plugin_entry()
    try:
        entry.register(object())
        tools = sys.modules[f"{module_name}.tools"]
        assert tools.__all__ == ["register_tools"]
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_directory_plugin_uses_root_entry_only() -> None:
    """目录插件使用根入口，不保留可被误发现的旧子包入口。"""

    manifest = (PROJECT_ROOT / "plugin.yaml").read_text(encoding="utf-8")
    assert "provides_tools:" not in manifest
    assert (PROJECT_ROOT / "__init__.py").is_file()
    assert (PROJECT_ROOT / "tools.py").is_file()
    assert not (PROJECT_ROOT / "hermes_plugin_milky" / "__init__.py").exists()
