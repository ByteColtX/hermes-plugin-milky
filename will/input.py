"""Will 决策使用的、与协议 raw 解耦的输入快照。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from milky.models import Segment

MentionKind = Literal["self", "all", "here", "none"]


@dataclass(frozen=True, slots=True)
class WillInput:
    """提供给 routing 和 willingness 的稳定消息特征。"""

    event_type: str
    scene: str
    self_id: int
    chat_key: str
    channel: str
    timestamp: int
    segments: tuple[Segment, ...]
    text: str
    mention_kinds: tuple[MentionKind, ...]
    has_reply: bool
    reply_message_seq: int | None
    has_image: bool
    is_self_quote: bool = False
    is_self_poke: bool = False

    @property
    def mention_kind(self) -> MentionKind:
        """返回兼容单值调用方的主要 mention 类型。"""

        for kind in ("self", "all", "here"):
            if kind in self.mention_kinds:
                return kind  # type: ignore[return-value]
        return "none"

    @property
    def mention_self(self) -> bool:
        """返回是否直接提及 Bot。"""

        return "self" in self.mention_kinds

    @property
    def mention_all(self) -> bool:
        """返回是否全体提及。"""

        return "all" in self.mention_kinds

    @property
    def mention_here(self) -> bool:
        """返回是否明确识别到 mention here 扩展。"""

        return "here" in self.mention_kinds

    @property
    def has_quote(self) -> bool:
        """返回是否存在 reply segment。"""

        return self.has_reply

    @property
    def self_quote(self) -> bool:
        """返回 reply 是否明确指向 Bot。"""

        return self.is_self_quote

    @property
    def has_self_quote(self) -> bool:
        """返回是否存在指向 Bot 的 reply。"""

        return self.is_self_quote

    @property
    def self_poke(self) -> bool:
        """返回 nudge 是否明确由协议确认 Bot 为接收者。"""

        return self.is_self_poke

    @property
    def has_self_poke(self) -> bool:
        """返回是否存在指向 Bot 的 poke 观察。"""

        return self.is_self_poke

    @property
    def image(self) -> bool:
        """返回是否包含图片 segment。"""

        return self.has_image

    @property
    def is_direct(self) -> bool:
        """返回是否为 friend 私聊。"""

        return self.scene == "friend"


__all__ = ["MentionKind", "WillInput"]
