"""验证 Milky 入站消息到 Hermes MessageEvent 的交接边界。"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from gates import GateRegistry
from inbound.pipeline import InboundPipeline, PipelineResult
from milky.resources import (
    HermesAttachmentMaterialization,
    ResolvedMessage,
    ResolvedReply,
    ResolvedTriggerBatch,
    ResourceResolver,
)
from session import ChatAdmissionCoordinator, TtlDeduplicator, WaitBuffer
from will import (
    RoutingConfig,
    RoutingWillEngine,
    WillingnessConfig,
    WillingnessWillEngine,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "protocol"


def load_fixture(relative_path: str) -> object:
    """读取脱敏协议 fixture。"""

    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


class FakeMessageType:
    """提供 mapper 所需的最小 Hermes MessageType。"""

    TEXT = "text"
    PHOTO = "photo"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


@dataclass
class FakeMessageEvent:
    """保存 mapper 交给 fake Hermes 的完整事件。"""

    text: str
    message_type: str
    user_id: str | None = None
    user_name: str | None = None
    source: object | None = None
    raw_message: object | None = None
    message_id: str | None = None
    media_urls: list[str] = field(default_factory=list)
    media_types: list[str] = field(default_factory=list)
    reply_to_message_id: str | None = None
    reply_to_text: str | None = None
    reply_to_author_id: str | None = None
    reply_to_author_name: str | None = None
    reply_to_is_own_message: bool = False
    channel_context: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    timestamp: object | None = None
    allow_gateway_control: bool = True


@dataclass(frozen=True)
class FakeSource:
    """提供 Hermes source 的最小字段。"""

    platform: str
    chat_id: str
    chat_type: str
    user_id: str
    user_name: str
    message_id: str | None


class FakeHermes:
    """记录 source 和 MessageEvent 提交，不执行真实 Agent。"""

    def __init__(self) -> None:
        self.events: list[FakeMessageEvent] = []
        self.agent_finished = asyncio.Event()
        self.handle_returned = asyncio.Event()

    def build_source(self, **values: object) -> FakeSource:
        """构造带 Milky 平台和 namespaced chat key 的 source。"""

        return FakeSource(
            platform="milky",
            chat_id=values["chat_id"],  # type: ignore[arg-type]
            chat_type=values["chat_type"],  # type: ignore[arg-type]
            user_id=values["user_id"],  # type: ignore[arg-type]
            user_name=values["user_name"],  # type: ignore[arg-type]
            message_id=values["message_id"],  # type: ignore[arg-type]
        )

    async def handle_message(self, event: FakeMessageEvent) -> None:
        """模拟快速提交后由 Hermes 自己继续执行 Agent。"""

        self.events.append(event)
        self.handle_returned.set()
        asyncio.create_task(self.agent_finished.wait())


class FakeResolver:
    """记录 detached resolver 调用并模拟异步 materialization。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.started = asyncio.Event()
        self.completed = asyncio.Event()

    async def resolve_batch(self, batch: object) -> ResolvedTriggerBatch:
        """等待一个调度机会后返回安全的 resolved batch。"""

        self.started.set()
        await asyncio.sleep(0)
        history = tuple(
            ResolvedMessage(body=item.body, hermes_attachment_materializations=())
            for item in batch.history
        )
        materialization = HermesAttachmentMaterialization(
            path="/hermes/cache/current.png",
            mime_type="image/png",
            kind="image",
            display_name="fixture.png",
            reference_kind="image",
            reference_id="fixture-resource",
        )
        current = ResolvedMessage(
            body=batch.current.body,
            hermes_attachment_materializations=(materialization,),
        )
        self.calls.append((batch.chat_key, batch.current.message_id or "none"))
        self.completed.set()
        return ResolvedTriggerBatch(batch.chat_key, history, current)


class FailingResolver(FakeResolver):
    """模拟资源解析失败，验证 trigger 成本不会回滚。"""

    async def resolve_batch(self, _batch: object) -> ResolvedTriggerBatch:
        """在 detached 交接开始后抛出安全的本地异常。"""

        self.started.set()
        raise RuntimeError("fake resource resolution failed")


