"""验证 `[SPLIT]` 文本分段和 Hermes 附件交接顺序。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from milky.client import ActionError, SendResult
from outbound.sender import MilkyOutboundSender
from outbound.splitting import normalize_outbound_text, split_outbound_text
from tests.fixtures.outbound_split_inputs import (
    CQ_INLINE_SPLIT_MESSAGE,
    CQ_SPLIT_MESSAGE,
    ORDERED_ATTACHMENT_FIXTURE,
    SENSITIVE_MARKERS,
    SPLIT_TEXT_CASES,
)


@dataclass
class SplitClient:
    """记录脱敏 Milky Action，并按索引注入一次失败。"""

    fail_at: int | None = None
    failure: ActionError | None = None
    next_message_seq: int = 2001
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def send_group_message(self, group_id: int, message: list[dict[str, Any]]) -> SendResult:
        return await self._send("send_group_message", group_id, message)

    async def send_private_message(self, user_id: int, message: list[dict[str, Any]]) -> SendResult:
        return await self._send("send_private_message", user_id, message)

    async def _send(self, action: str, peer_id: int, message: list[dict[str, Any]]) -> SendResult:
        self.calls.append((action, {"peer_id": peer_id, "message": message}))
        if self.fail_at is not None and len(self.calls) - 1 == self.fail_at:
            raise self.failure or ActionError("rejected", action, "fixture failure")
        message_seq = str(self.next_message_seq)
        self.next_message_seq += 1
        return SendResult(message_seq=message_seq)

    async def upload_group_file(
        self,
        group_id: int,
        file_uri: object,
        file_name: str,
        *,
        parent_folder_id: object = None,
    ) -> object:
        self.calls.append(
            (
                "upload_group_file",
                {
                    "peer_id": group_id,
                    "file_uri": file_uri,
                    "file_name": file_name,
                    "parent_folder_id": parent_folder_id,
                },
            )
        )
        if self.fail_at is not None and len(self.calls) - 1 == self.fail_at:
            raise self.failure or ActionError("rejected", "upload_group_file", "fixture failure")
        from milky.models import MilkyEnvelope

        return MilkyEnvelope("ok", 0, {"file_id": "fixture-uploaded-file"})

    async def upload_private_file(self, user_id: int, file_uri: object, file_name: str) -> object:
        self.calls.append(
            (
                "upload_private_file",
                {"peer_id": user_id, "file_uri": file_uri, "file_name": file_name},
            )
        )
        if self.fail_at is not None and len(self.calls) - 1 == self.fail_at:
            raise self.failure or ActionError("rejected", "upload_private_file", "fixture failure")
        from milky.models import MilkyEnvelope

        return MilkyEnvelope("ok", 0, {"file_id": "fixture-uploaded-file"})


@pytest.mark.parametrize("name", tuple(SPLIT_TEXT_CASES))
def test_split_fixture_covers_line_and_inline_marker_boundaries(name: str) -> None:
    """fixture 覆盖独立行、行中、转义和 CQ-like 边界。"""

    case = SPLIT_TEXT_CASES[name]
    result = split_outbound_text(case["value"])
    if case["sections"] is None:
        assert result is None
    else:
        assert result == case["sections"]
    if "normalized" in case:
        assert normalize_outbound_text(case["value"]) == case["normalized"]


def test_split_fixture_contains_no_credentials_real_urls_or_local_paths() -> None:
    """分段 fixture 只能包含脱敏文本和合成内联 URI。"""

    rendered = repr((SPLIT_TEXT_CASES, CQ_SPLIT_MESSAGE, ORDERED_ATTACHMENT_FIXTURE))
    assert all(marker not in rendered for marker in SENSITIVE_MARKERS)


def test_split_sections_preserve_internal_whitespace_without_marker_lines() -> None:
    """标记行及其分隔边界被删除，段内有意空白仍保留。"""

    assert split_outbound_text("  第一行  \n第二行\n[SPLIT]\n 第三行 ") == (
        "  第一行  \n第二行",
        " 第三行 ",
    )


def test_split_sections_remove_inline_marker_only() -> None:
    """行中标记只删除自身，不改动两侧空白或换行。"""

    assert split_outbound_text("第一段 [SPLIT] 第二段") == ("第一段 ", " 第二段")
    assert split_outbound_text("第一段[SPLIT]\n第二段") == ("第一段", "\n第二段")


@pytest.mark.parametrize(
    "content",
    [
        "第一段\n[SPLIT]\n\n第二段",
        "第一段\r\n[SPLIT]\r\n\r\n第二段",
    ],
)
def test_split_removes_blank_lines_adjacent_to_marker(content: str) -> None:
    """标记相邻的空行属于分隔边界，不应进入下一条消息。"""

    assert split_outbound_text(content) == ("第一段", "第二段")


def test_sender_does_not_prefix_split_section_with_blank_line() -> None:
    """模型在标记后多输出一个空行时，下一条消息仍从可见正文开始。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("dm:800000001", "可以试试\n[SPLIT]\n\n但别拿退群吓奶龙～"))

    assert result.success is True
    assert [body["message"] for _, body in client.calls] == [
        [{"type": "text", "data": {"text": "可以试试"}}],
        [{"type": "text", "data": {"text": "但别拿退群吓奶龙～"}}],
    ]


