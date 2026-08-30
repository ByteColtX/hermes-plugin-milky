"""验证 fake Hermes 与 fake Milky 之间的模型可控出站交接。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from adapter import MilkyAdapter
from milky.client import SendResult
from outbound.sender import MilkyOutboundSender


@dataclass
class FakeMilky:
    """记录最终发送 body，并返回递增的远端消息序号。"""

    calls: list[tuple[str, int, list[dict[str, Any]]]] = field(default_factory=list)
    next_message_seq: int = 2001

    async def send_group_message(self, group_id: int, message: list[dict[str, Any]]) -> SendResult:
        self.calls.append(("group", group_id, message))
        result = SendResult(str(self.next_message_seq))
        self.next_message_seq += 1
        return result

    async def send_private_message(self, user_id: int, message: list[dict[str, Any]]) -> SendResult:
        self.calls.append(("dm", user_id, message))
        result = SendResult(str(self.next_message_seq))
        self.next_message_seq += 1
        return result


@dataclass(frozen=True)
class MessageHeader:
    """提供模型可见的当前消息和历史消息头。"""

    uid: str | None
    msg_id: str | None


class FakeHermes:
    """模拟模型输出、历史上下文和忙碌期间的有界交接。"""

    def __init__(self, adapter: MilkyAdapter) -> None:
        self._adapter = adapter
        self.contexts: list[tuple[MessageHeader, tuple[MessageHeader, ...]]] = []
        self.pending: list[tuple[str, MessageHeader]] = []

    async def deliver(
        self,
        content: str,
        current: MessageHeader,
        history: tuple[MessageHeader, ...],
        *,
        busy: bool = False,
    ) -> object | None:
        """提交一次模型输出，忙碌时只排队一次。"""

        self.contexts.append((current, history))
        if busy:
            self.pending.append((content, current))
            return None
        return await self._adapter._send_with_retry(
            "group:700000001",
            content,
            reply_to=current.msg_id,
        )

    async def flush_pending(self) -> None:
        """在 Hermes busy 状态结束后交接每个待处理输出一次。"""

        pending = tuple(self.pending)
        self.pending.clear()
        for content, current in pending:
            await self.deliver(content, current, (), busy=False)


def make_adapter(client: FakeMilky) -> MilkyAdapter:
    """创建已连接但不启动生命周期的 fake adapter。"""

    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = MilkyOutboundSender(client)
    return adapter


def test_model_controls_cover_plain_at_reply_combo_history_and_busy_handoff() -> None:
    """模型可独立选择控制码，忙碌交接不重复发送且不带隐式引用。"""

    async def scenario() -> tuple[FakeMilky, FakeHermes]:
        client = FakeMilky()
        hermes = FakeHermes(make_adapter(client))
        current = MessageHeader(uid="10001", msg_id="9001")
        history = (MessageHeader(uid="10002", msg_id="8999"),)

        await hermes.deliver("普通回复", current, history)
        await hermes.deliver("[CQ:at,qq=10001]", current, history)
        await hermes.deliver("[CQ:reply,id=8999]引用回复", current, history)
        await hermes.deliver(
            "[CQ:reply,id=8999][CQ:at,qq=10001]组合回复",
            current,
            history,
        )
        await hermes.deliver("[CQ:at,qq=10002]忙碌后的回复", current, history, busy=True)
        await hermes.flush_pending()
        return client, hermes

    client, hermes = asyncio.run(scenario())

    assert len(client.calls) == 5
    assert client.calls[0][2] == [{"type": "text", "data": {"text": "普通回复"}}]
    assert client.calls[1][2] == [{"type": "mention", "data": {"user_id": 10001}}]
    assert client.calls[2][2] == [
        {"type": "reply", "data": {"message_seq": 8999}},
        {"type": "text", "data": {"text": "引用回复"}},
    ]
    assert client.calls[3][2] == [
        {"type": "reply", "data": {"message_seq": 8999}},
        {"type": "mention", "data": {"user_id": 10001}},
        {"type": "text", "data": {"text": "组合回复"}},
    ]
    assert client.calls[4][2] == [
        {"type": "mention", "data": {"user_id": 10002}},
        {"type": "text", "data": {"text": "忙碌后的回复"}},
    ]
    assert all(
        segment["type"] != "reply" or segment["data"]["message_seq"] != 9001
        for _, _, message in client.calls
        for segment in message
    )
    assert hermes.contexts[0] == (
        MessageHeader(uid="10001", msg_id="9001"),
        (MessageHeader(uid="10002", msg_id="8999"),),
    )
