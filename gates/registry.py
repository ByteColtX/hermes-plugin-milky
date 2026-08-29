"""实现 T09 的三道确定性入站门禁及固定顺序 registry。"""

from __future__ import annotations

from collections.abc import Iterable

from session.identity import validate_chat_key

from .base import Gate, GateContext, GateResult


class SelfMessageGate(Gate):
    """拒绝 Bot 自己发出的消息。"""

    name = "self_message"

    def check(self, context: GateContext) -> GateResult:
        """根据 sender 和 self 身份做确定性判断。"""

        if context.sender_id == context.self_id:
            return GateResult(False, self.name)
        return GateResult(True, "passed")


class ChatAllowlistGate(Gate):
    """按完整的 namespaced chat key 执行白名单门禁。"""

    name = "chat_allowlist"

    def __init__(self, allowed_chats: Iterable[str] | None = None) -> None:
        """保存已校验的完整 chat key 白名单。"""

        values = () if allowed_chats is None else allowed_chats
        self._allowed_chats = frozenset(validate_chat_key(value) for value in values)

    @property
    def allowed_chats(self) -> frozenset[str]:
        """返回不可变的白名单快照。"""

        return self._allowed_chats

    def check(self, context: GateContext) -> GateResult:
        """只按完整 chat key 匹配，不读取数值部分或其他字段。"""

        if not self._allowed_chats or context.chat_key in self._allowed_chats:
            return GateResult(True, "passed")
        return GateResult(False, "chat_not_allowed")


class MutedGroupGate(Gate):
    """拒绝成员禁言、全体禁言或未确认禁言状态的群消息。"""

    name = "muted_group"

    def check(self, context: GateContext) -> GateResult:
        """只读取调用方提供的二态快照，不主动查询状态。"""

        if context.scene == "friend":
            return GateResult(True, "passed")
        if context.scene != "group":
            return GateResult(False, "unsupported_scene")
        if context.member_mute == "muted":
            return GateResult(False, "member_muted")
        if context.member_mute != "unmuted":
            return GateResult(False, "mute_state_unknown")
        if context.whole_mute == "muted":
            return GateResult(False, "whole_muted")
        if context.whole_mute != "unmuted":
            return GateResult(False, "mute_state_unknown")
        return GateResult(True, "passed")


class GateRegistry:
    """以固定顺序短路执行 Self、allowlist 和 mute 三道 Gate。"""

    def __init__(self, allowed_chats: Iterable[str] | None = None) -> None:
        """创建只读配置的 Gate registry。"""

        self._gates: tuple[Gate, ...] = (
            SelfMessageGate(),
            ChatAllowlistGate(allowed_chats),
            MutedGroupGate(),
        )

    @property
    def gates(self) -> tuple[Gate, ...]:
        """返回固定顺序的 Gate 快照。"""

        return self._gates

    @property
    def gate_names(self) -> tuple[str, ...]:
        """返回用于诊断和回归测试的稳定 Gate 名称顺序。"""

        return tuple(gate.name for gate in self._gates)

    def check(self, context: GateContext) -> GateResult:
        """按固定顺序检查上下文，并在首个拒绝处停止。"""

        for gate in self._gates:
            result = gate.check(context)
            if not result.allow:
                return result
        return GateResult(True, "allowed")

    def evaluate(self, context: GateContext) -> GateResult:
        """提供语义化的 Gate 判断入口。"""

        return self.check(context)

    def run(self, context: GateContext) -> GateResult:
        """提供 pipeline 使用的兼容入口。"""

        return self.check(context)


__all__ = [
    "ChatAllowlistGate",
    "GateRegistry",
    "MutedGroupGate",
    "SelfMessageGate",
]
