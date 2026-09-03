"""验证 T08 segment normalizer、extractor 和 WillInput。"""

from __future__ import annotations

import builtins
import json
import random
import socket
import time
from pathlib import Path

import pytest

from inbound.normalizer import normalize_event
from milky.models import UnknownSegment

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "protocol"
WILL_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "will_routing"


def load_fixture(relative_path: str) -> object:
    """读取脱敏协议 fixture。"""

    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def load_will_fixture() -> dict[str, object]:
    """读取消息目标判断的脱敏 fixture。"""

    return json.loads((WILL_FIXTURE_ROOT / "target_signals.json").read_text(encoding="utf-8"))


def test_normalizer_preserves_all_known_segments_and_strategy_features() -> None:
    """规范化应保留 14 类 segment 顺序并一次性生成策略特征。"""

    result = normalize_event(load_fixture("events/message_receive.group.all_segments.json"))

    assert result.classification == "accepted"
    assert result.value is not None
    normalized = result.value
    assert [segment.type for segment in normalized.segments] == [
        "text",
        "mention",
        "mention_all",
        "face",
        "reply",
        "image",
        "record",
        "video",
        "file",
        "forward",
        "market_face",
        "light_app",
        "xml",
        "markdown",
    ]
    assert normalized.body == (
        "中性文本@合成机器人@全体成员[face:fixture-face]"
        "[img:file_name=[合成图片]][record:NOT SUPPORTED][video:NOT SUPPORTED]"
        "[file:file_id=fixture-file-id,file_name=fixture.txt,file_hash=NOT SUPPORTED]"
        "[forward:forward_id=fixture-forward-id][market_face:summary=[合成市场表情]]"
        '[light_app:{"meta":{"contact":{"type":"qq","id":800000004,'
        '"labels":["测试",null]},"nested":{"enabled":true}}}]'
        "[xml:NOT SUPPORTED]### 中性内容"
    )
    assert normalized.strategy_text == "中性文本@合成机器人@全体成员### 中性内容"
    assert normalized.mention_kinds == ("self", "all")
    assert normalized.mention_kind == "self"
    assert normalized.has_reply is True
    assert normalized.reply_message_seq == 1000
    assert normalized.has_image is True
    assert [reference.kind for reference in normalized.media_resource_references] == [
        "image",
        "record",
        "video",
    ]
    assert [reference.file_id for reference in normalized.file_attachment_references] == [
        "fixture-file-id"
    ]
    assert [reference.forward_id for reference in normalized.forward_references] == [
        "fixture-forward-id"
    ]
    assert normalized.reply_references[0].message_seq == 1000
    assert normalized.will_input.text == normalized.strategy_text
    assert normalized.will_input.chat_key == "group:700000001"
    assert normalized.will_input.channel == "group:700000001"


def test_normalizer_keeps_friend_scene_and_does_not_use_group_fields() -> None:
    """friend 消息应生成 dm chat key 和独立的 direct WillInput。"""

    result = normalize_event(load_fixture("events/message_receive.friend.json"))

    assert result.value is not None
    assert result.value.scene == "friend"
    assert result.value.chat_key == "dm:800000001"
    assert result.value.will_input.is_direct is True
    assert result.value.will_input.scene == "friend"


def test_temp_message_is_ignored_before_normalization() -> None:
    """temp 消息不得建立规范化结果或 chat key。"""

    result = normalize_event(load_fixture("events/message_receive.temp.json"))

    assert result.classification == "ignored_temp"
    assert result.value is None
    assert result.reason == "temporary message scene"


def test_unknown_segment_is_metadata_only_and_does_not_enter_strategy_text() -> None:
    """未知 segment 只能进入安全诊断，不能变成正文或关键词。"""

    result = normalize_event(load_fixture("events/message_receive.group.unknown_extension.json"))

    assert result.value is not None
    normalized = result.value
    assert isinstance(normalized.segments[1], UnknownSegment)
    assert normalized.body == "保留文本"
    assert normalized.strategy_text == "保留文本"
    assert normalized.unknown_segments[0]["type"] == "future_segment_extension"
    assert "unknown_segment" in normalized.diagnostics


def test_unknown_only_message_is_dropped_with_explicit_reason() -> None:
    """只有未知内容的消息必须安全丢弃并说明原因。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [{"type": "future_extension", "data": {"opaque": "诊断内容"}}]

    result = normalize_event(payload)

    assert result.classification == "dropped"
    assert result.value is None
    assert result.reason == "no_supported_content"


def test_structured_only_message_remains_processable() -> None:
    """没有普通文本的合法结构化消息也必须保留。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {"type": "image", "data": {"resource_id": "fixture-image-resource"}}
    ]

    result = normalize_event(payload)

    assert result.classification == "accepted"
    assert result.value is not None
    assert result.value.body == "[img:file_name=fixture-image-resource]"
    assert result.value.strategy_text == ""
    assert result.value.has_image is True


def test_reply_missing_required_fields_is_malformed_without_fabricating_quote() -> None:
    """reply 缺字段时必须保留诊断且不能伪造引用目标。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {"type": "reply", "data": {"message_seq": 1000}},
    ]

    result = normalize_event(payload)

    assert result.classification == "malformed"
    assert result.value is not None
    assert result.value.has_reply is True
    assert result.value.reply_message_seq == 1000
    assert result.value.is_self_quote is False
    assert result.value.body == "[reply:NOT SUPPORTED]"
    assert "malformed_reply" in result.value.diagnostics


def test_inline_reply_does_not_need_remote_resolution() -> None:
    """完整 inline reply 应直接保留目标，不产生补全请求。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"].append(
        {
            "type": "reply",
            "data": {
                "message_seq": 1000,
                "sender_id": 800000002,
                "sender_name": "合成回复者",
                "time": 1700000005,
                "segments": [{"type": "text", "data": {"text": "原文"}}],
            },
        }
    )

    result = normalize_event(payload)

    assert result.classification == "accepted"
    assert result.value is not None
    assert result.value.reply_message_seq == 1000
    assert result.value.body == "朋友消息"
    assert "[引用]" not in result.value.body


