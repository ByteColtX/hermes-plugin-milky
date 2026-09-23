"""验证普通文本出站精确拦截及非文本入口隔离。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from adapter import MilkyAdapter
from milky.client import SendResult
from outbound.sender import MilkyOutboundSender
from outbound.text_interceptor import (
    HERMES_UNEXPECTED_SILENCE_REPLY,
    should_intercept_text,
)


class RecordingClient:
    """记录合成消息 Action，不访问 Milky 服务。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def send_group_message(self, group_id: int, message: list[dict[str, Any]]) -> SendResult:
        """记录群消息 Action 并返回合成远端序号。"""

        self.calls.append(("send_group_message", {"group_id": group_id, "message": message}))
        return SendResult(message_seq="fixture-message-seq")

    async def send_private_message(self, user_id: int, message: list[dict[str, Any]]) -> SendResult:
        """记录私聊消息 Action 并返回合成远端序号。"""

        self.calls.append(("send_private_message", {"user_id": user_id, "message": message}))
        return SendResult(message_seq="fixture-message-seq")


class RecordingOutboundSender(MilkyOutboundSender):
    """记录 adapter 是否进入统一 sender。"""

    def __init__(self, client: RecordingClient) -> None:
        super().__init__(client)
        self.send_calls = 0

    async def send(
        self,
        chat_id: str,
        content: object,
        reply_to: object = None,
        metadata: object = None,
    ) -> object:
        """记录调用后交给真实 sender 逻辑。"""

        self.send_calls += 1
        return await super().send(chat_id, content, reply_to, metadata)  # type: ignore[arg-type]


def make_adapter(sender: object, *, connected: bool = True) -> MilkyAdapter:
    """创建仅配置出站状态的 adapter。"""

    adapter = object.__new__(MilkyAdapter)
    adapter._connected = connected
    adapter._closed = not connected
    adapter._outbound = sender
    return adapter


def test_interceptor_matches_complete_values_and_accepts_multiple_rules() -> None:
    """拦截器只做完整相等比较，并支持调用方登记多条规则。"""

    assert should_intercept_text(HERMES_UNEXPECTED_SILENCE_REPLY)
    assert should_intercept_text("second rule", ("first rule", "second rule"))
    assert not should_intercept_text("prefix " + HERMES_UNEXPECTED_SILENCE_REPLY)
    assert not should_intercept_text(  # type: ignore[arg-type]
        HERMES_UNEXPECTED_SILENCE_REPLY.encode("utf-8")
    )


def test_adapter_intercepts_before_sender_and_message_action() -> None:
    """完整命中在 sender 和 Milky 消息 Action 前终止，且不伪造消息 ID。"""

    client = RecordingClient()
    sender = RecordingOutboundSender(client)
    adapter = make_adapter(sender)

    result = asyncio.run(adapter.send("group:700000001", HERMES_UNEXPECTED_SILENCE_REPLY))

    assert result.success is True
    assert result.message_id is None
    assert sender.send_calls == 0
    assert client.calls == []


def test_connection_check_precedes_text_interception() -> None:
    """断开时仍返回原有 unsupported 结果，不将文本当作已处理。"""

    client = RecordingClient()
    sender = RecordingOutboundSender(client)
    adapter = make_adapter(sender, connected=False)

    result = asyncio.run(adapter.send("group:700000001", HERMES_UNEXPECTED_SILENCE_REPLY))

    assert result.success is False
    assert result.error_kind == "unsupported"
    assert sender.send_calls == 0
    assert client.calls == []


@pytest.mark.parametrize(
    "content",
    [
        "解释：" + HERMES_UNEXPECTED_SILENCE_REPLY + " 这是额外内容。",
        "前缀 " + HERMES_UNEXPECTED_SILENCE_REPLY,
        HERMES_UNEXPECTED_SILENCE_REPLY + " 后缀",
        " " + HERMES_UNEXPECTED_SILENCE_REPLY,
        HERMES_UNEXPECTED_SILENCE_REPLY + " ",
        HERMES_UNEXPECTED_SILENCE_REPLY.removesuffix(".") + "!",
        HERMES_UNEXPECTED_SILENCE_REPLY.lower(),
    ],
)
def test_nonmatching_text_continues_through_existing_send_path(content: str) -> None:
    """嵌入、前后缀及空白/标点/大小写差异均继续正常发送。"""

    client = RecordingClient()
    sender = RecordingOutboundSender(client)
    adapter = make_adapter(sender)

    result = asyncio.run(adapter.send("group:700000001", content))

    assert result.success is True
    assert result.message_id == "fixture-message-seq"
    assert sender.send_calls == 1
    assert len(client.calls) == 1


class RecordingMediaSender:
    """记录媒体和文件专用入口收到的调用。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def send_image(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("send_image", args, kwargs))
        return object()

    async def send_document(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("send_document", args, kwargs))
        return object()


def test_media_and_file_entries_do_not_intercept_matching_caption() -> None:
    """媒体和文件入口携带同一文案时仍走各自既有 sender。"""

    sender = RecordingMediaSender()
    adapter = make_adapter(sender)

    async def scenario() -> None:
        await adapter.send_image(
            "group:700000001",
            "https://media.example.invalid/fixture.png",
            caption=HERMES_UNEXPECTED_SILENCE_REPLY,
        )
        await adapter.send_document(
            "group:700000001",
            "https://media.example.invalid/fixture.txt",
            caption=HERMES_UNEXPECTED_SILENCE_REPLY,
            file_name="fixture.txt",
        )

    asyncio.run(scenario())

    assert [name for name, _, _ in sender.calls] == ["send_image", "send_document"]
    assert all(
        kwargs["caption"] == HERMES_UNEXPECTED_SILENCE_REPLY for _, _, kwargs in sender.calls
    )
