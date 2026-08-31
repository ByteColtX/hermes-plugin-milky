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

_CHAT_KEY_PATTERN = re.compile(r"^(group|dm):([0-9]+)$")
_ACTION_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_INTEGER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)$")

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
        }


def load_config(environment: Mapping[str, str] | None = None) -> MilkyConfig:
    """从环境映射一次性解析并校验 Milky 配置。"""

    values: Mapping[str, str] = os.environ if environment is None else environment

    missing = [name for name in ("MILKY_BASE_URL", "MILKY_ACCESS_TOKEN") if not values.get(name)]
    if missing:
        raise ConfigError(f"缺少必需配置: {', '.join(missing)}")

    base_url = _normalize_base_url(values["MILKY_BASE_URL"])
    access_token = _required_text(values["MILKY_ACCESS_TOKEN"], "MILKY_ACCESS_TOKEN")
    allowed_chats = _parse_allowed_chats(values.get("MILKY_ALLOWED_CHATS", ""))
    will_policy = _parse_will_policy(values.get("MILKY_WILL_POLICY", ""))
    session_buffer_size = _parse_non_negative_integer(
        values.get("MILKY_SESSION_BUFFER_SIZE", "20"),
        "MILKY_SESSION_BUFFER_SIZE",
    )
    home_channel = _parse_home_channel(values.get("MILKY_HOME_CHANNEL"))
    return MilkyConfig(
        base_url=base_url,
        access_token=access_token,
        allowed_chats=allowed_chats,
        will_policy=will_policy,
        session_buffer_size=session_buffer_size,
        home_channel=home_channel,
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
    """解析完整的 group/dm chat key 白名单。"""

    if value is None or (isinstance(value, str) and not value.strip()):
        return frozenset()
    if not isinstance(value, str):
        raise ConfigError("MILKY_ALLOWED_CHATS must be a comma-separated string")
    items = [item.strip() for item in value.split(",")]
    if any(not item for item in items):
        raise ConfigError("MILKY_ALLOWED_CHATS contains an empty chat key")
    return frozenset(_normalize_chat_key(item) for item in items)


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
    if "keywords" in values:
        keywords = values["keywords"]
        if not isinstance(keywords, list) or any(
            not isinstance(keyword, str) or not keyword.strip() for keyword in keywords
        ):
            raise ConfigError("MILKY_WILL_POLICY.willingness.keywords must be non-empty strings")
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


__all__ = ["ConfigError", "MilkyConfig", "load_config", "parse_config"]