class ContextImageResolver(FakeResolver):
    """返回含历史 context 图片和当前附件的脱敏 resolved batch。"""

    async def resolve_batch(self, batch: object) -> ResolvedTriggerBatch:
        """按历史/当前顺序返回合成的 materialization。"""

        history_first = HermesAttachmentMaterialization(
            path="/hermes/cache/history-first.png",
            mime_type="image/png",
            kind="image",
            display_name="history-first.png",
            reference_kind="image",
            reference_id="history-first",
        )
        shared = HermesAttachmentMaterialization(
            path="/hermes/cache/shared.png",
            mime_type="image/jpeg",
            kind="image",
            display_name="shared.jpg",
            reference_kind="image",
            reference_id="shared",
        )
        current_image = HermesAttachmentMaterialization(
            path="/hermes/cache/current.png",
            mime_type="image/webp",
            kind="image",
            display_name="current.webp",
            reference_kind="image",
            reference_id="current",
        )
        current_audio = HermesAttachmentMaterialization(
            path="/hermes/cache/current.ogg",
            mime_type="audio/ogg",
            kind="audio",
            display_name="current.ogg",
            reference_kind="record",
            reference_id="current-record",
        )
        history = (
            ResolvedMessage(
                body=batch.history[0].body,
                context_image_materializations=(history_first,),
            ),
            ResolvedMessage(
                body=batch.history[1].body,
                context_image_materializations=(shared,),
            ),
        )
        current = ResolvedMessage(
            body=batch.current.body,
            hermes_attachment_materializations=(shared, current_image, current_audio),
        )
        return ResolvedTriggerBatch(batch.chat_key, history, current)


class FailedContextImageResolver(FakeResolver):
    """返回历史图片失败后的安全降级结果。"""

    async def resolve_batch(self, batch: object) -> ResolvedTriggerBatch:
        """保留失败占位但不提供图片 materialization。"""

        history = tuple(
            ResolvedMessage(body="[img:file_name=NOT SUPPORTED]") for _item in batch.history
        )
        current = ResolvedMessage(body=batch.current.body)
        return ResolvedTriggerBatch(batch.chat_key, history, current)


class FakeMuteTracker:
    """为群 Gate 提供已确认的 unmuted 二态快照。"""

    def gate_snapshot(self, _group_id: int) -> tuple[str, str]:
        """返回可发言的成员和全体禁言状态。"""

        return "unmuted", "unmuted"


class RecordingWill:
    """记录 Will 调用，验证系统事件不进入普通策略路径。"""

    def __init__(self) -> None:
        self.inputs: list[object] = []
        self.reply_costs: list[str] = []

    def decide(self, input_value: object) -> str:
        """记录输入并返回 trigger 供普通消息测试使用。"""

        self.inputs.append(input_value)
        return "trigger"

    def on_reply_submitted(self, chat_key: str) -> None:
        """记录 trigger 参与成本反馈。"""

        self.reply_costs.append(chat_key)


def make_pipeline(
    hermes: FakeHermes,
    resolver: FakeResolver,
    *,
    routing: RoutingConfig | None = None,
    will_engine: object | None = None,
    buffer_size: int = 20,
) -> InboundPipeline:
    """创建只包含本地 fake 依赖的入站 pipeline。"""

    return InboundPipeline(
        self_id=900000001,
        hermes=hermes,
        resource_resolver=resolver,
        gate_registry=GateRegistry(),
        will_engine=will_engine or RoutingWillEngine(routing or RoutingConfig()),
        wait_buffer=WaitBuffer(buffer_size),
        admission=ChatAdmissionCoordinator(),
        deduplicator=TtlDeduplicator(),
        message_event_cls=FakeMessageEvent,
        message_type_cls=FakeMessageType,
        mute_tracker=FakeMuteTracker(),
    )


def test_group_and_friend_triggers_map_to_hermes_with_stable_source() -> None:
    """friend/group 应分别使用 dm/group source 并保留 Milky 消息 ID。"""

    async def scenario() -> list[FakeMessageEvent]:
        hermes = FakeHermes()
        pipeline = make_pipeline(hermes, FakeResolver())
        friend = await pipeline.handle_event(load_fixture("events/message_receive.friend.json"))
        group = await pipeline.handle_event(
            load_fixture("events/message_receive.group.all_segments.json")
        )
        assert friend.classification == "trigger"
        assert group.classification == "trigger"
        await pipeline.wait_idle()
        return hermes.events

    events = asyncio.run(scenario())

    assert [event.message_id for event in events] == ["1001", "1002"]
    assert [event.source.chat_id for event in events] == ["dm:800000001", "group:700000001"]
    assert [event.source.chat_type for event in events] == ["dm", "group"]
    assert all(event.source.platform == "milky" for event in events)
    assert all(event.allow_gateway_control is False for event in events)
    assert all(event.user_id is not None and event.user_name is not None for event in events)


