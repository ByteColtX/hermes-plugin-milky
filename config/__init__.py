"""Milky 插件启动配置、默认值和安全摘要。"""

from __future__ import annotations

import copy
import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from session.identity import ChatKeyError, validate_chat_rule

_CHAT_KEY_PATTERN = re.compile(r"^(group|dm):([0-9]+)$")
_ACTION_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_INTEGER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)$")

MIN_LOCAL_MEDIA_BYTES = 8 * 1024 * 1024
MAX_LOCAL_MEDIA_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_LOCAL_MEDIA_BYTES = MAX_LOCAL_MEDIA_BYTES
MAX_LONG_TEXT_FORWARD_THRESHOLD = 4096
DEFAULT_LONG_TEXT_FORWARD_THRESHOLD = 0

_ROUTING_DEFAULTS = {
    "direct": "trigger",
    "mention": "trigger",
    "mentionAll": "wait",
    "quote": "wait",
    "poke": "wait",
    "allMessage": "wait",
    "keywords": [],
}
_WILLINGNESS_DEFAULTS = {
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
    "interestKeywords": [],
    "forceKeywords": [],
    "keywordMultiplier": 1.2,
    "defaultMultiplier": 1,
    "hotWindowSeconds": 15,
    "warmWindowSeconds": 60,
    "hotDecayWeight": 0.3,
    "warmDecayWeight": 0.7,
    "mentionForce": False,
    "quoteForce": False,
    "directForce": False,
}
_DEFAULT_WILL_POLICY = {
    "engine": "routing",
    "routing": _ROUTING_DEFAULTS,
    "willingness": _WILLINGNESS_DEFAULTS,
    "priority": 1000,
}


class ConfigError(ValueError):
    """表示启动配置缺失、类型错误或值域错误。"""


@dataclass(frozen=True, slots=True)
class MilkyConfig:
    """保存一次解析后的 Milky 启动配置。"""

    base_url: str
    access_token: str = field(repr=False)
    allowed_chats: frozenset[str] = field(default_factory=frozenset, repr=False)
    will_policy: dict[str, Any] = field(default_factory=dict, repr=False)
    session_buffer_size: int = 20
    home_channel: str | None = field(default=None, repr=False)
    max_local_media_bytes: int = DEFAULT_MAX_LOCAL_MEDIA_BYTES
    long_text_forward_threshold: int = DEFAULT_LONG_TEXT_FORWARD_THRESHOLD
    group_member_event_notifications: bool = False

    @property
    def event_url(self) -> str:
        """返回带 path prefix 的 SSE 事件地址。"""

        return f"{self.base_url}/event"

    def action_url(self, action: str) -> str:
        """返回一个已校验 Action 的 HTTP 地址。"""

        if not isinstance(action, str) or not _ACTION_PATTERN.fullmatch(action):
            raise ConfigError("Action 名称必须只包含 ASCII 字母、数字或下划线")
        return f"{self.base_url}/api/{action}"

    @property
    def auth_headers(self) -> dict[str, str]:
        """返回 Milky HTTP 请求所需的认证 header。"""

        return {"Authorization": f"Bearer {self.access_token}"}

    def redacted_summary(self) -> dict[str, object]:
        """返回不包含 token、header 或聊天 ID 的配置摘要。"""

        return {
            "base_url": self.base_url,
            "allowed_chat_count": len(self.allowed_chats),
            "will_engine": self.will_policy["engine"],
            "session_buffer_size": self.session_buffer_size,
            "has_access_token": bool(self.access_token),
            "has_home_channel": self.home_channel is not None,
            "max_local_media_bytes": self.max_local_media_bytes,
            "long_text_forward_threshold": self.long_text_forward_threshold,
            "group_member_event_notifications": self.group_member_event_notifications,
        }


