"""配置管理的旧版本、逐项失败和凭证脱敏验证。"""

import copy
import sys
from types import ModuleType

import pytest

from dashboard import settings
from dashboard.host import ManagementError


@pytest.fixture
def inputs(monkeypatch):
    current = {"base_url": "http://127.0.0.1:4000"}
    legacy, env = {}, {}
    monkeypatch.setattr(
        settings,
        "_inputs",
        lambda: (copy.deepcopy(current), legacy, copy.deepcopy(current), env, "synthetic-secret"),
    )
    monkeypatch.setattr(settings, "_writable", lambda: dict.fromkeys(settings.KEYS, True))
    monkeypatch.setattr(
        settings,
        "_resolve",
        lambda candidate, *_: {
            "effective": candidate,
            "sources": dict.fromkeys(candidate, "settings"),
        },
    )
    module = ModuleType("hermes_cli.plugins_state")
    module.save_plugin_setting = lambda _plugin, keys, value: current.update({keys[0]: value})
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins_state", module)
    return current, module


def test_read_never_returns_secret(inputs):
    result = settings.read()
    assert result["has_access_token"] is True
    assert "synthetic-secret" not in repr(result)
    assert result["runtime_status"] == "unknown"


def test_stale_form_and_unknown_fields_do_not_write(inputs):
    current, _ = inputs
    version = settings.read()["version"]
    current["home_channel"] = "dm:123"
    with pytest.raises(ManagementError) as caught:
        settings.save(version, {"session_buffer_size": 0})
    assert caught.value.status == "conflict"
    assert "session_buffer_size" not in current
    with pytest.raises(ManagementError):
        settings.save(settings.read()["version"], {"access_token": "must-not-save"})


def test_partial_failure_and_managed_refusal_are_explicit(inputs, monkeypatch):
    current, module = inputs

    def write(_plugin, keys, value):
        if keys[0] == "home_channel":
            raise OSError("sensitive-error")
        current[keys[0]] = value

    module.save_plugin_setting = write
    monkeypatch.setattr(
        settings,
        "_writable",
        lambda: {**dict.fromkeys(settings.KEYS, True), "allowed_chats": False},
    )
    result = settings.save(
        settings.read()["version"],
        {"session_buffer_size": 0, "home_channel": "dm:12", "allowed_chats": []},
    )
    assert result["status"] == "partial"
    assert result["results"] == {
        "session_buffer_size": "saved",
        "home_channel": "failed",
        "allowed_chats": "blocked",
    }
    assert "sensitive-error" not in repr(result)


def test_complete_candidate_validation_precedes_any_write(inputs, monkeypatch):
    current, _ = inputs

    def reject(*_):
        raise ValueError("sensitive-input")

    monkeypatch.setattr(settings, "_resolve", reject)
    with pytest.raises(ManagementError) as caught:
        settings.save(settings.read()["version"], {"session_buffer_size": -1})
    assert caught.value.status == "invalid_input"
    assert "session_buffer_size" not in current


def test_readback_detects_concurrent_change_without_rollback(inputs):
    current, module = inputs

    def write(_plugin, keys, value):
        current[keys[0]] = value
        current["session_buffer_size"] = 99

    module.save_plugin_setting = write
    result = settings.save(settings.read()["version"], {"session_buffer_size": 0})
    assert result["results"]["session_buffer_size"] == "conflict"
    assert current["session_buffer_size"] == 99


def test_invalid_priority_source_has_no_fabricated_effective_value(monkeypatch):
    monkeypatch.setattr(
        settings, "_inputs", lambda: ({"base_url": "", "session_buffer_size": -1}, {}, {}, {}, None)
    )
    monkeypatch.setattr(settings, "_writable", lambda: dict.fromkeys(settings.KEYS, True))
    result = settings.read()
    assert result["status"] == "invalid_config"
    assert result["effective"]["base_url"] is None
    assert result["effective"]["session_buffer_size"] is None
    assert result["sources"]["base_url"] == "settings"
    assert result["errors"] == {"base_url": "invalid_input", "session_buffer_size": "invalid_input"}


def test_credential_rejected_write_is_not_reported_saved(inputs, monkeypatch):
    lifecycle = ModuleType("hermes_cli.credential_lifecycle")
    lifecycle.save_provider_env_credential = lambda *_: None
    lifecycle.remove_provider_env_credential = lambda *_: None
    core = ModuleType("hermes_cli.config")
    core.load_env = lambda: {"MILKY_ACCESS_TOKEN": "synthetic-original"}
    monkeypatch.setitem(sys.modules, "hermes_cli.credential_lifecycle", lifecycle)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", core)
    replacement = settings.credential("replace", "synthetic-new")
    cleared = settings.credential("clear")
    assert replacement["status"] == cleared["status"] == "blocked"
    assert "synthetic-original" not in repr(replacement)
    assert "synthetic-new" not in repr(replacement)


def test_malformed_host_config_is_sanitized(monkeypatch):
    core = ModuleType("hermes_cli.config")
    core.read_user_config_raw = lambda: (_ for _ in ()).throw(ValueError("private-config-body"))
    core.load_config_readonly = dict
    secret = ModuleType("agent.secret_scope")
    secret.get_secret = lambda _: "must-not-expose"
    monkeypatch.setitem(sys.modules, "hermes_cli.config", core)
    monkeypatch.setitem(sys.modules, "agent.secret_scope", secret)
    with pytest.raises(ManagementError) as caught:
        settings._inputs()
    assert str(caught.value) == "malformed"


def test_managed_overlay_preserves_explicit_and_effective_distinction(monkeypatch):
    monkeypatch.setattr(
        settings,
        "_inputs",
        lambda: ({"session_buffer_size": 20}, {}, {"session_buffer_size": 10}, {}, None),
    )
    monkeypatch.setattr(
        settings,
        "_writable",
        lambda: {**dict.fromkeys(settings.KEYS, True), "session_buffer_size": False},
    )
    result = settings.read()
    assert result["explicit"]["session_buffer_size"] == 10
    assert result["effective"]["session_buffer_size"] == 20
    assert result["sources"]["session_buffer_size"] == "settings"
    assert not result["writable"]["session_buffer_size"]


def test_allowlist_save_promotes_environment_and_empty_shadows_it(monkeypatch):
    """QQ/Web 共享单键保存，显式空名单遮蔽环境且不改其他配置。"""
    current = {"base_url": "http://127.0.0.1:4000", "session_buffer_size": 7}
    env = {"MILKY_ALLOWED_CHATS": "group:*"}
    monkeypatch.setattr(
        settings,
        "_inputs",
        lambda: (copy.deepcopy(current), {}, copy.deepcopy(current), env, "synthetic"),
    )
    monkeypatch.setattr(settings, "_writable", lambda: dict.fromkeys(settings.KEYS, True))
    module = ModuleType("hermes_cli.plugins_state")
    writes = []

    def save(_plugin, keys, value):
        writes.append(keys)
        current[keys[0]] = value

    module.save_plugin_setting = save
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins_state", module)
    before = settings.read()
    assert before["sources"]["allowed_chats"] == "environment"
    assert settings.save(before["version"], {"allowed_chats": []})["status"] == "saved"
    after = settings.read()
    assert after["effective"]["allowed_chats"] == []
    assert after["sources"]["allowed_chats"] == "settings"
    assert after["runtime_status"] == "unknown"
    assert current["session_buffer_size"] == 7 and writes == [("allowed_chats",)]