def test_wait_history_is_context_only_and_current_message_is_not_repeated() -> None:
    """历史 wait 消息只进入上下文，当前 trigger 只进入正文。"""

    async def scenario() -> FakeMessageEvent:
        hermes = FakeHermes()
        pipeline = make_pipeline(
            hermes,
            FakeResolver(),
            routing=RoutingConfig(direct="trigger", mention="trigger", all_message="wait"),
        )
        first = load_fixture("events/message_receive.group.all_segments.json")
        first["data"]["message_seq"] = 2001
        first["data"]["segments"] = [{"type": "text", "data": {"text": "历史消息"}}]
        second = load_fixture("events/message_receive.group.all_segments.json")
        second["data"]["message_seq"] = 2002
        second["data"]["segments"] = [
            {
                "type": "mention",
                "data": {"user_id": 900000001, "name": "合成机器人"},
            },
            {"type": "text", "data": {"text": "触发消息"}},
        ]
        assert (await pipeline.handle_event(first)).classification == "wait"
        assert (await pipeline.handle_event(second)).classification == "trigger"
        await pipeline.wait_idle()
        return hermes.events[0]

    event = asyncio.run(scenario())

    assert event.channel_context == "<合成名片 uid 800000002 msg_id 2001> 历史消息"
    assert event.text == "<合成名片 uid 800000002 msg_id 2002> @合成机器人触发消息"
    assert "触发消息" not in event.channel_context
    assert "历史消息" not in event.text


def test_dm_wait_history_is_body_only_and_group_history_stays_headered() -> None:
    """dm pipeline 上下文只交付正文，group 仍保持既有 header。"""

    class DmResolvedBodyResolver(FakeResolver):
        """为 dm 历史替换正文，确认 pipeline 使用 resolved body。"""

        async def resolve_batch(self, batch: object) -> ResolvedTriggerBatch:
            """只改写 dm 历史，保留其他场景的既有 fake 行为。"""

            resolved = await super().resolve_batch(batch)
            if not batch.chat_key.startswith("dm:"):
                return resolved
            return ResolvedTriggerBatch(
                resolved.chat_key,
                tuple(
                    ResolvedMessage(body=f"resolved:{message.body}") for message in resolved.history
                ),
                ResolvedMessage(
                    body=resolved.current.body,
                    replies=(
                        ResolvedReply(
                            message_seq=2398,
                            sender_id=900000001,
                            sender_name="合成机器人",
                            timestamp=1700000008,
                            body="机器人原文",
                            segments=(),
                        ),
                    ),
                ),
            )

    async def scenario() -> tuple[FakeMessageEvent, FakeMessageEvent]:
        hermes = FakeHermes()
        pipeline = make_pipeline(
            hermes,
            DmResolvedBodyResolver(),
            routing=RoutingConfig(
                direct="wait", mention="trigger", all_message="wait", keywords=("触发",)
            ),
        )
        friend_history = load_fixture("events/message_receive.friend.json")
        friend_history["data"]["message_seq"] = 2401
        friend_history["data"]["segments"] = [
            {
                "type": "reply",
                "data": {
                    "message_seq": 2399,
                    "sender_id": 900000001,
                    "sender_name": "合成机器人",
                    "time": 1700000009,
                    "segments": [{"type": "text", "data": {"text": "机器人原文"}}],
                },
            },
            {"type": "text", "data": {"text": "私聊历史\\路径\r\n下一行"}},
        ]
        friend_current = load_fixture("events/message_receive.friend.json")
        friend_current["data"]["message_seq"] = 2402
        friend_current["data"]["segments"] = [
            {
                "type": "reply",
                "data": {
                    "message_seq": 2398,
                    "sender_id": 900000001,
                    "sender_name": "合成机器人",
                    "time": 1700000008,
                    "segments": [{"type": "text", "data": {"text": "机器人原文"}}],
                },
            },
            {"type": "text", "data": {"text": "私聊触发"}},
        ]
        group_history = load_fixture("events/message_receive.group.all_segments.json")
        group_history["data"]["message_seq"] = 2403
        group_history["data"]["segments"] = [
            {"type": "text", "data": {"text": "群聊历史"}},
        ]
        group_current = load_fixture("events/message_receive.group.all_segments.json")
        group_current["data"]["message_seq"] = 2404
        group_current["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "群聊触发"}},
        ]

        assert (await pipeline.handle_event(friend_history)).classification == "wait"
        assert (await pipeline.handle_event(friend_current)).classification == "trigger"
        assert (await pipeline.handle_event(group_history)).classification == "wait"
        assert (await pipeline.handle_event(group_current)).classification == "trigger"
        await pipeline.wait_idle()
        return hermes.events[0], hermes.events[1]

    friend_event, group_event = asyncio.run(scenario())

    assert friend_event.channel_context == "resolved:私聊历史\\路径\\n下一行"
    assert friend_event.text == (
        "<合成好友 uid 800000001 msg_id 2402 reply_to your_previous_msg> 私聊触发"
    )
    assert friend_event.reply_to_message_id == "2398"
    assert friend_event.reply_to_author_id == "900000001"
    assert friend_event.reply_to_is_own_message is True
    assert "reply_to" not in friend_event.channel_context
    assert "msg_id" not in friend_event.channel_context
    assert group_event.channel_context == "<合成名片 uid 800000002 msg_id 2403> 群聊历史"
    assert group_event.text == "<合成名片 uid 800000002 msg_id 2404> @合成机器人群聊触发"