def test_target_fixture_keeps_self_quote_separate_from_reply_and_sender() -> None:
    """reply 作者才决定 self quote，当前消息作者和嵌套 mention 不参与判断。"""

    fixture = load_will_fixture()
    for case in fixture["message_cases"]:  # type: ignore[union-attr]
        assert isinstance(case, dict)
        result = normalize_event(case["event"])
        expected_classification = case.get("expected_classification", "accepted")
        assert result.classification == expected_classification
        assert result.value is not None
        normalized = result.value
        assert list(normalized.mention_kinds) == case.get("expected_mention_kinds", ["none"])
        assert normalized.is_self_quote is case["expected_self_quote"]
        assert normalized.will_input.is_self_quote is case["expected_self_quote"]
        assert normalized.will_input.has_reply == ("expected_reply_message_seq" in case)
        if "expected_reply_message_seq" in case:
            assert normalized.reply_message_seq == case["expected_reply_message_seq"]
            assert normalized.will_input.reply_message_seq == case["expected_reply_message_seq"]


def test_target_fixture_contains_only_synthetic_protocol_fields() -> None:
    """目标 fixture 不得携带凭证、路径、URL 或敏感正文。"""

    contents = (WILL_FIXTURE_ROOT / "target_signals.json").read_text(encoding="utf-8")
    forbidden = ("MILKY_ACCESS_TOKEN", "Authorization", "Bearer ", "http://", "https://", "/Users/")
    assert not any(value in contents for value in forbidden)


def test_media_and_forward_only_store_references() -> None:
    """媒体和 forward 只生成引用，不展开或下载内容。"""

    result = normalize_event(load_fixture("events/message_receive.group.all_segments.json"))

    assert result.value is not None
    image, record, video = result.value.media_resource_references
    assert image.resource_id == "fixture-image-resource"
    assert record.resource_id == "fixture-record-resource"
    assert video.resource_id == "fixture-video-resource"
    file = result.value.file_attachment_references[0]
    assert file.file_id == "fixture-file-id"
    assert file.file_name == "fixture.txt"
    assert result.value.forward_references[0].forward_id == "fixture-forward-id"


@pytest.mark.parametrize("case_index", range(4))
def test_file_placeholder_and_reference_share_normalized_hash(case_index: int) -> None:
    """文件正文和独立引用应共同使用 typed file_hash，不反解析正文。"""

    placeholder_fixture = json.loads(
        (Path(__file__).parent / "fixtures/inbound_context/file_placeholders.json").read_text(
            encoding="utf-8"
        )
    )
    case = placeholder_fixture["cases"][case_index]
    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [{"type": "file", "data": case["segment"]}]

    result = normalize_event(payload)

    assert result.value is not None
    assert result.value.body == case["expected"]
    reference = result.value.file_attachment_references[0]
    assert reference.file_hash == case["segment"].get("file_hash")
    assert reference.file_name == case["segment"]["file_name"]


def test_incomplete_media_gets_explanatory_placeholder() -> None:
    """缺少可用引用的媒体不能伪装成普通文本。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {"type": "image", "data": {}},
        {"type": "file", "data": {}},
        {"type": "forward", "data": {}},
    ]

    result = normalize_event(payload)

    assert result.value is not None
    assert result.value.body == (
        "[img:file_name=NOT SUPPORTED]"
        "[file:file_id=NOT SUPPORTED,file_name=NOT SUPPORTED,file_hash=NOT SUPPORTED]"
        "[forward:forward_id=NOT SUPPORTED]"
    )
    assert "incomplete_media_reference" in result.value.diagnostics


def test_v13_never_infers_mention_here_from_name_or_text() -> None:
    """v1.3 普通 mention/name/text 不得推断 mention_here。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["message_scene"] = "group"
    payload["data"]["peer_id"] = 700000001
    payload["data"]["sender_id"] = 800000002
    payload["data"]["group"] = {"group_id": 700000001}
    payload["data"]["group_member"] = {
        "group_id": 700000001,
        "user_id": 800000002,
        "nickname": "合成成员",
    }
    payload["data"]["segments"] = [
        {"type": "text", "data": {"text": "@合成机器人 here"}},
        {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
    ]

    result = normalize_event(payload)

    assert result.value is not None
    assert result.value.mention_kinds == ("self",)
    assert result.value.will_input.mention_here is False


def test_normalizer_has_no_network_filesystem_clock_or_random_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """规范化只能消费 DTO，不得访问网络、文件、时钟或随机源。"""

    def fail(*_args, **_kwargs):
        raise AssertionError("normalizer performed an external side effect")

    payload = load_fixture("events/message_receive.group.all_segments.json")
    monkeypatch.setattr(builtins, "open", fail)
    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(time, "time", fail)
    monkeypatch.setattr(time, "monotonic", fail)
    monkeypatch.setattr(random, "random", fail)

    result = normalize_event(payload)

    assert result.classification == "accepted"