def test_sender_sends_split_text_in_order_and_removes_markers() -> None:
    """有效分段应按顺序串行发送，用户不可见标记不进入 body。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("group:700000001", "第一段\n[SPLIT]\n第二段"))

    assert result.success is True
    assert [body["message"] for _, body in client.calls] == [
        [{"type": "text", "data": {"text": "第一段"}}],
        [{"type": "text", "data": {"text": "第二段"}}],
    ]
    assert result.message_id == "2002"
    assert result.continuation_message_ids == ("2001",)


def test_sender_sends_inline_split_text_in_order() -> None:
    """普通正文行中的标记也应按顺序形成独立消息。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("dm:800000001", "第一段[SPLIT]第二段"))

    assert result.success is True
    assert [body["message"] for _, body in client.calls] == [
        [{"type": "text", "data": {"text": "第一段"}}],
        [{"type": "text", "data": {"text": "第二段"}}],
    ]


def test_sender_unescapes_literal_split_without_enabling_split_limit() -> None:
    """字面量转义应还原可见文本且不创建额外消息。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("dm:800000001", "显示[[SPLIT]]文本"))

    assert result.success is True
    assert [body["message"] for _, body in client.calls] == [
        [{"type": "text", "data": {"text": "显示[SPLIT]文本"}}],
    ]


def test_sender_splits_after_valid_unknown_cq_candidate() -> None:
    """语法完整但未知 type 的 CQ fallback 不吞掉候选之后的标记。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("dm:800000001", "前[CQ:future,x=y][SPLIT]后"))

    assert result.success is True
    assert [body["message"] for _, body in client.calls] == [
        [
            {"type": "text", "data": {"text": "前"}},
            {"type": "text", "data": {"text": "[CQ:future,x=y]"}},
        ],
        [{"type": "text", "data": {"text": "后"}}],
    ]


def test_sender_splits_inside_malformed_cq_like_text() -> None:
    """malformed CQ-like 文本中的标记按普通控制语法处理。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("dm:800000001", "前[CQ:at,qq=[SPLIT]后"))

    assert result.success is True
    assert [body["message"] for _, body in client.calls] == [
        [
            {"type": "text", "data": {"text": "前"}},
            {"type": "text", "data": {"text": "[CQ:at,qq="}},
        ],
        [{"type": "text", "data": {"text": "后"}}],
    ]


def test_sender_filters_empty_split_sections_and_rejects_marker_only() -> None:
    """空段不产生空消息，只有控制标记时沿用空出站的本地拒绝。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)
    result = asyncio.run(sender.send("dm:800000001", "第一段\n[SPLIT]\n[SPLIT]\n第二段"))
    empty_result = asyncio.run(sender.send("dm:800000001", "[SPLIT]\n[SPLIT]"))

    assert result.success is True
    assert [body["message"][0]["data"]["text"] for _, body in client.calls] == [
        "第一段",
        "第二段",
    ]
    assert empty_result.success is False
    assert empty_result.error_kind == "invalid_input"
    assert len(client.calls) == 2