def test_dm_history_and_system_context_keep_ingress_order() -> None:
    """dm 普通历史和系统事件混排时只改变普通记录模板。"""

    async def scenario() -> FakeMessageEvent:
        hermes = FakeHermes()
        pipeline = make_pipeline(
            hermes,
            FakeResolver(),
            routing=RoutingConfig(
                direct="wait", mention="trigger", all_message="wait", keywords=("触发",)
            ),
        )
        history = load_fixture("events/message_receive.friend.json")
        history["data"]["message_seq"] = 2501
        history["data"]["segments"] = [{"type": "text", "data": {"text": "私聊历史"}}]
        trigger = load_fixture("events/message_receive.friend.json")
        trigger["data"]["message_seq"] = 2502
        trigger["data"]["segments"] = [{"type": "text", "data": {"text": "私聊触发"}}]
        assert (await pipeline.handle_event(history)).classification == "wait"
        recall = load_fixture("events/system.message_recall.friend.json")
        recall["data"]["message_seq"] = 2503
        assert (await pipeline.handle_event(recall)).classification == "observe_only"
        assert (await pipeline.handle_event(trigger)).classification == "trigger"
        await pipeline.wait_idle()
        return hermes.events[0]

    event = asyncio.run(scenario())

    assert event.channel_context == (
        "私聊历史\n<event message_recall> uid 800000001 撤回了消息 msg_seq 2503"
    )
    assert event.text == "<合成好友 uid 800000001 msg_id 2502> 私聊触发"


def test_pipeline_logs_wait_trigger_gate_and_handoff(caplog) -> None:
    """入站关键边界使用普通低敏日志消息表达。"""

    async def scenario() -> None:
        hermes = FakeHermes()
        pipeline = make_pipeline(
            hermes,
            FakeResolver(),
            routing=RoutingConfig(direct="trigger", mention="trigger", all_message="wait"),
        )
        first = load_fixture("events/message_receive.group.all_segments.json")
        first["data"]["message_seq"] = 2101
        first["data"]["segments"] = [{"type": "text", "data": {"text": "合成历史"}}]
        second = load_fixture("events/message_receive.group.all_segments.json")
        second["data"]["message_seq"] = 2102
        second["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "合成触发"}},
        ]
        with caplog.at_level(logging.DEBUG, logger="hermes_plugins.milky.inbound.pipeline"):
            assert (await pipeline.handle_event(first)).classification == "wait"
            assert (await pipeline.handle_event(second)).classification == "trigger"
            await pipeline.wait_idle()

    asyncio.run(scenario())

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "event=milky.inbound" in message and "decision=wait" in message for message in messages
    )
    assert any(
        "event=milky.inbound" in message and "decision=trigger" in message for message in messages
    )
    assert any(
        "event=milky.inbound" in message
        and "stage=handoff" in message
        and "classification=accepted" in message
        for message in messages
    )
    assert all("合成历史" not in message and "合成触发" not in message for message in messages)


def test_context_images_precede_current_images_and_deduplicate_media_paths() -> None:
    """历史图片应先于当前附件进入 media_urls，并按路径去重。"""

    async def scenario() -> FakeMessageEvent:
        hermes = FakeHermes()
        pipeline = make_pipeline(
            hermes,
            ContextImageResolver(),
            routing=RoutingConfig(direct="trigger", mention="trigger", all_message="wait"),
        )
        first = load_fixture("events/message_receive.group.all_segments.json")
        first["data"]["message_seq"] = 2101
        first["data"]["segments"] = [
            {"type": "image", "data": {"resource_id": "history-first"}},
        ]
        second = load_fixture("events/message_receive.group.all_segments.json")
        second["data"]["message_seq"] = 2102
        second["data"]["segments"] = [
            {"type": "image", "data": {"resource_id": "history-shared"}},
        ]
        current = load_fixture("events/message_receive.group.all_segments.json")
        current["data"]["message_seq"] = 2103
        current["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "image", "data": {"resource_id": "current-shared"}},
            {"type": "text", "data": {"text": "触发消息"}},
        ]
        assert (await pipeline.handle_event(first)).classification == "wait"
        assert (await pipeline.handle_event(second)).classification == "wait"
        assert (await pipeline.handle_event(current)).classification == "trigger"
        await pipeline.wait_idle()
        return hermes.events[0]

    event = asyncio.run(scenario())

    assert event.media_urls == [
        "/hermes/cache/history-first.png",
        "/hermes/cache/shared.png",
        "/hermes/cache/current.png",
        "/hermes/cache/current.ogg",
    ]
    assert event.media_types == ["image/png", "image/jpeg", "image/webp", "audio/ogg"]
    assert event.channel_context is not None
    assert "历史消息" not in event.text
    assert "触发消息" not in event.channel_context


