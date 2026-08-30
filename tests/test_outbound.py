"""验证 Hermes 出站内容、上传和显式工具的安全边界。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from milky.client import ActionError
from milky.client import SendResult as MilkySendResult
from milky.models import MilkyEnvelope
from outbound.chunking import chunk_text
from outbound.formatter import (
    OutboundFormatError,
    face_segment,
    format_message,
    forward_segment,
    image_segment,
    light_app_segment,
    mention_all_segment,
    mention_segment,
    record_segment,
    reply_segment,
    text_segment,
    video_segment,
)
from outbound.sender import MilkyOutboundSender
from outbound.tools import bind_sender, unbind_sender
from tools import register_tools


@dataclass
class FakeOutboundClient:
    """记录出站 Action，并提供可控的脱敏结果。"""

    message_sequences: list[int] = field(default_factory=lambda: [101, 102, 103, 104])
    error: ActionError | None = None
    delay: float = 0

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.upload_calls: list[tuple[str, dict[str, Any]]] = []

    async def send_group_message(
        self, group_id: int, message: list[dict[str, Any]]
    ) -> MilkySendResult:
        self.calls.append(("send_group_message", {"group_id": group_id, "message": message}))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return MilkySendResult(str(self.message_sequences.pop(0)))

    async def send_private_message(
        self, user_id: int, message: list[dict[str, Any]]
    ) -> MilkySendResult:
        self.calls.append(("send_private_message", {"user_id": user_id, "message": message}))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return MilkySendResult(str(self.message_sequences.pop(0)))

    async def upload_group_file_from_path(
        self,
        group_id: int,
        file_path: object,
        file_name: str,
        *,
        parent_folder_id: object = None,
    ) -> MilkyEnvelope:
        self.upload_calls.append(
            (
                "upload_group_file",
                {
                    "group_id": group_id,
                    "file_path": file_path,
                    "file_name": file_name,
                    "parent_folder_id": parent_folder_id,
                },
            )
        )
        if self.error is not None:
            raise self.error
        return MilkyEnvelope("ok", 0, {"file_id": "uploaded-group-file"})

    async def upload_private_file_from_path(
        self, user_id: int, file_path: object, file_name: str
    ) -> MilkyEnvelope:
        self.upload_calls.append(
            (
                "upload_private_file",
                {"user_id": user_id, "file_path": file_path, "file_name": file_name},
            )
        )
        if self.error is not None:
            raise self.error
        return MilkyEnvelope("ok", 0, {"file_id": "uploaded-private-file"})

    async def send_profile_like(self, user_id: int, count: object = None) -> MilkyEnvelope:
        params: dict[str, Any] = {"user_id": user_id}
        if count is not None:
            params["count"] = count
        self.calls.append(("send_profile_like", params))
        return MilkyEnvelope("ok", 0, {})

    async def send_friend_nudge(self, user_id: int, is_self: object = None) -> MilkyEnvelope:
        params: dict[str, Any] = {"user_id": user_id}
        if is_self is not None:
            params["is_self"] = is_self
        self.calls.append(("send_friend_nudge", params))
        return MilkyEnvelope("ok", 0, {})

    async def send_group_nudge(self, group_id: int, user_id: int) -> MilkyEnvelope:
        self.calls.append(("send_group_nudge", {"group_id": group_id, "user_id": user_id}))
        return MilkyEnvelope("ok", 0, {})

    async def recall_group_message(self, group_id: int, message_seq: int) -> MilkyEnvelope:
        self.calls.append(
            ("recall_group_message", {"group_id": group_id, "message_seq": message_seq})
        )
        return MilkyEnvelope("ok", 0, {})


@dataclass
class FakeMuteTracker:
    """记录群发送失败通知。"""

    failures: list[str] = field(default_factory=list)

    async def refresh_after_send_failure(self, target: str) -> bool:
        self.failures.append(target)
        return True


def test_formatter_emits_confirmed_milky_outgoing_segments() -> None:
    """格式化器应生成 OpenAPI 已确认的 outgoing segment 字段。"""

    message = format_message(
        [
            text_segment("hello"),
            mention_segment(900000001),
            mention_all_segment(),
            face_segment("14", is_large=True),
            reply_segment(1005),
            image_segment("base64://image"),
            record_segment("base64://record"),
            video_segment("base64://video"),
            forward_segment(
                [
                    {
                        "time": 1700000000,
                        "user_id": 900000001,
                        "sender_name": "合成发送者",
                        "segments": [text_segment("转发内容")],
                    }
                ]
            ),
            light_app_segment('{"app":"fixture"}'),
        ]
    )

    assert message == [
        {"type": "text", "data": {"text": "hello"}},
        {"type": "mention", "data": {"user_id": 900000001}},
        {"type": "mention_all", "data": {}},
        {"type": "face", "data": {"face_id": "14", "is_large": True}},
        {"type": "reply", "data": {"message_seq": 1005}},
        {"type": "image", "data": {"uri": "base64://image"}},
        {"type": "record", "data": {"uri": "base64://record"}},
        {"type": "video", "data": {"uri": "base64://video"}},
        {
            "type": "forward",
            "data": {
                "messages": [
                    {
                        "time": 1700000000,
                        "user_id": 900000001,
                        "sender_name": "合成发送者",
                        "segments": [text_segment("转发内容")],
                    }
                ]
            },
        },
        {"type": "light_app", "data": {"json_payload": '{"app":"fixture"}'}},
    ]


@pytest.mark.parametrize(
    "value",
    [
        [],
        "   ",
        [{"type": "file", "data": {"uri": "base64://not-a-message"}}],
        [{"type": "unknown_extension", "data": {"secret": "do-not-echo"}}],
    ],
)
def test_formatter_rejects_empty_file_and_unknown_content_without_echo(value: object) -> None:
    """空内容、file 和未知 segment 应本地拒绝且不回显不可信值。"""

    with pytest.raises(OutboundFormatError) as error_info:
        format_message(value)

    assert error_info.value.classification in {"invalid_input", "unsupported"}
    assert "do-not-echo" not in str(error_info.value)


def test_chunking_preserves_content_and_prefers_explicit_whitespace_boundaries() -> None:
    """分块不得截断内容，并在可行时把换行或空格作为边界。"""

    content = "第一段\n第二段 第三段"
    chunks = chunk_text(content, max_length=6)

    assert "".join(chunks) == content
    assert all(len(chunk) <= 6 for chunk in chunks)
    assert chunks == ("第一段\n", "第二段 ", "第三段")


def test_sender_routes_group_and_dm_and_uses_remote_message_sequence() -> None:
    """发送器应按 chat namespace 选择 Action，并返回稳定远端 ID。"""

    client = FakeOutboundClient([1001, 1002])
    sender = MilkyOutboundSender(client)

    group_result = asyncio.run(sender.send("group:700000001", "群消息"))
    dm_result = asyncio.run(sender.send("dm:800000001", "私聊消息"))

    assert group_result.success is True
    assert group_result.message_id == "1001"
    assert dm_result.message_id == "1002"
    assert [call[0] for call in client.calls] == [
        "send_group_message",
        "send_private_message",
    ]
    assert client.calls[0][1]["message"] == [{"type": "text", "data": {"text": "群消息"}}]


def test_sender_integrates_structured_media_segments_without_implicit_reply() -> None:
    """媒体和 caption 应保持顺序，Hermes 隐式 reply 不应进入消息。"""

    client = FakeOutboundClient([1101])
    sender = MilkyOutboundSender(client)

    result = asyncio.run(
        sender.send_image(
            "dm:800000001",
            "https://media.example/image",
            caption="图片说明",
            reply_to="1005",
        )
    )

    assert result.success is True
    assert client.calls[0][1]["message"] == [
        {"type": "text", "data": {"text": "图片说明"}},
        {"type": "image", "data": {"uri": "https://media.example/image"}},
    ]


def test_sender_converts_explicit_cq_controls_for_group_and_dm() -> None:
    """group 和 dm 请求都应使用模型显式选择的 native segment。"""

    client = FakeOutboundClient([1102, 1103])
    sender = MilkyOutboundSender(client)

    group_result = asyncio.run(
        sender.send(
            "group:700000001",
            "[CQ:reply,id=9001][CQ:at,qq=10001]群答复",
            reply_to="9002",
        )
    )
    dm_result = asyncio.run(
        sender.send("dm:800000001", "[CQ:at,qq=10002]私聊答复", reply_to="9003")
    )

    assert group_result.message_id == "1102"
    assert dm_result.message_id == "1103"
    assert client.calls[0] == (
        "send_group_message",
        {
            "group_id": 700000001,
            "message": [
                {"type": "reply", "data": {"message_seq": 9001}},
                {"type": "mention", "data": {"user_id": 10001}},
                {"type": "text", "data": {"text": "群答复"}},
            ],
        },
    )
    assert client.calls[1] == (
        "send_private_message",
        {
            "user_id": 800000001,
            "message": [
                {"type": "mention", "data": {"user_id": 10002}},
                {"type": "text", "data": {"text": "私聊答复"}},
            ],
        },
    )


def test_sender_keeps_cq_fallback_and_sends_once_on_remote_failure() -> None:
    """CQ fallback 只改变 body，远端失败仍只调用一次 send。"""

    client = FakeOutboundClient(
        error=ActionError("transport_unknown", "send_group_message", "unknown")
    )
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("group:700000001", "前[CQ:future,x=y]后"))

    assert result.error_kind == "transport_unknown"
    assert len(client.calls) == 1
    assert client.calls[0][1]["message"] == [
        {"type": "text", "data": {"text": "前"}},
        {"type": "text", "data": {"text": "[CQ:future,x=y]"}},
        {"type": "text", "data": {"text": "后"}},
    ]


def test_senders_for_different_chats_can_progress_concurrently() -> None:
    """不同目标的出站调用不应被 sender 共享锁串行阻塞。"""

    client = FakeOutboundClient([1201, 1202], delay=0.01)
    sender = MilkyOutboundSender(client)

    async def send_both() -> list[Any]:
        """并发发送两个独立目标。"""

        return await asyncio.gather(
            sender.send("group:700000001", "群"),
            sender.send("dm:800000001", "私聊"),
        )

    results = asyncio.run(send_both())

    assert [result.message_id for result in results] == ["1201", "1202"]
    assert {call[0] for call in client.calls} == {
        "send_group_message",
        "send_private_message",
    }


@pytest.mark.parametrize(
    "target", ["", "temp:700000001", "group:-1", "group:1:2", "private:800000001"]
)
def test_sender_rejects_temp_and_invalid_targets_before_network(target: str) -> None:
    """临时或非法目标不得回退到其他 namespace 或访问网络。"""

    client = FakeOutboundClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send(target, "不会发送"))

    assert result.success is False
    assert result.error_kind in {"invalid_input", "unsupported"}
    assert client.calls == []


def test_sender_rejects_blank_message_before_network() -> None:
    """空白消息应在 Action 之前返回本地输入错误。"""

    client = FakeOutboundClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("group:700000001", " \n\t"))

    assert result.success is False
    assert result.error_kind == "invalid_input"
    assert client.calls == []


def test_sender_sends_long_text_as_ordered_chunks() -> None:
    """超长文本应完整拆分，并把各 chunk 的远端结果保留下来。"""

    client = FakeOutboundClient([201, 202, 203])
    sender = MilkyOutboundSender(client, max_text_length=4)

    result = asyncio.run(sender.send("dm:800000001", "abcdefghijk"))

    assert result.success is True
    assert result.message_id == "203"
    assert result.continuation_message_ids == ("201", "202")
    assert [call[1]["message"][0]["data"]["text"] for call in client.calls] == [
        "abcd",
        "efgh",
        "ijk",
    ]


def test_sender_keeps_action_error_category_and_refreshes_only_group_failure() -> None:
    """群 Action 失败应保留分类并通知 tracker，私聊失败不得查询群状态。"""

    tracker = FakeMuteTracker()
    group_client = FakeOutboundClient(
        error=ActionError("rejected", "send_group_message", "permission denied")
    )
    group_sender = MilkyOutboundSender(group_client, mute_tracker=tracker)
    group_result = asyncio.run(group_sender.send("group:700000001", "失败"))

    dm_client = FakeOutboundClient(
        error=ActionError("transport_unknown", "send_private_message", "request outcome unknown")
    )
    dm_sender = MilkyOutboundSender(dm_client, mute_tracker=tracker)
    dm_result = asyncio.run(dm_sender.send("dm:800000001", "失败"))

    assert group_result.error_kind == "rejected"
    assert dm_result.error_kind == "transport_unknown"
    assert tracker.failures == ["group:700000001"]
    assert len(group_client.calls) == 1
    assert len(dm_client.calls) == 1


def test_sender_uploads_file_separately_and_never_builds_file_message_segment(tmp_path) -> None:
    """document/file 出站必须使用独立 upload Action。"""

    file_path = tmp_path / "fixture.txt"
    file_path.write_text("fixture", encoding="utf-8")
    client = FakeOutboundClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send_document("group:700000001", str(file_path)))

    assert result.success is True
    assert result.message_id == "uploaded-group-file"
    assert client.calls == []
    assert client.upload_calls[0][0] == "upload_group_file"
    assert client.upload_calls[0][1]["file_name"] == "fixture.txt"


def test_group_file_upload_failure_keeps_category_and_notifies_tracker(tmp_path) -> None:
    """文件上传失败应保留错误分类，并只通知对应群刷新。"""

    file_path = tmp_path / "fixture.txt"
    file_path.write_text("fixture", encoding="utf-8")
    tracker = FakeMuteTracker()
    client = FakeOutboundClient(
        error=ActionError("rejected", "upload_group_file", "permission denied")
    )
    sender = MilkyOutboundSender(client, mute_tracker=tracker)

    result = asyncio.run(sender.send_document("group:700000001", file_path))

    assert result.success is False
    assert result.error_kind == "rejected"
    assert client.calls == []
    assert len(client.upload_calls) == 1
    assert tracker.failures == ["group:700000001"]


def test_local_file_upload_rejects_missing_path_before_action(tmp_path) -> None:
    """不可读本地文件不得进入 upload Action。"""

    client = FakeOutboundClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send_document("group:700000001", tmp_path / "missing.txt"))

    assert result.success is False
    assert result.error_kind == "invalid_input"
    assert client.upload_calls == []


def test_sender_does_not_retry_recall_or_unknown_transport() -> None:
    """撤回和发送未知结果均只能调用一次，不得盲目重试。"""

    client = FakeOutboundClient()
    sender = MilkyOutboundSender(client)

    recall_result = asyncio.run(sender.recall_group_message("group:700000001", "123"))
    assert recall_result.success is True
    assert client.calls == [("recall_group_message", {"group_id": 700000001, "message_seq": 123})]

    client.error = ActionError("transport_unknown", "send_group_message", "unknown")
    send_result = asyncio.run(sender.send("group:700000001", "一次"))
    assert send_result.error_kind == "transport_unknown"
    assert len(client.calls) == 2


class ToolContext:
    """捕获 Hermes 显式 ToolSpec 注册参数。"""

    def __init__(self) -> None:
        self.registered: list[dict[str, Any]] = []

    def register_tool(self, **kwargs: Any) -> None:
        self.registered.append(kwargs)


def test_tools_register_exactly_three_explicit_specs_and_validate_arguments() -> None:
    """工具发现只注册三个显式能力，并在网络前校验参数。"""

    context = ToolContext()
    register_tools(context)

    names = [item["name"] for item in context.registered]
    assert names == ["milky_profile_like", "milky_nudge", "milky_recall_group_message"]
    assert all(item["is_async"] is True for item in context.registered)
    assert {item["schema"]["name"] for item in context.registered} == set(names)

    client = FakeOutboundClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        handlers = {item["name"]: item["handler"] for item in context.registered}
        invalid = json.loads(asyncio.run(handlers["milky_profile_like"]({"user_id": True})))
        invalid_type = json.loads(
            asyncio.run(handlers["milky_profile_like"]({"user_id": "800000001"}))
        )
        invalid_nudge = json.loads(
            asyncio.run(handlers["milky_nudge"]({"target": "group:700000001"}))
        )
        assert invalid["classification"] == "invalid_input"
        assert invalid_type["classification"] == "invalid_input"
        assert invalid_nudge["classification"] == "invalid_input"
        assert client.calls == []
    finally:
        unbind_sender()


def test_tools_call_confirmed_actions_after_local_validation() -> None:
    """工具通过本地校验后才调用对应的 Milky Action。"""

    context = ToolContext()
    register_tools(context)
    handlers = {item["name"]: item["handler"] for item in context.registered}
    client = FakeOutboundClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        profile = json.loads(
            asyncio.run(handlers["milky_profile_like"]({"user_id": 800000001, "count": 2}))
        )
        friend_nudge = json.loads(asyncio.run(handlers["milky_nudge"]({"target": "dm:800000001"})))
        group_nudge = json.loads(
            asyncio.run(
                handlers["milky_nudge"]({"target": "group:700000001", "user_id": 900000001})
            )
        )
        recall = json.loads(
            asyncio.run(
                handlers["milky_recall_group_message"](
                    {"target": "group:700000001", "message_seq": 123}
                )
            )
        )
    finally:
        unbind_sender()

    assert all(item["ok"] is True for item in (profile, friend_nudge, group_nudge, recall))
    assert [call[0] for call in client.calls] == [
        "send_profile_like",
        "send_friend_nudge",
        "send_group_nudge",
        "recall_group_message",
    ]


def test_profile_like_tool_omits_optional_count_when_not_provided() -> None:
    """名片点赞工具省略可选数量时不得发送伪造默认字段。"""

    context = ToolContext()
    register_tools(context)
    handler = next(
        item["handler"] for item in context.registered if item["name"] == "milky_profile_like"
    )
    client = FakeOutboundClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        result = json.loads(asyncio.run(handler({"user_id": 800000001})))
    finally:
        unbind_sender()

    assert result["ok"] is True
    assert client.calls == [("send_profile_like", {"user_id": 800000001})]


def test_outbound_fixture_directory_contains_sanitized_action_envelopes() -> None:
    """出站 Action fixture 应可读且不含凭证、真实路径或个人身份。"""

    fixture_dir = Path(__file__).parent / "fixtures" / "protocol" / "actions"
    names = {
        "send_group_message.ok.json",
        "send_private_message.ok.json",
        "send_profile_like.ok.json",
        "send_friend_nudge.ok.json",
        "send_group_nudge.ok.json",
        "recall_group_message.ok.json",
        "send_group_message.rejected.json",
    }
    for name in names:
        payload = json.loads((fixture_dir / name).read_text(encoding="utf-8"))
        assert payload["status"] in {"ok", "failed"}
        assert "Authorization" not in repr(payload)
        assert "token" not in repr(payload).lower()