SETTING_DEFAULTS = {
    "base_url": None,
    "allowed_chats": [],
    "will_policy": _DEFAULT_WILL_POLICY,
    "session_buffer_size": 20,
    "home_channel": "",
    "max_local_media_bytes": DEFAULT_MAX_LOCAL_MEDIA_BYTES,
    "long_text_forward_threshold": DEFAULT_LONG_TEXT_FORWARD_THRESHOLD,
    "group_member_event_notifications": False,
}


def _native_environment(key: str, value: object) -> str:
    """将已验证原生类型转换为旧解析器的输入，不接受隐式类型转换。"""
    name = "MILKY_" + key.upper()
    if key in {"base_url", "home_channel"}:
        if not isinstance(value, str):
            raise ConfigError(name + " type error")
        return value
    if key == "allowed_chats":
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise ConfigError(name + " type error")
        for rule in value:
            validate_chat_rule(rule)
        return ",".join(value)
    if key == "will_policy":
        if not isinstance(value, dict):
            raise ConfigError(name + " type error")
        return json.dumps(value)
    if key == "group_member_event_notifications":
        if type(value) is not bool:
            raise ConfigError(name + " type error")
        return "true" if value else "false"
    if type(value) is not int:
        raise ConfigError(name + " type error")
    return str(value)


def resolve_settings(*, settings=None, legacy=None, environment=None, allow_missing=False):
    """逐键选源并统一校验普通设置；Will 整体选源，凭证不参与。"""
    settings = {} if settings is None else settings
    legacy = {} if legacy is None else legacy
    environment = {} if environment is None else environment
    if not isinstance(settings, Mapping) or not isinstance(legacy, Mapping):
        raise ConfigError("settings type error")
    if set(settings) - set(SETTING_DEFAULTS) or set(legacy) - set(SETTING_DEFAULTS):
        raise ConfigError("unknown settings field")
    selected, sources = {}, {}
    for key, default in SETTING_DEFAULTS.items():
        env_name = "MILKY_" + key.upper()
        if key in settings:
            value, source = settings[key], "settings"
        elif key in legacy:
            value, source = legacy[key], "legacy"
        elif env_name in environment:
            value, source = environment[env_name], "environment"
        else:
            value, source = copy.deepcopy(default), "default"
        sources[key] = source
        if key == "base_url" and source != "default" and not value:
            raise ConfigError("MILKY_BASE_URL invalid")
        if value is None and key == "base_url" and source == "default":
            if allow_missing:
                selected[env_name] = ""
                continue
            raise ConfigError("缺少必需配置: MILKY_BASE_URL")
        selected[env_name] = value if source == "environment" else _native_environment(key, value)
    effective = {
        "base_url": _normalize_base_url(selected["MILKY_BASE_URL"])
        if selected["MILKY_BASE_URL"]
        else "",
        "allowed_chats": sorted(_parse_allowed_chats(selected["MILKY_ALLOWED_CHATS"])),
        "will_policy": _parse_will_policy(selected["MILKY_WILL_POLICY"]),
        "session_buffer_size": _parse_non_negative_integer(
            selected["MILKY_SESSION_BUFFER_SIZE"], "MILKY_SESSION_BUFFER_SIZE"
        ),
        "home_channel": _parse_home_channel(selected["MILKY_HOME_CHANNEL"]) or "",
        "max_local_media_bytes": _parse_max_local_media_bytes(
            selected["MILKY_MAX_LOCAL_MEDIA_BYTES"]
        ),
        "long_text_forward_threshold": _parse_long_text_forward_threshold(
            selected["MILKY_LONG_TEXT_FORWARD_THRESHOLD"]
        ),
        "group_member_event_notifications": _parse_boolean(
            selected["MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS"],
            "MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS",
        ),
    }
    if not effective["base_url"] and not allow_missing:
        raise ConfigError("缺少必需配置: MILKY_BASE_URL")
    return {"effective": effective, "sources": sources}


