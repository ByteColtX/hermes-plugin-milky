"""定义入站 Gate 的纯确定性边界。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

ChatScene = Literal["friend", "group"]
MuteState = Literal["muted", "unmuted"]


@dataclass(frozen=True, slots=True)
class GateContext:
    """提供 Gate 所需的规范化身份和 MuteTracker 快照。"""

    self_id: str
    sender_id: str
    scene: ChatScene
    chat_key: str
    member_mute: MuteState = "muted"
    whole_mute: MuteState = "muted"


@dataclass(frozen=True, slots=True)
class GateResult:
    """表示一次无副作用的 Gate 判断结果。"""

    allow: bool
    reason: str


class Gate(ABC):
    """定义不执行网络或策略副作用的同步 Gate。"""

    name: str

    @abstractmethod
    def check(self, context: GateContext) -> GateResult:
        """根据已准备的上下文返回稳定的 allow/reject 结果。"""
