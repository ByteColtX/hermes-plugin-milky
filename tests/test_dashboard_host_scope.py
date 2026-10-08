"""Dashboard 请求 profile scope 的宿主解析边界。"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from types import ModuleType

import pytest

from dashboard.host import ManagementError, profile_scope


def _install_host_profile_fakes(monkeypatch, homes: dict[str, Path]) -> ContextVar[str]:
    """安装最小 Hermes profile API fake，模拟宿主确认的请求作用域。"""
    active_profile = ContextVar("dashboard_request_profile", default="")

    class HTTPException(Exception):
        """模拟 Hermes profile resolver 的拒绝。"""

    fastapi = ModuleType("fastapi")
    fastapi.HTTPException = HTTPException  # type: ignore[attr-defined]
    hermes_cli = ModuleType("hermes_cli")
    hermes_cli.__path__ = []  # type: ignore[attr-defined]
    plugins_cmd = ModuleType("hermes_cli.plugins_cmd")
    plugins_cmd._get_enabled_set = lambda: (
        set() if active_profile.get() == "disabled" else {"hermes-plugin-milky"}
    )  # type: ignore[attr-defined]
    plugins_cmd._get_disabled_set = lambda: set()  # type: ignore[attr-defined]
    web_profiles = ModuleType("hermes_cli.web_server_profiles")

    def resolve_profile(name: str) -> Path:
        if name not in homes:
            raise HTTPException("unknown profile")
        return homes[name]

    web_profiles._resolve_profile_dir = resolve_profile  # type: ignore[attr-defined]

    @contextmanager
    def config_profile_scope(name: str):
        token = active_profile.set(name)
        try:
            yield
        finally:
            active_profile.reset(token)

    web_profiles._config_profile_scope = config_profile_scope  # type: ignore[attr-defined]
    constants = ModuleType("hermes_constants")
    constants.get_hermes_home = lambda: homes[active_profile.get()]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastapi", fastapi)
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins_cmd", plugins_cmd)
    monkeypatch.setitem(sys.modules, "hermes_cli.web_server_profiles", web_profiles)
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)
    return active_profile


def test_dashboard_request_scope_never_falls_back_to_launch_profile(
    tmp_path: Path, monkeypatch
) -> None:
    """每个 API 请求按请求 profile 得到独立目录，未知 profile 不回退启动 profile。"""
    homes = {name: tmp_path / "profiles" / name for name in ("launch", "worker", "disabled")}
    active_profile = _install_host_profile_fakes(monkeypatch, homes)
    observed = []

    for name in ("launch", "worker", "launch"):
        with profile_scope(name) as confirmed:
            observed.append((active_profile.get(), confirmed))

    assert observed == [
        ("launch", homes["launch"]),
        ("worker", homes["worker"]),
        ("launch", homes["launch"]),
    ]
    with pytest.raises(ManagementError) as caught, profile_scope("ghost"):
        pytest.fail("未确认的 profile 不应进入 API handler")
    assert caught.value.status == "invalid_profile"
    with pytest.raises(ManagementError) as caught, profile_scope("disabled"):
        pytest.fail("未启用插件的 profile 不应进入 API handler")
    assert caught.value.status == "disabled"