def test_pipeline_uses_finalized_body_context_and_media_representatives(tmp_path: Path) -> None:
    """pipeline 应从同一批次 finalization 交付正文、上下文和媒体。"""

    class PipelineHermes(FakeHermes):
        """将两个脱敏 URL 映射到内容相同的临时文件。"""

        def __init__(self) -> None:
            super().__init__()
            self.paths = {
                "history": str(tmp_path / "history.png"),
                "current": str(tmp_path / "current.webp"),
            }
            Path(self.paths["history"]).write_bytes(b"same-image")
            Path(self.paths["current"]).write_bytes(b"same-image")

        async def cache_image_from_url(self, url: str, ext: str = ".jpg") -> str:
            """返回 fake Hermes 已落盘的本地路径。"""

            del ext
            return self.paths[url]

    async def scenario() -> FakeMessageEvent:
        hermes = PipelineHermes()
        pipeline = make_pipeline(
            hermes,
            ResourceResolver(object(), hermes),
            routing=RoutingConfig(direct="trigger", mention="trigger", all_message="wait"),
        )
        history = load_fixture("events/message_receive.group.all_segments.json")
        history["data"]["message_seq"] = 2301
        history["data"]["segments"] = [
            {
                "type": "image",
                "data": {"temp_url": "history", "summary": "历史图", "mime_type": "image/png"},
            }
        ]
        current = load_fixture("events/message_receive.group.all_segments.json")
        current["data"]["message_seq"] = 2302
        current["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "image", "data": {"temp_url": "current", "summary": "当前图"}},
        ]
        assert (await pipeline.handle_event(history)).classification == "wait"
        assert (await pipeline.handle_event(current)).classification == "trigger"
        await pipeline.wait_idle()
        return hermes.events[0]

    event = asyncio.run(scenario())

    assert event.channel_context is not None
    assert "history.png" in event.channel_context
    assert str(tmp_path / "current.webp") not in event.text
    assert "history.png" in event.text
    assert event.media_urls == [str(tmp_path / "history.png")]
    assert event.media_types == ["image/png"]


def test_failed_context_image_keeps_placeholder_without_media_url() -> None:
    """历史图片失败时保留占位，不能伪造媒体路径。"""

    async def scenario() -> FakeMessageEvent:
        hermes = FakeHermes()
        pipeline = make_pipeline(
            hermes,
            FailedContextImageResolver(),
            routing=RoutingConfig(direct="trigger", mention="trigger", all_message="wait"),
        )
        history = load_fixture("events/message_receive.group.all_segments.json")
        history["data"]["message_seq"] = 2201
        history["data"]["segments"] = [
            {"type": "image", "data": {"resource_id": "failed-history-image"}},
        ]
        current = load_fixture("events/message_receive.group.all_segments.json")
        current["data"]["message_seq"] = 2202
        current["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "触发消息"}},
        ]
        assert (await pipeline.handle_event(history)).classification == "wait"
        assert (await pipeline.handle_event(current)).classification == "trigger"
        await pipeline.wait_idle()
        return hermes.events[0]

    event = asyncio.run(scenario())

    assert event.media_urls == []
    assert event.media_types == []
    assert event.channel_context is not None
    assert "[img:file_name=NOT SUPPORTED]" in event.channel_context


def test_duplicate_gate_deny_temp_and_system_event_stop_before_resolver_or_hermes(caplog) -> None:
    """重复、门禁拒绝、temp 和系统事件都不得进入资源或 Hermes。"""

    async def scenario() -> tuple[list[str], list[FakeMessageEvent], list[str]]:
        hermes = FakeHermes()
        resolver = FakeResolver()
        observed: list[str] = []
        pipeline = make_pipeline(hermes, resolver)
        pipeline = pipeline.with_observer(lambda event: observed.append(event.event_type))
        event = load_fixture("events/message_receive.friend.json")
        assert (await pipeline.handle_event(event)).classification == "trigger"
        assert (await pipeline.handle_event(event)).classification == "duplicate"
        denied = load_fixture("events/message_receive.friend.json")
        denied["data"]["message_seq"] = 1009
        denied["data"]["sender_id"] = 900000001
        denied["data"]["friend"]["user_id"] = 900000001
        denied["data"]["peer_id"] = 900000001
        assert (await pipeline.handle_event(denied)).classification == "denied"
        assert (
            await pipeline.handle_event(load_fixture("events/message_receive.temp.json"))
        ).classification == "ignored_temp"
        assert (
            await pipeline.handle_event(load_fixture("events/system.message_recall.json"))
        ).classification == "observe_only"
        await pipeline.wait_idle()
        return [call[1] for call in resolver.calls], hermes.events, observed

    caplog.set_level(logging.DEBUG, logger="hermes_plugins.milky.inbound.pipeline")
    calls, events, observed = asyncio.run(scenario())

    assert calls == ["1001"]
    assert [event.message_id for event in events] == ["1001"]
    assert observed == ["message_recall"]
    assert any(
        "event=milky.inbound" in record.getMessage()
        and "stage=gate" in record.getMessage()
        and "reason=self_message" in record.getMessage()
        for record in caplog.records
    )


