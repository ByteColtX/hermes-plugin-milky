"""验证 Milky 启动配置和 manifest 契约。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import ConfigError, load_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ENV = {
    "MILKY_BASE_URL": "https://localhost:5500/milky/",
    "MILKY_ACCESS_TOKEN": "test-token-that-must-not-leak",
}

FULL_WILL_POLICY = {
    "engine": "routing",
    "routing": {
        "direct": "trigger",
        "mention": "trigger",
        "mentionAll": "wait",
        "mentionHere": "wait",
        "quote": "wait",
        "image": "wait",
        "poke": "wait",
        "group": "wait",
    },
    "willingness": {
        "maxScore": 100,
        "initialScore": 0,
        "decayHalfLifeSeconds": 600,
        "probabilityThreshold": 55,
        "probabilityAmplifier": 0.04,
        "replyCost": 35,
        "textGain": 12,
        "mentionGain": 100,
        "quoteGain": 15,
        "directGain": 40,
        "imageGain": 8,
        "pokeGain": 80,
        "keywords": [],
        "keywordMultiplier": 1.2,
        "defaultMultiplier": 1,
        "hotWindowSeconds": 15,
        "warmWindowSeconds": 60,
        "hotDecayWeight": 0.3,
        "warmDecayWeight": 0.7,
        "mentionForce": False,
        "quoteForce": False,
        "directForce": False,
    },
    "priority": 1000,
}


def test_load_config_derives_prefixed_urls_and_bearer_header() -> None:
    """配置应保留 path prefix，并只将 token 放入认证 header。"""

    config = load_config(DEFAULT_ENV)

    assert config.base_url == "https://localhost:5500/milky"
    assert config.home_channel is None
    assert config.action_url("get_group_list") == (
        "https://localhost:5500/milky/api/get_group_list"
    )
    assert config.event_url == "https://localhost:5500/milky/event"
    assert config.auth_headers == {
        "Authorization": "Bearer test-token-that-must-not-leak",
    }
    assert "test-token-that-must-not-leak" not in repr(config.redacted_summary())
    assert "test-token-that-must-not-leak" not in repr(config)


@pytest.mark.parametrize("missing", ["MILKY_BASE_URL", "MILKY_ACCESS_TOKEN"])
def test_load_config_reports_missing_required_name_without_secret(missing: str) -> None:
    """缺少必需配置时只报告配置名，不回显凭证。"""

    environment = DEFAULT_ENV.copy()
    environment.pop(missing)

    with pytest.raises(ConfigError, match=missing) as error:
        load_config(environment)

    assert "test-token-that-must-not-leak" not in str(error.value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ftp://localhost:5500",
        "localhost:5500",
        "https://",
        "https://host:not-a-port",
        "https://host?secret=1",
    ],
)
def test_load_config_rejects_invalid_base_url(value: str) -> None:
    """配置应拒绝无法安全派生 HTTP/SSE 地址的基址。"""

    environment = DEFAULT_ENV | {"MILKY_BASE_URL": value}

    with pytest.raises(ConfigError, match="MILKY_BASE_URL"):
        load_config(environment)


@pytest.mark.parametrize(
    "value",
    [
        "group:123,dm:456",
        " group:123 , dm:456 ",
    ],
)
def test_load_config_normalizes_chat_allowlist(value: str) -> None:
    """白名单应保留完整且命名空间隔离的 chat key。"""

    config = load_config(DEFAULT_ENV | {"MILKY_ALLOWED_CHATS": value})

    assert config.allowed_chats == frozenset({"group:123", "dm:456"})


@pytest.mark.parametrize(
    "value",
    ["group:abc", "private:123", "group:1:2", "dm:-1", "group:", "group: 1"],
)
def test_load_config_rejects_invalid_chat_allowlist(value: str) -> None:
    """白名单中的非法目标不得被静默转换。"""

    with pytest.raises(ConfigError, match="MILKY_ALLOWED_CHATS"):
        load_config(DEFAULT_ENV | {"MILKY_ALLOWED_CHATS": value})


def test_load_config_uses_complete_nested_will_defaults_and_buffer_size() -> None:
    """省略策略时应使用完整嵌套默认值，buffer 默认 20。"""

    config = load_config(DEFAULT_ENV)

    assert config.session_buffer_size == 20
    assert config.will_policy == FULL_WILL_POLICY


def test_load_config_preserves_complete_nested_will_policy() -> None:
    """完整嵌套策略应按原 schema 保留，而不是合并旧扁平字段。"""

    config = load_config(
        DEFAULT_ENV
        | {
            "MILKY_WILL_POLICY": json.dumps(FULL_WILL_POLICY),
            "MILKY_SESSION_BUFFER_SIZE": "0",
        }
    )

    assert config.will_policy == FULL_WILL_POLICY
    assert config.session_buffer_size == 0


@pytest.mark.parametrize(
    "policy",
    [
        {"engine": "unknown"},
        {"engine": "routing", "routing": {"direct": "maybe"}},
        {"engine": "routing", "willingness": {"maxScore": True}},
        {"engine": "routing", "willingness": {"keywords": [1]}},
        {"direct": "trigger"},
    ],
)
def test_load_config_rejects_invalid_or_flat_will_policy(policy: dict) -> None:
    """非法或旧扁平策略应返回安全配置错误。"""

    with pytest.raises(ConfigError, match="MILKY_WILL_POLICY"):
        load_config(DEFAULT_ENV | {"MILKY_WILL_POLICY": json.dumps(policy)})


def test_load_config_does_not_include_token_in_policy_error() -> None:
    """配置错误即使发生在凭证同时存在时也不得回显 token。"""

    with pytest.raises(ConfigError) as error:
        load_config(
            DEFAULT_ENV
            | {
                "MILKY_WILL_POLICY": "not-json",
                "MILKY_ACCESS_TOKEN": "another-secret-token",
            }
        )

    assert "another-secret-token" not in str(error.value)


@pytest.mark.parametrize("value", ["-1", "1.5", "not-an-int"])
def test_load_config_rejects_invalid_session_buffer_size(value: str) -> None:
    """历史缓冲上限只接受非负十进制整数。"""

    with pytest.raises(ConfigError, match="MILKY_SESSION_BUFFER_SIZE"):
        load_config(DEFAULT_ENV | {"MILKY_SESSION_BUFFER_SIZE": value})


@pytest.mark.parametrize(
    ("value", "expected"),
    [("group:700000001", "group:700000001"), (" dm:800000001 ", "dm:800000001")],
)
def test_load_config_preserves_home_channel_as_outbound_target(value: str, expected: str) -> None:
    """home channel 应独立于入站白名单保存为规范化目标。"""

    config = load_config(DEFAULT_ENV | {"MILKY_HOME_CHANNEL": value})

    assert config.home_channel == expected
    assert config.allowed_chats == frozenset()
    assert config.redacted_summary()["has_home_channel"] is True
    assert expected not in repr(config.redacted_summary())


@pytest.mark.parametrize(
    "value",
    [
        "   ",
        "home",
        "temp:700000001",
        "group:",
        "group:-1",
        "group:1:2",
        "dm:abc",
    ],
)
def test_load_config_rejects_invalid_home_channel_without_echoing_value(value: str) -> None:
    """home channel 只接受完整 group/dm chat key，错误不得回显输入。"""

    with pytest.raises(ConfigError, match="MILKY_HOME_CHANNEL") as error:
        load_config(DEFAULT_ENV | {"MILKY_HOME_CHANNEL": value})

    assert value.strip() not in str(error.value) or not value.strip()


def test_load_config_treats_empty_home_channel_as_unconfigured() -> None:
    """可选环境变量为空字符串时不创建隐式 home 目标。"""

    config = load_config(DEFAULT_ENV | {"MILKY_HOME_CHANNEL": ""})

    assert config.home_channel is None
    assert config.redacted_summary()["has_home_channel"] is False


def test_manifest_declares_only_the_new_environment_contract_and_tools() -> None:
    """manifest 应只暴露新环境变量和三项显式 ToolSpec。"""

    manifest = (PROJECT_ROOT / "plugin.yaml").read_text(encoding="utf-8")

    assert "MILKY_BASE_URL" in manifest
    assert "MILKY_ACCESS_TOKEN" in manifest
    assert "MILKY_ALLOWED_CHATS" in manifest
    assert "MILKY_WILL_POLICY" in manifest
    assert "MILKY_SESSION_BUFFER_SIZE" in manifest
    assert "MILKY_HOME_CHANNEL" in manifest
    assert "provides_tools:" in manifest
    assert manifest.count("  - milky_profile_like") == 1
    assert manifest.count("  - milky_nudge") == 1
    assert manifest.count("  - milky_recall_group_message") == 1