def test_sender_merges_tail_sections_without_losing_order() -> None:
    """超过三个逻辑段时，第三个单元合并剩余内容并保留单个边界换行。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)
    content = "一\n[SPLIT]\n二\n[SPLIT]\n三\n[SPLIT]\n四\n[SPLIT]\n五"

    result = asyncio.run(sender.send("dm:800000001", content))

    assert result.success is True
    assert [body["message"][0]["data"]["text"] for _, body in client.calls] == [
        "一",
        "二",
        "三\n四\n五",
    ]


def test_sender_preflights_split_length_limit_before_any_action() -> None:
    """分段后的物理消息超过三条时，首个 Action 前整体拒绝。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client, max_text_length=2)
    content = "甲甲甲\n[SPLIT]\n乙乙乙\n[SPLIT]\n丙丙丙\n[SPLIT]\n丁丁丁"

    result = asyncio.run(sender.send("group:700000001", content))

    assert result.success is False
    assert result.error_kind == "invalid_input"
    assert client.calls == []


def test_sender_applies_existing_length_chunking_after_split_sections() -> None:
    """分段逻辑单元仍按既有长度边界分块，并在三条内顺序发送。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client, max_text_length=2)
    content = "甲乙丙\n[SPLIT]\n丁戊"

    result = asyncio.run(sender.send("dm:800000001", content))

    assert result.success is True
    assert [body["message"][0]["data"]["text"] for _, body in client.calls] == [
        "甲乙",
        "丙",
        "丁戊",
    ]


def test_sender_keeps_unmarked_long_text_unbounded_by_split_limit() -> None:
    """没有有效标记的普通长文本继续使用既有多条分块语义。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client, max_text_length=2)

    result = asyncio.run(sender.send("dm:800000001", "一二三四五六七"))

    assert result.success is True
    assert len(client.calls) == 4


def test_sender_keeps_escaped_literal_long_text_unbounded_by_split_limit() -> None:
    """只有字面量转义的长文本不应误用三条分段上限。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client, max_text_length=2)

    result = asyncio.run(sender.send("dm:800000001", "一[[SPLIT]]二三四"))

    assert result.success is True
    assert [body["message"][0]["data"]["text"] for _, body in client.calls] == [
        "一[",
        "SP",
        "LI",
        "T]",
        "二三",
        "四",
    ]


def test_sender_formats_cq_controls_inside_each_split_unit_in_order() -> None:
    """CQ-compatible 控制码在各分段内保持原顺序并走既有 formatter。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("dm:800000001", CQ_SPLIT_MESSAGE))

    assert result.success is True
    assert client.calls[0][1]["message"] == [
        {"type": "text", "data": {"text": "前段"}},
        {"type": "mention", "data": {"user_id": 10001}},
    ]
    assert client.calls[1][1]["message"] == [
        {"type": "text", "data": {"text": "后段"}},
        {"type": "reply", "data": {"message_seq": 10002}},
    ]


def test_sender_formats_cq_controls_around_inline_split_in_order() -> None:
    """行中分段不改变相邻 CQ-compatible 控制码顺序。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("dm:800000001", CQ_INLINE_SPLIT_MESSAGE))

    assert result.success is True
    assert client.calls[0][1]["message"] == [
        {"type": "text", "data": {"text": "前段"}},
        {"type": "mention", "data": {"user_id": 10001}},
    ]
    assert client.calls[1][1]["message"] == [
        {"type": "text", "data": {"text": "后段"}},
        {"type": "reply", "data": {"message_seq": 10002}},
    ]


def test_sender_preserves_partial_result_and_stops_after_first_split_failure() -> None:
    """中间 Action 失败时保留已成功 ID，不重试也不发送后续单元。"""

    client = SplitClient(
        fail_at=1,
        failure=ActionError("transport_unknown", "send_group_message", "fixture failure"),
    )
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send("group:700000001", "第一段\n[SPLIT]\n第二段\n[SPLIT]\n第三段"))

    assert result.success is False
    assert result.error_kind == "transport_unknown"
    assert result.message_id == "2001"
    assert result.continuation_message_ids == ()
    assert len(client.calls) == 2


@pytest.mark.parametrize("target", ["group:1", "temp:700000001", "dm:800000001"])
def test_split_preflight_rejects_invalid_target_or_all_blank_without_network(target: str) -> None:
    """非法目标和空分段均在任何 Milky Action 前返回。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)
    content = "[SPLIT]\n[SPLIT]" if target != "group:1" else "有效文本"

    result = asyncio.run(sender.send(target, content))

    assert result.success is False
    assert client.calls == []


