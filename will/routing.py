"""基于规范化策略特征的确定性 Will routing。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from .input import WillInput

Decision = Literal["wait", "trigger"]


@dataclass(frozen=True, slots=True)
class RoutingConfig:
    """保存 routing 动作和确定性关键词的独立配置。"""

    direct: Decision = "trigger"
    mention: Decision = "trigger"
    mention_all: Decision = "wait"
    quote: Decision = "wait"
    poke: Decision = "wait"
    all_message: Decision = "wait"
    keywords: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """拒绝未纳入 routing 契约的动作值。"""

        for name in (
            "direct",
            "mention",
            "mention_all",
            "quote",
            "poke",
            "all_message",
        ):
            if getattr(self, name) not in {"wait", "trigger"}:
                raise ValueError(f"routing.{name} must be wait or trigger")
        if not isinstance(self.keywords, tuple) or any(
            not isinstance(keyword, str) or not keyword.strip() for keyword in self.keywords
        ):
            raise ValueError("routing.keywords must contain non-empty strings")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object] | None = None) -> RoutingConfig:
        """从外部 camelCase mapping 构造 routing 配置。"""

        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise TypeError("routing must be an object")
        aliases = {
            "direct": "direct",
            "mention": "mention",
            "mentionAll": "mention_all",
            "quote": "quote",
            "poke": "poke",
            "allMessage": "all_message",
            "keywords": "keywords",
        }
        unknown = sorted(set(value) - set(aliases))
        if unknown:
            raise ValueError("routing contains unsupported fields")
        values: dict[str, object] = {aliases[key]: value[key] for key in value}
        if "keywords" in values:
            keywords = values["keywords"]
            if not isinstance(keywords, Sequence) or isinstance(keywords, (str, bytes)):
                raise TypeError("routing.keywords must be an array")
            values["keywords"] = tuple(keywords)
        return cls(**values)  # type: ignore[arg-type]

    @property
    def mentionAll(self) -> Decision:
        """返回外部 schema 使用的全体提及动作名。"""

        return self.mention_all

    @property
    def allMessage(self) -> Decision:
        """返回外部 schema 使用的全消息动作名。"""

        return self.all_message


class RoutingWillEngine:
    """按所有命中规则的 OR 结果将输入路由为 wait 或 trigger。"""

    def __init__(self, config: RoutingConfig | Mapping[str, object] | None = None) -> None:
        """创建不执行任何外部操作的 routing engine。"""

        if isinstance(config, RoutingConfig):
            self.config = config
        elif config is None or isinstance(config, Mapping):
            self.config = RoutingConfig.from_mapping(config)
        else:
            raise TypeError("config must be a RoutingConfig or object")

    def decide(self, input_value: WillInput) -> Decision:
        """合并普通消息的所有适用 routing 规则。"""

        if not isinstance(input_value, WillInput):
            raise TypeError("input_value must be a WillInput")
        if input_value.event_type != "message_receive":
            return "wait"
        matched_actions: list[Decision] = [self.config.all_message]
        if input_value.is_direct:
            matched_actions.append(self.config.direct)
        if input_value.mention_self:
            matched_actions.append(self.config.mention)
        if input_value.mention_all:
            matched_actions.append(self.config.mention_all)
        if input_value.has_reply:
            matched_actions.append(self.config.quote)
        if any(keyword in input_value.text for keyword in self.config.keywords):
            matched_actions.append("trigger")
        return "trigger" if "trigger" in matched_actions else "wait"

    def route(self, input_value: WillInput) -> Decision:
        """提供语义化的 routing 调用入口。"""

        return self.decide(input_value)


__all__ = ["Decision", "RoutingConfig", "RoutingWillEngine"]
