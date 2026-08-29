"""基于规范化策略特征的确定性 Will routing。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .input import WillInput

Decision = Literal["wait", "trigger"]


@dataclass(frozen=True, slots=True)
class RoutingConfig:
    """保存八类 routing 动作的独立配置。"""

    direct: Decision = "trigger"
    mention: Decision = "trigger"
    mention_all: Decision = "wait"
    mention_here: Decision = "wait"
    quote: Decision = "wait"
    image: Decision = "wait"
    poke: Decision = "wait"
    group: Decision = "wait"

    def __post_init__(self) -> None:
        """拒绝未纳入 routing 契约的动作值。"""

        for name in (
            "direct",
            "mention",
            "mention_all",
            "mention_here",
            "quote",
            "image",
            "poke",
            "group",
        ):
            if getattr(self, name) not in {"wait", "trigger"}:
                raise ValueError(f"routing.{name} must be wait or trigger")

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
            "mentionHere": "mention_here",
            "quote": "quote",
            "image": "image",
            "poke": "poke",
            "group": "group",
        }
        unknown = sorted(set(value) - set(aliases))
        if unknown:
            raise ValueError("routing contains unsupported fields")
        values = {aliases[key]: value[key] for key in value}
        return cls(**values)  # type: ignore[arg-type]

    @property
    def mentionAll(self) -> Decision:
        """返回外部 schema 使用的全体提及动作名。"""

        return self.mention_all

    @property
    def mentionHere(self) -> Decision:
        """返回外部 schema 使用的 here 提及动作名。"""

        return self.mention_here


class RoutingWillEngine:
    """按固定优先级将一个规范化输入路由为 wait 或 trigger。"""

    def __init__(self, config: RoutingConfig | Mapping[str, object] | None = None) -> None:
        """创建不执行任何外部操作的 routing engine。"""

        if isinstance(config, RoutingConfig):
            self.config = config
        elif config is None or isinstance(config, Mapping):
            self.config = RoutingConfig.from_mapping(config)
        else:
            raise TypeError("config must be a RoutingConfig or object")

    def decide(self, input_value: WillInput) -> Decision:
        """按 direct、mention、quote、image、group 顺序返回消息动作。"""

        if not isinstance(input_value, WillInput):
            raise TypeError("input_value must be a WillInput")
        if input_value.event_type != "message_receive":
            return "wait"
        if input_value.is_direct:
            return self.config.direct
        if input_value.mention_self:
            return self.config.mention
        if input_value.mention_all:
            return self.config.mention_all
        if input_value.mention_here:
            return self.config.mention_here
        if input_value.has_reply:
            return self.config.quote
        if input_value.has_image:
            return self.config.image
        return self.config.group

    def route(self, input_value: WillInput) -> Decision:
        """提供语义化的 routing 调用入口。"""

        return self.decide(input_value)


__all__ = ["Decision", "RoutingConfig", "RoutingWillEngine"]