def load_config(
    environment: Mapping[str, str] | None = None, *, settings=None, legacy=None
) -> MilkyConfig:
    """解析同一 profile 的设置、旧配置、环境和独立凭证启动快照。"""
    if environment is None:
        try:
            from agent.secret_scope import get_secret
            from hermes_cli.config import load_config_readonly
        except ImportError:
            environment = os.environ
        else:
            host = load_config_readonly()
            entry = host.get("plugins", {}).get("entries", {}).get("hermes-plugin-milky", {})
            settings = entry.get("settings", {}) if settings is None else settings
            legacy = entry.get("config", {}) if legacy is None else legacy
            names = ["MILKY_" + key.upper() for key in SETTING_DEFAULTS] + ["MILKY_ACCESS_TOKEN"]
            environment = {name: value for name in names if (value := get_secret(name)) is not None}
    resolved = resolve_settings(settings=settings, legacy=legacy, environment=environment)
    token = _required_text(environment.get("MILKY_ACCESS_TOKEN"), "MILKY_ACCESS_TOKEN")
    values = resolved["effective"]
    return MilkyConfig(
        **{
            **values,
            "allowed_chats": frozenset(values["allowed_chats"]),
            "home_channel": values["home_channel"] or None,
        },
        access_token=token,
    )


def parse_config(environment: Mapping[str, str] | None = None) -> MilkyConfig:
    """兼容调用方的配置解析命名。"""

    return load_config(environment)


def _required_text(value: object, name: str) -> str:
    """读取非空字符串，同时避免在错误中回显值。"""

    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")
    return value.strip()


def _normalize_base_url(value: object) -> str:
    """校验 HTTP(S) 基址并去除末尾斜杠。"""

    raw = _required_text(value, "MILKY_BASE_URL")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as error:
        raise ConfigError("MILKY_BASE_URL is malformed") from error
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError("MILKY_BASE_URL must be an absolute http or https URL")
    if port is not None and not 0 < port <= 65535:
        raise ConfigError("MILKY_BASE_URL contains an invalid port")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigError("MILKY_BASE_URL must not contain user credentials")
    if parsed.query or parsed.fragment:
        raise ConfigError("MILKY_BASE_URL must not contain a query or fragment")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _parse_allowed_chats(value: object) -> frozenset[str]:
    """解析具体 chat key 和受支持通配符组成的白名单。"""

    if value is None or (isinstance(value, str) and not value.strip()):
        return frozenset()
    if not isinstance(value, str):
        raise ConfigError("MILKY_ALLOWED_CHATS must be a comma-separated string")
    items = [item.strip() for item in value.split(",")]
    if any(not item for item in items):
        raise ConfigError("MILKY_ALLOWED_CHATS contains an empty chat key")
    return frozenset(_normalize_chat_rule(item) for item in items)


def _normalize_chat_rule(value: str) -> str:
    """规范化一个具体 chat key 或命名空间通配符。"""

    try:
        return validate_chat_rule(value)
    except ChatKeyError:
        raise ConfigError("MILKY_ALLOWED_CHATS contains an invalid chat rule") from None


def _normalize_chat_key(value: str) -> str:
    """校验并规范化单个 chat key。"""

    match = _CHAT_KEY_PATTERN.fullmatch(value)
    if match is None:
        raise ConfigError("MILKY_ALLOWED_CHATS contains an invalid chat key")
    return f"{match.group(1)}:{int(match.group(2))}"


def _parse_home_channel(value: object) -> str | None:
    """解析可选的出站 home channel chat key。"""

    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ConfigError("MILKY_HOME_CHANNEL contains an invalid chat key")
    if not value.strip():
        raise ConfigError("MILKY_HOME_CHANNEL contains an invalid chat key")
    try:
        return _normalize_chat_key(value.strip())
    except ConfigError:
        raise ConfigError("MILKY_HOME_CHANNEL contains an invalid chat key") from None