def test_fake_hermes_delivers_all_text_before_attachments_in_extraction_order() -> None:
    """Hermes 只交给插件清理后的文本和附件列表，插件保持固定先文本后附件。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)
    events: list[str] = []

    async def fake_hermes_turn() -> None:
        text_result = await sender.send(
            "group:700000001", "文本一\n[SPLIT]\n文本二\n[SPLIT]\n文本三"
        )
        assert text_result.success is True
        events.extend(f"text:{body['message'][0]['data']['text']}" for _, body in client.calls)
        for kind, uri, file_name in ORDERED_ATTACHMENT_FIXTURE:
            if kind == "image":
                result = await sender.send_image("group:700000001", uri)
            elif kind == "audio":
                result = await sender.send_voice("group:700000001", uri)
            elif kind == "video":
                result = await sender.send_video("group:700000001", uri)
            else:
                result = await sender.send_document("group:700000001", uri, file_name=file_name)
            assert result.success is True
            events.append(f"attachment:{kind}")

    asyncio.run(fake_hermes_turn())

    assert events == [
        "text:文本一",
        "text:文本二",
        "text:文本三",
        "attachment:image",
        "attachment:audio",
        "attachment:video",
        "attachment:document",
    ]
    assert [name for name, _ in client.calls] == [
        "send_group_message",
        "send_group_message",
        "send_group_message",
        "send_group_message",
        "send_group_message",
        "send_group_message",
        "upload_group_file",
    ]


def test_fake_hermes_attachment_failure_keeps_text_and_does_not_infer_interleaving() -> None:
    """附件失败保留前序文本和首个附件错误，不从正文位置插入或重发文本。"""

    client = SplitClient(
        fail_at=3,
        failure=ActionError("rejected", "send_group_message", "fixture failure"),
    )
    sender = MilkyOutboundSender(client)

    async def fake_hermes_turn() -> tuple[object, object, object]:
        text_result = await sender.send(
            "group:700000001",
            "正文前\n[SPLIT]\n正文后",
        )
        image_result = await sender.send_image("group:700000001", ORDERED_ATTACHMENT_FIXTURE[0][1])
        voice_result = await sender.send_voice("group:700000001", ORDERED_ATTACHMENT_FIXTURE[1][1])
        return text_result, image_result, voice_result

    text_result, image_result, voice_result = asyncio.run(fake_hermes_turn())

    assert text_result.success is True
    assert image_result.success is True
    assert voice_result.success is False
    assert voice_result.error_kind == "rejected"
    assert [name for name, _ in client.calls] == [
        "send_group_message",
        "send_group_message",
        "send_group_message",
        "send_group_message",
    ]


def test_silent_is_owned_by_hermes_core_and_is_not_a_plugin_control_code() -> None:
    """`[SILENT]` 不被 split parser 解释，Hermes core 抑制时不触发 Milky Action。"""

    client = SplitClient()
    sender = MilkyOutboundSender(client)

    async def fake_hermes_delivery(content: str) -> object | None:
        if content == "[SILENT]":
            return None
        return await sender.send("dm:800000001", content)

    assert split_outbound_text("[SILENT]") is None
    assert asyncio.run(fake_hermes_delivery("[SILENT]")) is None
    assert client.calls == []