def test_message_recall_stays_observe_only_without_normal_pipeline_side_effects() -> None:
    """撤回事件只登记上下文，不触发 canonical、Will、资源或 Hermes turn。"""

    async def scenario() -> tuple[
        PipelineResult, FakeResolver, FakeHermes, RecordingWill, InboundPipeline
    ]:
        hermes = FakeHermes()
        resolver = FakeResolver()
        will = RecordingWill()
        pipeline = make_pipeline(hermes, resolver).with_will_engine(will)
        result = await pipeline.handle_event(load_fixture("events/system.message_recall.json"))
        await pipeline.wait_idle()
        return result, resolver, hermes, will, pipeline

    result, resolver, hermes, will, pipeline = asyncio.run(scenario())

    assert result.classification == "observe_only"
    assert resolver.calls == []
    assert hermes.events == []
    assert will.inputs == []
    assert pipeline.reply_costs == 0
    assert pipeline._system_context.size("group:700000001") == 1


def test_recall_context_failure_is_recorded_without_readding_or_creating_turn() -> None:
    """撤回上下文交接失败时只记录安全失败，不能回填批次或重复执行。"""

    async def scenario() -> tuple[InboundPipeline, FakeHermes]:
        hermes = FakeHermes()
        hermes.handle_message = _raise_submission  # type: ignore[method-assign]
        pipeline = make_pipeline(hermes, FakeResolver())
        assert (
            await pipeline.handle_event(load_fixture("events/system.message_recall.json"))
        ).classification == "observe_only"
        trigger = load_fixture("events/message_receive.group.all_segments.json")
        trigger["data"]["message_seq"] = 1010
        trigger["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "交接触发"}},
        ]
        assert (await pipeline.handle_event(trigger)).classification == "trigger"
        await pipeline.wait_idle()
        return pipeline, hermes

    pipeline, hermes = asyncio.run(scenario())

    assert hermes.events == []
    assert pipeline._system_context.snapshot("group:700000001") == ()
    assert pipeline._buffer.snapshot("group:700000001") == ()
    assert pipeline._buffer.diagnostics[-1].reason == "detached_handoff_failed"


def test_self_poke_remains_observe_only_without_will_or_hermes_turn() -> None:
    """self-poke 可被观察，但不能绕过普通消息生命周期。"""

    async def scenario() -> tuple[str, list[tuple[str, str]], list[FakeMessageEvent], int, int]:
        hermes = FakeHermes()
        resolver = FakeResolver()
        will = RecordingWill()
        pipeline = make_pipeline(
            hermes,
            resolver,
            routing=RoutingConfig(poke="trigger", all_message="trigger"),
        ).with_will_engine(will)
        result = await pipeline.handle_event(
            load_fixture("../will_routing/target_signals.json")["nudge_cases"][0]["event"]
        )
        await pipeline.wait_idle()
        return (
            result.classification,
            resolver.calls,
            hermes.events,
            pipeline.reply_costs,
            len(will.inputs),
        )

    classification, calls, events, reply_costs, will_calls = asyncio.run(scenario())

    assert classification == "observe_only"
    assert calls == []
    assert events == []
    assert reply_costs == 0
    assert will_calls == 0


def test_materialization_finishes_before_mapping_and_submit_does_not_wait_for_agent() -> None:
    """资源 helper 必须先完成，pipeline 不等待 Hermes 后续 Agent。"""

    async def scenario() -> tuple[FakeMessageEvent, bool, bool, bool]:
        hermes = FakeHermes()
        resolver = FakeResolver()
        pipeline = make_pipeline(hermes, resolver)
        result = await pipeline.handle_event(load_fixture("events/message_receive.friend.json"))
        assert result.classification == "trigger"
        await resolver.started.wait()
        await pipeline.wait_idle()
        return (
            hermes.events[0],
            hermes.handle_returned.is_set(),
            hermes.agent_finished.is_set(),
            resolver.completed.is_set(),
        )

    event, submitted, agent_finished, resolved = asyncio.run(scenario())

    assert submitted is True
    assert agent_finished is False
    assert resolved is True
    assert event.media_urls == ["/hermes/cache/current.png"]
    assert event.media_types == ["image/png"]


