"""以 Hermes 提供的作用域与启用状态约束管理请求。"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from management.errors import PLUGIN_ID, ManagementError


@contextmanager
def profile_scope(profile: str):
    """仅进入宿主确认的明确 profile，拒绝隐式 current 或路径。"""
    if not isinstance(profile, str) or not profile or profile in {"current", ".", ".."}:
        raise ManagementError("invalid_profile")
    try:
        from fastapi import HTTPException
        from hermes_cli.plugins_cmd import _get_disabled_set, _get_enabled_set
        from hermes_cli.web_server_profiles import _config_profile_scope, _resolve_profile_dir
        from hermes_constants import get_hermes_home
    except ImportError:
        raise ManagementError("unsupported") from None
    try:
        confirmed = _resolve_profile_dir(profile).resolve()
    except (HTTPException, ValueError, OSError):
        raise ManagementError("invalid_profile") from None
    with _config_profile_scope(profile):
        if get_hermes_home().resolve() != confirmed:
            raise ManagementError("unsupported")
        if PLUGIN_ID not in _get_enabled_set() or PLUGIN_ID in _get_disabled_set():
            raise ManagementError("disabled")
        yield confirmed


def storage_root(confirmed: Path) -> Path:
    """计算已确认作用域的固定只读根，不调用会创建目录的 helper。"""
    return confirmed / "plugin-data" / PLUGIN_ID


def profiles() -> dict[str, object]:
    """列出宿主已确认范围，不暴露对应文件系统路径。"""
    try:
        from hermes_cli.profiles import list_profiles
        from hermes_constants import get_process_hermes_home
    except ImportError:
        raise ManagementError("unsupported") from None
    choices = []
    selected = None
    for item in list_profiles(lazy_skill_count=True):
        name = item.name
        if not isinstance(name, str):
            continue
        try:
            with profile_scope(name) as confirmed:
                choices.append(name)
                if confirmed == get_process_hermes_home().resolve():
                    selected = name
        except ManagementError:
            continue
    return {"profiles": choices, "selected": selected}
