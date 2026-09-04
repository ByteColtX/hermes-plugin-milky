"""验证入站 context 渲染、系统事件注入和 forward 查询边界。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from inbound.system_events import is_context_event, parse_context_event
from milky.parser import parse_event
from milky.resources import ResourceResolver
from session import SystemContextBuffer, render_message_record

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "protocol"
WILL_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "will_routing"
LEGACY_PLACEHOLDERS = (
    "[引用]",
    "[引用不可用]",
    "[图片]",
    "[图片不可用]",
    "[语音]",
    "[语音不可用]",
    "[视频]",
    "[视频不可用]",
    "[文件]",
    "[文件不可用]",
    "[转发]",
    "[转发不可用]",
    "[表情]",
    "[市场表情]",
    "[小程序]",
    "[XML]",
)


@dataclass(frozen=True, slots=True)
class ContextMessage:
    """提供 renderer 所需的最小普通消息字段。"""

    chat_key: str
    sender_name: str
    sender_id: int
    body: str
    message_id: str | None = None
    reply_message_id: str | None = None
    quote_target_is_self: bool = False


def load_fixture(relative_path: str) -> object:
    """读取脱敏协议 fixture。"""

    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def load_target_fixture() -> dict[str, object]:
    """读取 nudge 目标判断的脱敏 fixture。"""

    return json.loads((WILL_FIXTURE_ROOT / "target_signals.json").read_text(encoding="utf-8"))


def test_message_context_is_single_line_and_escapes_header_boundaries() -> None:
    """普通消息的 header 和正文必须在一行内保持可解析边界。"""

    fixture = json.loads(
        (Path(__file__).parent / "fixtures/inbound_context/ordinary_messages.json").read_text(
            encoding="utf-8"
        )
    )
    records = fixture["records"]

    first = ContextMessage("group:700000001", **records[0])
    second = ContextMessage("group:700000001", **records[1])

    assert render_message_record(first) == fixture["expected"]["first"]
    assert render_message_record(second) == fixture["expected"]["second"]
    assert "\n" not in render_message_record(first)
    assert "\r" not in render_message_record(first)


def test_context_renderer_labels_only_confirmed_self_reply_target() -> None:
    """Agent-facing header 只将已确认的实际引用目标显示为自引用。"""

    self_reply = ContextMessage(
        "group:700000001",
        "合成机器人",
        800000002,
        "回复正文",
        message_id="7001",
        reply_message_id="6999",
        quote_target_is_self=True,
    )
    other_reply = ContextMessage(
        "group:700000001",
        "合成用户",
        800000003,
        "回复正文",
        message_id="7002",
        reply_message_id="6998",
    )
    unknown_target = ContextMessage(
        "group:700000001",
        "合成用户",
        800000003,
        "回复正文",
        message_id="7003",
        reply_message_id="6997",
    )
    no_target = ContextMessage(
        "group:700000001",
        "合成用户",
        800000003,
        "无引用",
        message_id="7004",
        quote_target_is_self=True,
    )

    assert render_message_record(self_reply) == (
        "<合成机器人 uid 800000002 msg_id 7001 reply_to your_previous_msg> 回复正文"
    )
    assert render_message_record(other_reply) == (
        "<合成用户 uid 800000003 msg_id 7002 reply_to 6998> 回复正文"
    )
    assert render_message_record(unknown_target) == (
        "<合成用户 uid 800000003 msg_id 7003 reply_to 6997> 回复正文"
    )
    assert render_message_record(no_target) == "<合成用户 uid 800000003 msg_id 7004> 无引用"


def test_segment_placeholders_keep_order_and_variable_light_app_meta() -> None:
    """结构化 placeholder 和 light app meta 投影必须按原顺序保留。"""

    from inbound.normalizer import normalize_event

    result = normalize_event(load_fixture("events/message_receive.group.all_segments.json"))
    assert result.value is not None
    assert result.value.body == (
        "中性文本@合成机器人@全体成员[face:fixture-face]"
        "[img:file_name=[合成图片]][record:NOT SUPPORTED][video:NOT SUPPORTED]"
        "[file:file_id=fixture-file-id,file_name=fixture.txt,file_hash=NOT SUPPORTED]"
        "[forward:forward_id=fixture-forward-id][market_face:summary=[合成市场表情]]"
        '[light_app:{"meta":{"contact":{"type":"qq","id":800000004,'
        '"labels":["测试",null]},"nested":{"enabled":true}}}]'
        "[xml:NOT SUPPORTED]### 中性内容"
    )
    assert all(marker not in result.value.body for marker in LEGACY_PLACEHOLDERS)

    missing_meta = load_fixture("events/message_receive.friend.json")
    missing_meta["data"]["segments"] = [
        {"type": "light_app", "data": {"json_payload": '{"app":"contact"}'}},
        {"type": "light_app", "data": {"json_payload": "not-json"}},
    ]
    missing_result = normalize_event(missing_meta)
    assert missing_result.value is not None
    assert missing_result.value.body == ("[light_app:NOT SUPPORTED][light_app:NOT SUPPORTED]")
    assert "malformed_light_app" in missing_result.value.diagnostics


def test_file_placeholder_preserves_id_and_name_from_segment_data() -> None:
    """file placeholder 应原样保留 segment 提供的 ID 和文件名。"""

    from inbound.normalizer import normalize_event

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"] = [
        {
            "type": "file",
            "data": {
                "file_id": "/fixture-file-id",
                "file_name": "logs.txt",
                "file_size": 8,
            },
        }
    ]

    result = normalize_event(payload)

    assert result.value is not None
    assert result.value.body == (
        "[file:file_id=/fixture-file-id,file_name=logs.txt,file_hash=NOT SUPPORTED]"
    )


def test_system_events_render_only_confirmed_fields() -> None:
    """nudge 和成员变更只使用协议确认的字段。"""

    group_nudge = parse_context_event(parse_event(load_fixture("events/system.group_nudge.json")))
    friend_nudge = parse_context_event(parse_event(load_fixture("events/system.friend_nudge.json")))
    increase = parse_context_event(
        parse_event(load_fixture("events/system.group_member_increase.json"))
    )
    minimal = parse_context_event(
        parse_event(load_fixture("events/system.group_member_increase.optional_missing.json"))
    )
    decrease = parse_context_event(
        parse_event(load_fixture("events/system.group_member_decrease.json"))
    )

    assert group_nudge.value is not None
    assert group_nudge.value.chat_key == "group:700000001"
    assert group_nudge.value.body == "uid 800000002 戳了 uid 900000001"
    assert friend_nudge.value is not None
    assert friend_nudge.value.chat_key == "dm:800000001"
    assert friend_nudge.value.body == "uid 800000001 戳了一下"
    assert increase.value is not None
    assert increase.value.body == (
        "uid 800000004 加入了群聊 Details: "
        '{"group_id": 700000001, "user_id": 800000004, "operator_id": 900000001, "invitor_id": 800000002}'
    )
    assert minimal.value is not None
    assert minimal.value.body == (
        'uid 800000005 加入了群聊 Details: {"group_id": 700000001, "user_id": 800000005}'
    )
    assert decrease.value is not None
    assert decrease.value.body == (
        'uid 800000004 退出了群聊 Details: {"group_id": 700000001, "user_id": 800000004, "operator_id": 900000001}'
    )

    malformed = parse_context_event(
        parse_event(load_fixture("events/system.group_nudge.malformed.json"))
    )
    assert malformed.classification == "malformed"
    assert malformed.value is None


def test_message_recall_maps_scene_operator_and_filters_extensions() -> None:
    """撤回事件只使用已确认字段，并按场景生成隔离 chat key。"""

    cases = (
        (
            "events/system.message_recall.group.self.json",
            "group:700000001",
            "uid 800000002 撤回了消息 msg_seq 1001",
        ),
        (
            "events/system.message_recall.json",
            "group:700000001",
            "管理员 uid 900000001 撤回了 uid 800000002 的消息 msg_seq 1000",
        ),
        (
            "events/system.message_recall.friend.json",
            "dm:800000001",
            "uid 800000001 撤回了消息 msg_seq 2001",
        ),
        (
            "events/system.message_recall.friend.operator.json",
            "dm:800000001",
            "uid 900000001 撤回了 uid 800000001 的消息 msg_seq 2002",
        ),
    )

    assert is_context_event("message_recall") is True
    for path, expected_chat_key, expected_body in cases:
        event = load_fixture(path)
        result = parse_context_event(parse_event(event))

        assert result.classification == "accepted"
        assert result.value is not None
        assert result.value.chat_key == expected_chat_key
        assert result.value.body == expected_body
        assert "display_suffix" not in result.value.body
        assert "display_action" not in result.value.body


def test_message_recall_invalid_scene_and_ids_fail_closed() -> None:
    """撤回事件的非法场景和 ID 不得创建上下文记录。"""

    malformed_paths = (
        "events/system.message_recall.malformed.missing_sender.json",
        "events/system.message_recall.invalid_id.json",
    )
    for path in malformed_paths:
        result = parse_context_event(parse_event(load_fixture(path)))
        assert result.classification == "malformed"
        assert result.value is None

    for path in (
        "events/system.message_recall.temp.json",
        "events/system.message_recall.unknown_scene.json",
    ):
        result = parse_context_event(parse_event(load_fixture(path)))
        assert result.classification == "unsupported"
        assert result.value is None


def test_nudge_target_fixture_only_marks_protocol_confirmed_self_pokes() -> None:
    """group 用 receiver_id，friend 用明确方向字段，未知方向安全降级。"""

    fixture = load_target_fixture()
    for case in fixture["nudge_cases"]:  # type: ignore[union-attr]
        assert isinstance(case, dict)
        result = parse_context_event(parse_event(case["event"]))
        expected_classification = case.get("expected_classification", "accepted")
        assert result.classification == expected_classification
        if result.value is None:
            assert case["expected_self_poke"] is False
            continue
        assert result.value.is_self_poke is case["expected_self_poke"]
        if case["name"].startswith("group_"):
            assert result.value.sender_id == case["event"]["data"]["sender_id"]
            assert result.value.receiver_id == case["event"]["data"]["receiver_id"]

    group = parse_context_event(parse_event(load_fixture("events/system.group_nudge.json")))
    friend = parse_context_event(parse_event(load_fixture("events/system.friend_nudge.json")))
    assert group.value is not None and group.value.is_self_poke is True
    assert friend.value is not None and friend.value.is_self_poke is True


def test_system_context_buffer_isolated_bounded_and_drained_once() -> None:
    """系统上下文按 chat 隔离，溢出淘汰最早事件，drain 后不重复注入。"""

    buffer = SystemContextBuffer(max_size=2)
    buffer.append("group:700000001", "group_nudge", "第一条", ingress_sequence=1)
    buffer.append("group:700000001", "group_nudge", "第二条", ingress_sequence=2)
    result = buffer.append("group:700000001", "group_nudge", "第三条", ingress_sequence=3)
    buffer.append("dm:800000001", "friend_nudge", "私聊", ingress_sequence=4)

    assert result.reason == "system_context_overflow"
    assert [event.body for event in buffer.snapshot("group:700000001")] == ["第二条", "第三条"]
    assert [event.body for event in buffer.drain("group:700000001")] == ["第二条", "第三条"]
    assert buffer.drain("group:700000001") == ()
    assert [event.body for event in buffer.snapshot("dm:800000001")] == ["私聊"]
    assert buffer.diagnostics[-1].reason == "system_context_overflow"


def test_system_context_buffer_preserves_self_poke_feature_and_identities() -> None:
    """context buffer 重建事件时不得丢失 nudge 的目标特征。"""

    from session import ContextOnlyEvent

    buffer = SystemContextBuffer(max_size=1)
    buffer.append(
        ContextOnlyEvent(
            chat_key="group:700000001",
            event_type="group_nudge",
            body="uid 800000002 戳了 uid 900000001",
            sender_id=800000002,
            receiver_id=900000001,
            is_self_poke=True,
        ),
        ingress_sequence=1,
    )

    stored = buffer.snapshot("group:700000001")[0]
    assert stored.sender_id == 800000002
    assert stored.receiver_id == 900000001
    assert stored.is_self_poke is True


def test_forward_resolution_does_not_query_forwarded_messages() -> None:
    """普通 trigger resolver 只保留 forward ID，不自动展开远端内容。"""

    from inbound.canonical import canonicalize_event
    from tests.test_resources import FakeHermesMedia, make_client

    canonical = canonicalize_event(
        load_fixture("events/message_receive.group.all_segments.json")
    ).value
    assert canonical is not None
    client = make_client()
    resolved = asyncio.run(ResourceResolver(client, FakeHermesMedia()).resolve(canonical))

    assert not any(name == "get_forwarded_messages" for name, _ in client.calls)
    assert resolved.forwards[0].forward_id == "fixture-forward-id"
    assert resolved.forwards[0].messages == ()
    assert "[forward:forward_id=fixture-forward-id]" in resolved.body


def test_pipeline_merges_context_events_by_ingress_and_does_not_create_turn() -> None:
    """系统事件只进入同 chat 下一次 trigger 的上下文。"""

    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, make_pipeline
    from will import RoutingConfig

    async def scenario():
        hermes = FakeHermes()
        pipeline = make_pipeline(
            hermes,
            FakeResolver(),
            routing=RoutingConfig(direct="trigger", mention="trigger", all_message="wait"),
        )
        history = load_fixture("events/message_receive.group.all_segments.json")
        history["data"]["message_seq"] = 5001
        history["data"]["segments"] = [{"type": "text", "data": {"text": "历史消息"}}]
        trigger = load_fixture("events/message_receive.group.all_segments.json")
        trigger["data"]["message_seq"] = 5002
        trigger["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "触发消息"}},
        ]
        assert (await pipeline.handle_event(history)).classification == "wait"
        assert (
            await pipeline.handle_event(load_fixture("events/system.group_nudge.json"))
        ).classification == "observe_only"
        assert (
            await pipeline.handle_event(load_fixture("events/system.group_member_increase.json"))
        ).classification == "observe_only"
        assert (await pipeline.handle_event(trigger)).classification == "trigger"
        await pipeline.wait_idle()
        return pipeline, hermes

    pipeline, hermes = asyncio.run(scenario())
    assert len(hermes.events) == 1
    event = hermes.events[0]
    assert event.channel_context == (
        "<合成名片 uid 800000002 msg_id 5001> 历史消息\n"
        "<event group_nudge> uid 800000002 戳了 uid 900000001\n"
        "<event group_member_increase> uid 800000004 加入了群聊 Details: "
        '{"group_id": 700000001, "user_id": 800000004, "operator_id": 900000001, "invitor_id": 800000002}'
    )
    assert "触发消息" in event.text
    assert "触发消息" not in event.channel_context
    assert pipeline.reply_costs == 1


def test_pipeline_merges_recall_context_once_and_keeps_scene_namespaces_isolated() -> None:
    """撤回事件应和普通历史按 ingress 合并，并只注入对应 chat 一次。"""

    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, make_pipeline
    from will import RoutingConfig

    async def scenario():
        hermes = FakeHermes()
        pipeline = make_pipeline(
            hermes,
            FakeResolver(),
            routing=RoutingConfig(direct="trigger", mention="trigger", all_message="wait"),
        )
        history = load_fixture("events/message_receive.group.all_segments.json")
        history["data"]["message_seq"] = 5101
        history["data"]["segments"] = [{"type": "text", "data": {"text": "历史消息"}}]
        group_trigger = load_fixture("events/message_receive.group.all_segments.json")
        group_trigger["data"]["message_seq"] = 5102
        group_trigger["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "群聊触发"}},
        ]
        group_second_trigger = load_fixture("events/message_receive.group.all_segments.json")
        group_second_trigger["data"]["message_seq"] = 5103
        group_second_trigger["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "群聊第二次触发"}},
        ]
        friend_trigger = load_fixture("events/message_receive.friend.json")
        friend_trigger["data"]["message_seq"] = 5104
        friend_trigger["data"]["segments"] = [{"type": "text", "data": {"text": "好友触发"}}]

        assert (await pipeline.handle_event(history)).classification == "wait"
        assert (
            await pipeline.handle_event(
                load_fixture("events/system.message_recall.group.self.json")
            )
        ).classification == "observe_only"
        assert (
            await pipeline.handle_event(load_fixture("events/system.group_nudge.json"))
        ).classification == "observe_only"
        assert (
            await pipeline.handle_event(load_fixture("events/system.message_recall.friend.json"))
        ).classification == "observe_only"
        assert (await pipeline.handle_event(group_trigger)).classification == "trigger"
        assert (await pipeline.handle_event(group_second_trigger)).classification == "trigger"
        assert (await pipeline.handle_event(friend_trigger)).classification == "trigger"
        await pipeline.wait_idle()
        return hermes

    hermes = asyncio.run(scenario())

    group_events = [event for event in hermes.events if event.source.chat_id == "group:700000001"]
    friend_events = [event for event in hermes.events if event.source.chat_id == "dm:800000001"]
    assert len(group_events) == 2
    assert len(friend_events) == 1
    assert group_events[0].channel_context == (
        "<合成名片 uid 800000002 msg_id 5101> 历史消息\n"
        "<event message_recall> uid 800000002 撤回了消息 msg_seq 1001\n"
        "<event group_nudge> uid 800000002 戳了 uid 900000001"
    )
    assert group_events[1].channel_context is None
    assert friend_events[0].channel_context == (
        "<event message_recall> uid 800000001 撤回了消息 msg_seq 2001"
    )


def test_pipeline_recall_context_obeys_bounded_fifo_and_drains_once() -> None:
    """撤回事件复用独立有界 FIFO，溢出保留最新记录且不重复注入。"""

    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, make_pipeline
    from will import RoutingConfig

    async def scenario():
        hermes = FakeHermes()
        pipeline = make_pipeline(
            hermes,
            FakeResolver(),
            routing=RoutingConfig(direct="trigger", mention="trigger", all_message="wait"),
            buffer_size=2,
        )
        for message_seq in (3001, 3002, 3003):
            recall = load_fixture("events/system.message_recall.group.self.json")
            recall["data"]["message_seq"] = message_seq
            assert (await pipeline.handle_event(recall)).classification == "observe_only"
        trigger = load_fixture("events/message_receive.group.all_segments.json")
        trigger["data"]["message_seq"] = 5201
        trigger["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "触发"}},
        ]
        assert (await pipeline.handle_event(trigger)).classification == "trigger"
        second = load_fixture("events/message_receive.group.all_segments.json")
        second["data"]["message_seq"] = 5202
        second["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "再次触发"}},
        ]
        assert (await pipeline.handle_event(second)).classification == "trigger"
        await pipeline.wait_idle()
        return pipeline, hermes

    pipeline, hermes = asyncio.run(scenario())

    assert len(hermes.events) == 2
    assert hermes.events[0].channel_context == (
        "<event message_recall> uid 800000002 撤回了消息 msg_seq 3002\n"
        "<event message_recall> uid 800000002 撤回了消息 msg_seq 3003"
    )
    assert hermes.events[1].channel_context is None
    assert pipeline._system_context.diagnostics[-1].reason == "system_context_overflow"


def test_complete_reply_uses_reply_header_without_success_placeholder() -> None:
    """完整 reply 只在 header 和 Hermes metadata 表达，不重复污染正文。"""

    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, make_pipeline

    async def scenario():
        hermes = FakeHermes()
        pipeline = make_pipeline(hermes, FakeResolver())
        payload = load_fixture("events/message_receive.friend.json")
        payload["data"]["message_seq"] = 7991
        payload["data"]["segments"] = [
            {
                "type": "reply",
                "data": {
                    "message_seq": 7989,
                    "sender_id": 800000001,
                    "sender_name": "合成好友",
                    "time": 1700000009,
                    "segments": [{"type": "text", "data": {"text": "原始消息"}}],
                },
            },
            {"type": "text", "data": {"text": "引用消息"}},
        ]
        assert (await pipeline.handle_event(payload)).classification == "trigger"
        await pipeline.wait_idle()
        return hermes.events[0]

    event = asyncio.run(scenario())

    assert event.text == "<合成好友 uid 800000001 msg_id 7991 reply_to 7989> 引用消息"
    assert event.reply_to_message_id == "7989"
    assert "[引用]" not in event.text


def test_current_bot_reply_uses_label_and_preserves_hermes_reply_metadata() -> None:
    """当前消息显示自引用文案时仍保留 Hermes 的真实 reply 元数据。"""

    from tests.test_hermes_pipeline import FakeHermes, make_pipeline
    from tests.test_resources import FakeHermesMedia, make_client

    async def scenario():
        hermes = FakeHermes()
        resolver = ResourceResolver(make_client(), FakeHermesMedia())
        pipeline = make_pipeline(hermes, resolver)
        payload = load_fixture("events/message_receive.friend.json")
        payload["data"]["message_seq"] = 7992
        payload["data"]["segments"] = [
            {
                "type": "reply",
                "data": {
                    "message_seq": 7989,
                    "sender_id": 900000001,
                    "sender_name": "合成机器人",
                    "time": 1700000009,
                    "segments": [{"type": "text", "data": {"text": "机器人原文"}}],
                },
            },
            {"type": "text", "data": {"text": "引用机器人"}},
        ]
        assert (await pipeline.handle_event(payload)).classification == "trigger"
        await pipeline.wait_idle()
        return hermes.events[0]

    event = asyncio.run(scenario())

    assert (
        event.text == "<合成好友 uid 800000001 msg_id 7992 reply_to your_previous_msg> 引用机器人"
    )
    assert event.message_id == "7992"
    assert event.reply_to_message_id == "7989"
    assert event.reply_to_author_id == "900000001"
    assert event.reply_to_author_name == "合成机器人"
    assert event.reply_to_is_own_message is True


def test_history_bot_reply_uses_same_label_and_excludes_current_message() -> None:
    """wait 历史引用 Bot 时使用同一文案，current 仍只进入本次正文。"""

    from tests.test_hermes_pipeline import FakeHermes, make_pipeline
    from tests.test_resources import FakeHermesMedia, make_client
    from will import RoutingConfig

    async def scenario():
        hermes = FakeHermes()
        resolver = ResourceResolver(make_client(), FakeHermesMedia())
        pipeline = make_pipeline(
            hermes,
            resolver,
            routing=RoutingConfig(direct="trigger", mention="trigger", all_message="wait"),
        )
        history = load_fixture("events/message_receive.group.all_segments.json")
        history["data"]["message_seq"] = 6101
        history["data"]["segments"] = [
            {
                "type": "reply",
                "data": {
                    "message_seq": 6099,
                    "sender_id": 900000001,
                    "sender_name": "合成机器人",
                    "time": 1700000009,
                    "segments": [{"type": "text", "data": {"text": "机器人原文"}}],
                },
            },
            {"type": "text", "data": {"text": "历史引用"}},
        ]
        current = load_fixture("events/message_receive.group.all_segments.json")
        current["data"]["message_seq"] = 6102
        current["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "触发消息"}},
        ]
        assert (await pipeline.handle_event(history)).classification == "wait"
        assert (await pipeline.handle_event(current)).classification == "trigger"
        await pipeline.wait_idle()
        return hermes.events[0]

    event = asyncio.run(scenario())

    assert event.channel_context == (
        "<合成名片 uid 800000002 msg_id 6101 reply_to your_previous_msg> 历史引用"
    )
    assert event.text == "<合成名片 uid 800000002 msg_id 6102> @合成机器人触发消息"
    assert "触发消息" not in event.channel_context