def test_image_segment_waits_without_image_route_and_triggers_by_keyword() -> None:
    """图片仍进入规范化和延迟补全，但不再通过独立 image route 触发。"""

    async def scenario() -> tuple[list[tuple[str, str]], FakeMessageEvent]:
        hermes = FakeHermes()
        resolver = FakeResolver()
        pipeline = make_pipeline(
            hermes,
            resolver,
            routing=RoutingConfig(all_message="wait", keywords=("提醒",)),
        )
        image_only = load_fixture("events/message_receive.group.all_segments.json")
        image_only["data"]["message_seq"] = 4001
        image_only["data"]["segments"] = [
            {"type": "image", "data": {"resource_id": "fixture-image-resource"}}
        ]
        assert (await pipeline.handle_event(image_only)).classification == "wait"
        assert resolver.calls == []

        keyword_trigger = load_fixture("events/message_receive.group.all_segments.json")
        keyword_trigger["data"]["message_seq"] = 4002
        keyword_trigger["data"]["segments"] = [
            {"type": "image", "data": {"resource_id": "fixture-image-resource"}},
            {"type": "text", "data": {"text": "请提醒我"}},
        ]
        assert (await pipeline.handle_event(keyword_trigger)).classification == "trigger"
        await pipeline.wait_idle()
        return resolver.calls, hermes.events[0]

    calls, event = asyncio.run(scenario())

    assert calls == [("group:700000001", "4002")]
    assert event.message_id == "4002"
    assert event.media_types == ["image/png"]


def test_reply_cost_runs_once_for_each_trigger_before_detached_handoff() -> None:
    """每次 trigger 都在 detached 交接前扣费，资源或 Hermes 失败也保留。"""

    async def scenario() -> tuple[int, int, int, int, int, int, int, int]:
        hermes = FakeHermes()
        resolver = FakeResolver()
        will = RecordingWill()
        pipeline = make_pipeline(hermes, resolver, will_engine=will)
        await pipeline.handle_event(load_fixture("events/message_receive.friend.json"))
        before_handoff = (
            pipeline.reply_costs,
            len(will.reply_costs),
            len(resolver.calls),
        )
        await pipeline.wait_idle()
        successful_cost = pipeline.reply_costs

        failing_hermes = FakeHermes()
        failing_hermes.handle_message = _raise_submission  # type: ignore[method-assign]
        failing_will = RecordingWill()
        failing = make_pipeline(failing_hermes, FakeResolver(), will_engine=failing_will)
        await failing.handle_event(
            load_fixture("events/message_receive.friend.no_message_seq.json")
        )
        await failing.wait_idle()
        failing_resolver = FailingResolver()
        resolver_failure_will = RecordingWill()
        resolver_failure = make_pipeline(
            FakeHermes(),
            failing_resolver,
            will_engine=resolver_failure_will,
        )
        await resolver_failure.handle_event(
            load_fixture("events/message_receive.friend.no_message_seq.json")
        )
        await resolver_failure.wait_idle()
        return (
            before_handoff[0],
            before_handoff[1],
            before_handoff[2],
            successful_cost,
            failing.reply_costs,
            len(failing_will.reply_costs),
            resolver_failure.reply_costs,
            len(resolver_failure_will.reply_costs),
        )

    (
        before_cost,
        before_feedback,
        before_resolver,
        successful_cost,
        failing_cost,
        failing_feedback,
        resolver_failure_cost,
        resolver_failure_feedback,
    ) = asyncio.run(scenario())

    assert before_cost == 1
    assert before_feedback == 1
    assert before_resolver == 0
    assert successful_cost == 1
    assert failing_cost == 1
    assert failing_feedback == 1
    assert resolver_failure_cost == 1
    assert resolver_failure_feedback == 1


def test_same_chat_next_willingness_decision_observes_trigger_cost() -> None:
    """同 chat 的后续 Will 决策必须读取 admission 内已扣除的成本。"""

    async def scenario() -> tuple[str, str, float, int, int]:
        random_values = iter((0.0, 0.6))
        will = WillingnessWillEngine(
            WillingnessConfig(
                initial_score=60,
                text_gain=20,
                mention_gain=0,
                quote_gain=0,
                direct_gain=0,
                image_gain=0,
                probability_threshold=70,
                probability_amplifier=0.05,
                reply_cost=35,
            ),
            clock=lambda: 0.0,
            random_fn=lambda: next(random_values),
        )
        hermes = FakeHermes()
        resolver = FakeResolver()
        pipeline = make_pipeline(hermes, resolver, will_engine=will)
        first = load_fixture("events/message_receive.friend.json")
        first["data"]["message_seq"] = 6101
        second = load_fixture("events/message_receive.friend.json")
        second["data"]["message_seq"] = 6102

        first_result = await pipeline.handle_event(first)
        score_after_first = will.get_current_willingness("dm:800000001")
        second_result = await pipeline.handle_event(second)
        await pipeline.wait_idle()
        return (
            first_result.classification,
            second_result.classification,
            score_after_first,
            pipeline.reply_costs,
            len(hermes.events),
        )

    first, second, score_after_first, costs, submitted = asyncio.run(scenario())

    assert first == "trigger"
    assert second == "wait"
    assert score_after_first == pytest.approx(50.088)
    assert costs == 1
    assert submitted == 1