def _parse_will_policy(value: object) -> dict[str, Any]:
    """解析完整嵌套 Will policy，并对缺省字段填入架构默认值。"""

    if value is None or (isinstance(value, str) and not value.strip()):
        return copy.deepcopy(_DEFAULT_WILL_POLICY)
    if not isinstance(value, str):
        raise ConfigError("MILKY_WILL_POLICY must be a JSON object")
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as error:
        raise ConfigError("MILKY_WILL_POLICY is malformed JSON") from error
    if not isinstance(raw, dict):
        raise ConfigError("MILKY_WILL_POLICY must be a JSON object")

    _reject_unknown_keys(raw, {"engine", "routing", "willingness", "priority"}, "MILKY_WILL_POLICY")
    policy = copy.deepcopy(_DEFAULT_WILL_POLICY)
    if "engine" in raw:
        if raw["engine"] not in {"routing", "willingness"}:
            raise ConfigError("MILKY_WILL_POLICY.engine has an unsupported value")
        policy["engine"] = raw["engine"]
    if "routing" in raw:
        routing = _mapping_value(raw["routing"], "MILKY_WILL_POLICY.routing")
        _reject_unknown_keys(routing, set(_ROUTING_DEFAULTS), "MILKY_WILL_POLICY.routing")
        for key, routing_value in routing.items():
            if key == "keywords":
                _validate_routing_keywords(routing_value)
            elif not isinstance(routing_value, str) or routing_value not in {"wait", "trigger"}:
                raise ConfigError(f"MILKY_WILL_POLICY.routing.{key} has an unsupported value")
        policy["routing"].update(routing)
    if "willingness" in raw:
        willingness = _mapping_value(
            raw["willingness"],
            "MILKY_WILL_POLICY.willingness",
        )
        _reject_unknown_keys(
            willingness,
            set(_WILLINGNESS_DEFAULTS),
            "MILKY_WILL_POLICY.willingness",
        )
        _validate_willingness(willingness)
        policy["willingness"].update(copy.deepcopy(willingness))
    if "priority" in raw:
        policy["priority"] = _non_negative_number(raw["priority"], "MILKY_WILL_POLICY.priority")
    _validate_willingness(policy["willingness"])
    return policy


def _validate_routing_keywords(value: object) -> None:
    """校验 routing 的确定性关键词数组。"""

    if not isinstance(value, list) or any(
        not isinstance(keyword, str) or not keyword.strip() for keyword in value
    ):
        raise ConfigError(
            "MILKY_WILL_POLICY.routing.keywords must be an array of non-empty strings"
        )


def _validate_willingness(values: Mapping[str, Any]) -> None:
    """校验 willingness 的类型和值域。"""

    non_negative_fields = {
        "maxScore",
        "initialScore",
        "decayHalfLifeSeconds",
        "replyCost",
        "textGain",
        "mentionGain",
        "quoteGain",
        "directGain",
        "imageGain",
        "pokeGain",
        "keywordMultiplier",
        "defaultMultiplier",
        "hotWindowSeconds",
        "warmWindowSeconds",
        "hotDecayWeight",
        "warmDecayWeight",
    }
    for name in non_negative_fields:
        if name in values:
            _non_negative_number(values[name], f"MILKY_WILL_POLICY.willingness.{name}")
    if "maxScore" in values and values["maxScore"] <= 0:
        raise ConfigError("MILKY_WILL_POLICY.willingness.maxScore must be positive")
    if "probabilityThreshold" in values:
        threshold = _number(values["probabilityThreshold"], "probabilityThreshold")
        if not 0 <= threshold <= 100:
            raise ConfigError("MILKY_WILL_POLICY.willingness.probabilityThreshold out of range")
    if "probabilityAmplifier" in values:
        amplifier = _non_negative_number(
            values["probabilityAmplifier"],
            "MILKY_WILL_POLICY.willingness.probabilityAmplifier",
        )
        if amplifier > 1:
            raise ConfigError("MILKY_WILL_POLICY.willingness.probabilityAmplifier out of range")
    for name in ("interestKeywords", "forceKeywords"):
        if name in values:
            keywords = values[name]
            if not isinstance(keywords, list) or any(
                not isinstance(keyword, str) or not keyword.strip() for keyword in keywords
            ):
                raise ConfigError(
                    f"MILKY_WILL_POLICY.willingness.{name} must be an array of non-empty strings"
                )
    for name in ("mentionForce", "quoteForce", "directForce"):
        if name in values and not isinstance(values[name], bool):
            raise ConfigError(f"MILKY_WILL_POLICY.willingness.{name} must be boolean")
    if (
        "initialScore" in values
        and "maxScore" in values
        and values["initialScore"] > values["maxScore"]
    ):
        raise ConfigError("MILKY_WILL_POLICY.willingness.initialScore exceeds maxScore")


