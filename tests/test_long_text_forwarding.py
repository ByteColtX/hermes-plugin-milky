"""验证超长文本合并转发的路由、身份和预检边界。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from config import load_config
from milky.client import ActionError, SendResult
from milky.models import LoginInfo
from outbound.formatter import image_segment, record_segment, text_segment, video_segment
from outbound.sender import MilkyOutboundSender
from outbound.standalone import make_standalone_sender

DEFAULT_ENV = {
    "MILKY_BASE_URL": "https://localhost:5500/milky",
    "MILKY_ACCESS_TOKEN": "fixture-token",
}


@dataclass
class ForwardClient:
    """记录 forward 请求并提供脱敏身份结果。"""

    login: object = field(default_factory=lambda: LoginInfo(900000001, "合成机器人"))
    login_error: ActionError | None = None
    send_error: ActionError | None = None
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    login_calls: int = 0
    next_message_seq: int = 7001

    async def get_login_info(self) -> object:
        """返回一次 standalone 身份查询结果。"""

        self.login_calls += 1
        if self.login_error is not None:
            raise self.login_error
        return self.login

    async def send_group_message(self, group_id: int, message: list[dict[str, Any]]) -> SendResult:
        """记录群消息并返回合成 message_seq。"""

        self.calls.append(("send_group_message", {"group_id": group_id, "message": message}))
        if self.send_error is not None:
            raise self.send_error
        message_id = str(self.next_message_seq)
        self.next_message_seq += 1
        return SendResult(message_id)

    async def send_private_message(self, user_id: int, message: list[dict[str, Any]]) -> SendResult:
        """记录私聊消息并返回合成 message_seq。"""

        self.calls.append(("send_private_message", {"user_id": user_id, "message": message}))
        if self.send_error is not None:
            raise self.send_error
        message_id = str(self.next_message_seq)
        self.next_message_seq += 1
        return SendResult(message_id)

    async def close(self) -> None:
        """提供 standalone 清理边界。"""


def _forward_body(client: ForwardClient) -> dict[str, Any]:
    """返回唯一消息 Action 的请求体。"""

    assert len(client.calls) == 1
    message = client.calls[0][1]["message"]
    assert len(message) == 1
    assert message[0]["type"] == "forward"
    return message[0]["data"]


def _text_content(nodes: list[dict[str, Any]]) -> str:
    """拼接 forward 节点中的文本以验证可逆顺序。"""

    return "".join(
        segment["data"]["text"]
        for node in nodes
        for segment in node["segments"]
        if segment["type"] == "text"
    )


def test_threshold_zero_keeps_ordinary_chunking_without_identity_request() -> None:
    """默认关闭时长文本仍按普通消息分块且不读取身份。"""

    client = ForwardClient()
    sender = MilkyOutboundSender(client, max_text_length=2, identity_loader=client.get_login_info)

    result = asyncio.run(sender.send("dm:800000001", "一二三四五"))

    assert result.success is True
    assert len(client.calls) == 3
    assert client.login_calls == 0
    assert all(body["message"][0]["type"] == "text" for _, body in client.calls)


def test_forward_uses_one_action_and_confirmed_identity() -> None:
    """超阈值普通长文本应形成一个 forward 并复用确认身份。"""

    client = ForwardClient()
    sender = MilkyOutboundSender(
        client,
        max_text_length=4,
        long_text_forward_threshold=4,
        identity_loader=client.get_login_info,
    )

    result = asyncio.run(sender.send("group:700000001", "一二三四五六七八"))

    assert result.success is True
    assert result.message_id == "7001"
    assert result.continuation_message_ids == ()
    forward = _forward_body(client)
    assert [(node["user_id"], node["sender_name"]) for node in forward["messages"]] == [
        (900000001, "合成机器人"),
        (900000001, "合成机器人"),
    ]
    assert _text_content(forward["messages"]) == "一二三四五六七八"
    assert client.login_calls == 1


def test_forward_private_target_uses_private_action_and_single_message_id() -> None:
    """私聊 forward 也只调用一次对应的 private message Action。"""

    client = ForwardClient()
    sender = MilkyOutboundSender(
        client,
        long_text_forward_threshold=1,
        identity_loader=client.get_login_info,
    )

    result = asyncio.run(sender.send("dm:800000001", "超长文本"))

    assert result.success is True
    assert result.message_id == "7001"
    assert result.continuation_message_ids == ()
    assert client.calls[0][0] == "send_private_message"
    assert client.calls[0][1]["user_id"] == 800000001
    assert client.calls[0][1]["message"][0]["type"] == "forward"


def test_threshold_is_strictly_greater_and_literal_split_counts() -> None:
    """等于阈值不转发，而字面量 `[SPLIT]` 计入可见长度。"""

    equal_client = ForwardClient()
    equal_sender = MilkyOutboundSender(
        equal_client,
        long_text_forward_threshold=4,
        identity_loader=equal_client.get_login_info,
    )
    equal_result = asyncio.run(equal_sender.send("dm:800000001", "一二三四"))

    assert equal_result.success is True
    assert equal_client.calls[0][1]["message"] == [{"type": "text", "data": {"text": "一二三四"}}]
    assert equal_client.login_calls == 0

    literal_client = ForwardClient()
    literal_sender = MilkyOutboundSender(
        literal_client,
        long_text_forward_threshold=8,
        identity_loader=literal_client.get_login_info,
    )
    literal_result = asyncio.run(literal_sender.send("dm:800000001", "a[[SPLIT]]b"))

    assert literal_result.success is True
    assert _text_content(_forward_body(literal_client)["messages"]) == "a[SPLIT]b"


def test_forward_keeps_all_split_sections_without_three_message_limit() -> None:
    """forward 路径保留超过三个有效逻辑段及其顺序。"""

    client = ForwardClient(login_error=ActionError("rejected", "get_login_info", "fixture"))
    sender = MilkyOutboundSender(
        client,
        max_text_length=2,
        long_text_forward_threshold=1,
        identity_loader=client.get_login_info,
    )
    content = "一\n[SPLIT]\n二\n[SPLIT]\n三\n[SPLIT]\n四\n[SPLIT]\n五"

    result = asyncio.run(sender.send("dm:800000001", content))

    assert result.success is True
    forward = _forward_body(client)
    assert len(forward["messages"]) == 5
    assert _text_content(forward["messages"]) == "一二三四五"
    assert {(node["user_id"], node["sender_name"]) for node in forward["messages"]} == {
        (10001, "QQ用户")
    }
    assert client.login_calls == 1


def test_forward_uses_4096_character_chunk_boundary() -> None:
    """forward 节点仍遵守既有 4096 字符文本边界。"""

    client = ForwardClient()
    sender = MilkyOutboundSender(
        client,
        max_text_length=4096,
        long_text_forward_threshold=4096,
    )

    result = asyncio.run(sender.send("dm:800000001", "x" * 4097))

    assert result.success is True
    nodes = _forward_body(client)["messages"]
    assert [len(_text_content([node])) for node in nodes] == [4096, 1]


def test_forward_action_failure_is_not_retried_or_fallback_to_plain_text() -> None:
    """forward 远端失败保持分类且只提交一次 Action。"""

    client = ForwardClient(
        send_error=ActionError("transport_unknown", "send_group_message", "fixture")
    )
    sender = MilkyOutboundSender(client, long_text_forward_threshold=1)

    result = asyncio.run(sender.send("group:700000001", "超长文本"))

    assert result.success is False
    assert result.error_kind == "transport_unknown"
    assert len(client.calls) == 1
    assert client.calls[0][0] == "send_group_message"


def test_ordered_native_media_batch_enters_same_forward() -> None:
    """同一 structured batch 中的文本和 native media 不拆成独立顶层 Action。"""

    client = ForwardClient()
    sender = MilkyOutboundSender(
        client,
        long_text_forward_threshold=3,
        identity_loader=client.get_login_info,
    )
    content = [
        text_segment("前置文本"),
        image_segment("https://media.example.invalid/fixture.png"),
        record_segment("base64://fixture-audio"),
        video_segment("https://media.example.invalid/fixture.mp4"),
    ]

    result = asyncio.run(sender.send("group:700000001", content))

    assert result.success is True
    nodes = _forward_body(client)["messages"]
    assert [segment["type"] for segment in nodes[0]["segments"]] == [
        "text",
        "image",
        "record",
        "video",
    ]
    assert len(client.calls) == 1


def test_forward_preflight_failure_does_not_send_partial_message(tmp_path) -> None:
    """nested native media 本地预检失败时不得产生消息 Action。"""

    client = ForwardClient()
    sender = MilkyOutboundSender(client, long_text_forward_threshold=1)
    missing_path = tmp_path / "missing-fixture.png"

    result = asyncio.run(
        sender.send(
            "group:700000001",
            [text_segment("超长文本"), image_segment(str(missing_path))],
        )
    )

    assert result.success is False
    assert result.error_kind == "invalid_input"
    assert client.calls == []


def test_standalone_forward_reads_identity_only_on_threshold_path() -> None:
    """standalone forward 使用一次登录查询，普通文本不增加查询。"""

    client = ForwardClient()
    config = load_config(DEFAULT_ENV | {"MILKY_LONG_TEXT_FORWARD_THRESHOLD": "1"})
    sender = make_standalone_sender(config, client_factory=lambda _config: client)

    result = asyncio.run(sender(object(), "dm:800000001", "standalone"))

    assert result == {"success": True, "message_id": "7001"}
    assert client.login_calls == 1
    assert _forward_body(client)["messages"][0]["user_id"] == 900000001


def test_standalone_ordinary_path_does_not_read_identity() -> None:
    """standalone 未触发阈值时不创建额外的身份 Action。"""

    client = ForwardClient()
    config = load_config(DEFAULT_ENV | {"MILKY_LONG_TEXT_FORWARD_THRESHOLD": "1"})
    sender = make_standalone_sender(config, client_factory=lambda _config: client)

    result = asyncio.run(sender(object(), "dm:800000001", "x"))

    assert result == {"success": True, "message_id": "7001"}
    assert client.login_calls == 0
    assert client.calls == [
        (
            "send_private_message",
            {
                "user_id": 800000001,
                "message": [{"type": "text", "data": {"text": "x"}}],
            },
        )
    ]
