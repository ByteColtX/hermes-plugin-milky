"""通过宿主设置与凭证机制读取、校验和逐字段核验管理配置。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from .errors import PLUGIN_ID, ManagementError

KEYS = (
    "base_url",
    "allowed_chats",
    "will_policy",
    "session_buffer_size",
    "home_channel",
    "max_local_media_bytes",
    "long_text_forward_threshold",
    "group_member_event_notifications",
)


def _inputs():
    """读取当前已绑定范围，损坏持久化配置拒绝降级。"""
    from agent.secret_scope import get_secret
    from hermes_cli.config import load_config_readonly, read_user_config_raw

    try:
        raw = read_user_config_raw()
        effective = load_config_readonly()
        entry = effective.get("plugins", {}).get("entries", {}).get(PLUGIN_ID, {})
        raw_entry = raw.get("plugins", {}).get("entries", {}).get(PLUGIN_ID, {})
        settings = entry.get("settings", {})
        legacy = entry.get("config", {})
        explicit = raw_entry.get("settings", {})
        if not all(isinstance(value, Mapping) for value in (settings, legacy, explicit)):
            raise ManagementError("malformed")
        env = {"MILKY_" + key.upper(): get_secret("MILKY_" + key.upper()) for key in KEYS}
        env = {key: value for key, value in env.items() if value is not None}
        token = get_secret("MILKY_ACCESS_TOKEN")
        return dict(settings), dict(legacy), dict(explicit), env, token
    except ManagementError:
        raise
    except Exception:  # noqa: BLE001 - 损坏配置只返回固定类别
        raise ManagementError("malformed") from None


def _writable():
    """将宿主托管策略投影成逐字段可写性。"""
    from hermes_cli.config import is_managed
    from hermes_cli.managed_scope import is_key_managed

    return {
        key: not is_managed() and not is_key_managed(f"plugins.entries.{PLUGIN_ID}.settings.{key}")
        for key in KEYS
    }


def _version(settings, legacy, env, has_token):
    """版本不包含凭证，只覆盖普通来源与凭证存在状态。"""
    payload = json.dumps([settings, legacy, env, has_token], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _resolve(settings, legacy, env):
    """调用运行时统一解析器，允许凭证尚未配置。"""
    from config import resolve_settings

    return resolve_settings(settings=settings, legacy=legacy, environment=env, allow_missing=True)


def read():
    """返回显式值、有效值和来源，不返回凭证。"""
    settings, legacy, explicit, env, token = _inputs()
    result = {
        "explicit": {key: value for key, value in explicit.items() if key in KEYS},
        "writable": _writable(),
        "version": _version(settings, legacy, env, bool(token)),
        "has_access_token": bool(token),
        "runtime_status": "unknown",
        "restart_required": True,
        "concurrency": "per_key_write_no_conditional_transaction",
    }
    try:
        resolved = _resolve(settings, legacy, env)
        result.update(resolved)
    except ValueError:
        from config import resolve_settings

        values = resolve_settings(allow_missing=True)["effective"]
        errors, sources = {}, {}
        for key in KEYS:
            selected = settings if key in settings else legacy if key in legacy else None
            source = (
                "settings"
                if key in settings
                else "legacy"
                if key in legacy
                else "environment"
                if "MILKY_" + key.upper() in env
                else "default"
            )
            sources[key] = source
            try:
                partial = {key: selected[key]} if selected is not None else {}
                input_env = (
                    {"MILKY_" + key.upper(): env["MILKY_" + key.upper()]}
                    if source == "environment"
                    else {}
                )
                values[key] = resolve_settings(
                    settings=partial, environment=input_env, allow_missing=True
                )["effective"][key]
            except ValueError:
                errors[key] = "invalid_input"
                # 非法高优先级值不继续回退，UI 可明确修复该字段。
                values[key] = None
        result.update(
            {"status": "invalid_config", "effective": values, "sources": sources, "errors": errors}
        )
    return result


def save(version: str, changes: object):
    """完整校验后仅提交变化键，并逐项读取确认真实保存结果。"""
    from hermes_cli.plugins_state import save_plugin_setting

    if not isinstance(changes, dict) or not changes or set(changes) - set(KEYS):
        raise ManagementError("invalid_input")
    settings, legacy, _explicit, env, token = _inputs()
    if version != _version(settings, legacy, env, bool(token)):
        raise ManagementError("conflict")
    candidate = {**settings, **changes}
    try:
        _resolve(candidate, legacy, env)
    except ValueError:
        for key in KEYS:
            try:
                _resolve(
                    {key: candidate[key]} if key in candidate else {},
                    {key: legacy[key]} if key in legacy else {},
                    {"MILKY_" + key.upper(): env["MILKY_" + key.upper()]}
                    if "MILKY_" + key.upper() in env
                    else {},
                )
            except ValueError:
                raise ManagementError("invalid_input", field=key) from None
        raise ManagementError("invalid_input") from None
    writable = _writable()
    results = {}
    for key, value in changes.items():
        if not writable[key]:
            results[key] = "blocked"
            continue
        try:
            save_plugin_setting(PLUGIN_ID, (key,), value)
        except PermissionError:
            results[key] = "blocked"
            continue
        except Exception:  # noqa: BLE001 - 写失败不能泄漏异常或盲目回滚
            results[key] = "failed"
            continue
        try:
            latest, _, saved, _, _ = _inputs()
            results[key] = (
                "saved" if saved.get(key) == value and latest.get(key) == value else "conflict"
            )
        except ManagementError:
            results[key] = "unknown"
    # 后续字段写入期间可能发生外部变更，再核验已确认字段。
    try:
        latest, _, saved, _, _ = _inputs()
        for key, value in changes.items():
            if results.get(key) == "saved" and (
                saved.get(key) != value or latest.get(key) != value
            ):
                results[key] = "conflict"
    except ManagementError:
        results = {
            key: "unknown" if status == "saved" else status for key, status in results.items()
        }
    return {
        "status": "saved" if all(x == "saved" for x in results.values()) else "partial",
        "results": results,
        "restart_required": True,
        "runtime_status": "unknown",
    }


def credential(action: str, value: object = ""):
    """独立保持、替换或清除凭证，并以持久来源核验。"""
    from hermes_cli.config import load_env
    from hermes_cli.credential_lifecycle import (
        remove_provider_env_credential,
        save_provider_env_credential,
    )

    if action not in {"keep", "replace", "clear"} or not isinstance(value, str):
        raise ManagementError("invalid_input")
    if action == "keep" or (action == "replace" and not value):
        return {"status": "unchanged", "has_access_token": bool(_inputs()[-1])}
    if action == "replace" and (not value.strip() or "\n" in value or "\r" in value):
        raise ManagementError("invalid_input")
    try:
        if action == "clear":
            remove_provider_env_credential("MILKY_ACCESS_TOKEN")
        else:
            save_provider_env_credential("MILKY_ACCESS_TOKEN", value)
        actual = load_env().get("MILKY_ACCESS_TOKEN")
        verified = not actual if action == "clear" else actual == value
        return {
            "status": "saved" if verified else "blocked",
            "has_access_token": bool(actual),
            "restart_required": True,
            "runtime_status": "unknown",
        }
    except Exception:  # noqa: BLE001 - 凭证不进入异常响应
        return {"status": "unknown", "restart_required": True, "runtime_status": "unknown"}