def _mapping_value(value: object, name: str) -> dict[str, Any]:
    """读取 JSON object，并复制为普通字典。"""

    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be an object")
    return value


def _reject_unknown_keys(values: Mapping[str, Any], allowed: set[str], name: str) -> None:
    """拒绝未纳入契约的配置字段。"""

    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ConfigError(f"{name} contains unsupported fields: {', '.join(unknown)}")


def _number(value: object, name: str) -> int | float:
    """读取不允许 boolean 冒充数字的数值。"""

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"MILKY_WILL_POLICY.willingness.{name} must be a number")
    if not math.isfinite(value):
        raise ConfigError(f"MILKY_WILL_POLICY.willingness.{name} must be finite")
    return value


def _non_negative_number(value: object, name: str) -> int | float:
    """读取非负数值。"""

    number = _number(value, name)
    if number < 0:
        raise ConfigError(f"{name} must be non-negative")
    return number


def _parse_non_negative_integer(value: object, name: str) -> int:
    """解析非负十进制整数配置。"""

    if not isinstance(value, str) or not _INTEGER_PATTERN.fullmatch(value.strip()):
        raise ConfigError(f"{name} must be a non-negative integer")
    return int(value)


def _parse_boolean(value: object, name: str) -> bool:
    """解析大小写不敏感的布尔配置。"""

    if not isinstance(value, str):
        raise ConfigError(f"{name} must be true or false")
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ConfigError(f"{name} must be true or false")


def _parse_max_local_media_bytes(value: object) -> int:
    """解析本地出站资源上限的十进制字节数。"""

    name = "MILKY_MAX_LOCAL_MEDIA_BYTES"
    if not isinstance(value, str) or not _INTEGER_PATTERN.fullmatch(value.strip()):
        raise ConfigError(f"{name} must be a decimal integer")
    parsed = int(value)
    if not MIN_LOCAL_MEDIA_BYTES <= parsed <= MAX_LOCAL_MEDIA_BYTES:
        raise ConfigError(f"{name} is out of range")
    return parsed


def _parse_long_text_forward_threshold(value: object) -> int:
    """解析超长文本合并转发阈值。"""

    name = "MILKY_LONG_TEXT_FORWARD_THRESHOLD"
    if not isinstance(value, str) or not _INTEGER_PATTERN.fullmatch(value.strip()):
        raise ConfigError(f"{name} must be a decimal integer")
    parsed = int(value)
    if not 0 <= parsed <= MAX_LONG_TEXT_FORWARD_THRESHOLD:
        raise ConfigError(f"{name} is out of range")
    return parsed


def validate_max_local_media_bytes(value: object) -> int:
    """校验已经解析的本地出站资源上限。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("max_local_media_bytes must be an integer")
    if not MIN_LOCAL_MEDIA_BYTES <= value <= MAX_LOCAL_MEDIA_BYTES:
        raise ValueError("max_local_media_bytes is out of range")
    return value


__all__ = [
    "DEFAULT_LONG_TEXT_FORWARD_THRESHOLD",
    "DEFAULT_MAX_LOCAL_MEDIA_BYTES",
    "MAX_LOCAL_MEDIA_BYTES",
    "MAX_LONG_TEXT_FORWARD_THRESHOLD",
    "MIN_LOCAL_MEDIA_BYTES",
    "ConfigError",
    "MilkyConfig",
    "load_config",
    "parse_config",
    "validate_max_local_media_bytes",
]