def test_force_keyword_uses_normal_pipeline_boundaries_and_reply_cost() -> None:
    """强制关键词只在普通消息边界内触发，并复用一次 reply cost。"""

    async def scenario() -> tuple[str, str, str, str, int, int]:
        def fail_random() -> float:
            raise AssertionError("force keyword path sampled random")

        will = WillingnessWillEngine(
            WillingnessConfig(force_keywords=("紧急",)),
            random_fn=fail_random,
        )
        hermes = FakeHermes()
        pipeline = make_pipeline(hermes, FakeResolver(), will_engine=will)

        denied = load_fixture("events/message_receive.group.all_segments.json")
        denied["data"]["message_seq"] = 6201
        denied["data"]["sender_id"] = 900000001
        denied["data"]["segments"] = [{"type": "text", "data": {"text": "紧急"}}]
        denied["data"]["group"]["group_id"] = 700000001
        denied["data"]["group_member"]["user_id"] = 900000001
        denied["data"]["peer_id"] = 700000001
        denied_result = await pipeline.handle_event(denied)

        command = load_fixture("events/message_receive.group.all_segments.json")
        command["data"]["message_seq"] = 6202
        command["data"]["segments"] = [{"type": "text", "data": {"text": "/milky 紧急"}}]
        command_result = await pipeline.handle_event(command)

        temp = load_fixture("events/message_receive.temp.json")
        temp["data"]["segments"] = [{"type": "text", "data": {"text": "紧急"}}]
        temp_result = await pipeline.handle_event(temp)

        system_result = await pipeline.handle_event(
            load_fixture("events/system.message_recall.json")
        )

        valid = load_fixture("events/message_receive.group.all_segments.json")
        valid["data"]["message_seq"] = 6203
        valid["data"]["segments"] = [{"type": "text", "data": {"text": "请紧急处理"}}]
        await pipeline.handle_event(valid)
        await pipeline.wait_idle()

        return (
            denied_result.classification,
            command_result.classification,
            temp_result.classification,
            system_result.classification,
            pipeline.reply_costs,
            len(hermes.events),
        )

    denied, command, temp, system, costs, submitted = asyncio.run(scenario())

    assert denied == "denied"
    assert command == "command"
    assert temp == "ignored_temp"
    assert system == "observe_only"
    assert costs == 1
    assert submitted == 2


async def _raise_submission(_event: FakeMessageEvent) -> None:
    """模拟 Hermes handle_message 提交异常。"""

    raise RuntimeError("fake Hermes submission failed")


def test_group_gate_defaults_fail_closed_without_a_confirmed_mute_snapshot() -> None:
    """没有 MuteTracker 快照时，群消息不得进入 Will 或 detached 交接。"""

    async def scenario() -> tuple[str, list[tuple[str, str]]]:
        hermes = FakeHermes()
        resolver = FakeResolver()
        pipeline = InboundPipeline(
            self_id=900000001,
            hermes=hermes,
            resource_resolver=resolver,
            gate_registry=GateRegistry(),
            will_engine=RoutingWillEngine(RoutingConfig(all_message="trigger")),
            wait_buffer=WaitBuffer(),
            admission=ChatAdmissionCoordinator(),
            deduplicator=TtlDeduplicator(),
            message_event_cls=FakeMessageEvent,
            message_type_cls=FakeMessageType,
        )
        result = await pipeline.handle_event(
            load_fixture("events/message_receive.group.all_segments.json")
        )
        await pipeline.wait_idle()
        return result.classification, resolver.calls

    classification, calls = asyncio.run(scenario())

    assert classification == "denied"
    assert calls == []


def test_same_chat_triggers_do_not_wait_for_the_previous_hermes_agent() -> None:
    """同 chat 的后续 trigger 只等待短 admission，不复制或等待 Agent 队列。"""

    async def scenario() -> tuple[list[str], bool, int]:
        hermes = FakeHermes()
        resolver = FakeResolver()
        pipeline = make_pipeline(
            hermes,
            resolver,
            routing=RoutingConfig(all_message="wait", mention="trigger"),
        )
        first = load_fixture("events/message_receive.group.all_segments.json")
        first["data"]["message_seq"] = 3001
        first["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "第一条"}},
        ]
        second = load_fixture("events/message_receive.group.all_segments.json")
        second["data"]["message_seq"] = 3002
        second["data"]["segments"] = [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "第二条"}},
        ]
        assert (await pipeline.handle_event(first)).classification == "trigger"
        assert (await pipeline.handle_event(second)).classification == "trigger"
        await pipeline.wait_idle()
        return (
            [event.message_id or "" for event in hermes.events],
            hermes.agent_finished.is_set(),
            len(resolver.calls),
        )

    message_ids, agent_finished, resolve_count = asyncio.run(scenario())

    assert message_ids == ["3001", "3002"]
    assert agent_finished is False
    assert resolve_count == 2
