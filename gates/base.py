from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class InboundContext:
    scene: str  # group 或 private 场景。
    peer_id: str  # group_id 或 user_id。
    user_id: str
    text: str
    is_at_me: bool
    raw: dict
    # 后续可以增加 message_id、timestamp、member_role 等字段。


@dataclass
class GateResult:
    allow: bool
    reason: str = ""


class Gate(ABC):
    name: str

    @abstractmethod
    async def check(self, ctx: InboundContext) -> GateResult: ...
