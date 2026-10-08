"""为源码包测试配置仓库根目录导入路径。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def target_hermes_helpers(monkeypatch: pytest.MonkeyPatch):
    """从目标 checkout 加载去重 helper，并隔离无关的 Gateway 启动依赖。"""

    hermes_root = next(
        (
            Path(entry or ".").resolve()
            for entry in sys.path
            if (Path(entry or ".") / "gateway" / "platforms" / "helpers.py").is_file()
        ),
        None,
    )
    if hermes_root is None:
        pytest.skip("Hermes target checkout is unavailable")

    gateway = ModuleType("gateway")
    gateway.__path__ = []  # type: ignore[attr-defined]
    platforms = ModuleType("gateway.platforms")
    platforms.__path__ = []  # type: ignore[attr-defined]
    event = ModuleType("gateway.platforms.event")
    event.MessageEvent = object  # type: ignore[attr-defined]
    utils = ModuleType("utils")
    utils.atomic_json_write = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.platforms", platforms)
    monkeypatch.setitem(sys.modules, "gateway.platforms.event", event)
    monkeypatch.setitem(sys.modules, "utils", utils)

    helper_path = hermes_root / "gateway" / "platforms" / "helpers.py"
    spec = importlib.util.spec_from_file_location("_milky_target_platform_helpers", helper_path)
    if spec is None or spec.loader is None:
        pytest.skip("Hermes target helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
