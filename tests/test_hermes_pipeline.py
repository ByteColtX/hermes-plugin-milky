"""验证 Milky 入站消息到 Hermes MessageEvent 的交接边界。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from gates import GateRegistry
from inbound.pipeline import InboundPipeline
from milky.resources import (
    HermesAttachmentMaterialization,
    ResolvedMessage,
    ResolvedTriggerBatch,
)
from session import ChatAdmissionCoordinator, TtlDeduplicator, WaitBuffer
from will import RoutingConfig, RoutingWillEngine

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

    def decide(self, input_value: object) -> str:
        """记录输入并返回 trigger 供普通消息测试使用。"""

        self.inputs.append(input_value)
        return "trigger"


def make_pipeline(
    hermes: FakeHermes,
    resolver: FakeResolver,
    *,
    routing: RoutingConfig | None = None,
    buffer_size: int = 20,
) -> InboundPipeline:
    """创建只包含本地 fake 依赖的入站 pipeline。"""

    return InboundPipeline(
        self_id=900000001,
        hermes=hermes,
        resource_resolver=resolver,
        gate_registry=GateRegistry(),
        will_engine=RoutingWillEngine(routing or RoutingConfig()),
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


def test_duplicate_gate_deny_temp_and_system_event_stop_before_resolver_or_hermes() -> None:
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

    calls, events, observed = asyncio.run(scenario())

    assert calls == ["1001"]
    assert [event.message_id for event in events] == ["1001"]
    assert observed == ["message_recall"]


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


def test_reply_cost_runs_once_only_after_successful_handle_submission() -> None:
    """只有提交成功才扣费，mapper 或 Hermes 异常不扣费。"""

    async def scenario() -> tuple[int, int]:
        hermes = FakeHermes()
        resolver = FakeResolver()
        will = RoutingWillEngine()
        pipeline = make_pipeline(hermes, resolver)
        pipeline = pipeline.with_will_engine(will)
        await pipeline.handle_event(load_fixture("events/message_receive.friend.json"))
        await pipeline.wait_idle()
        successful_cost = pipeline.reply_costs

        failing_hermes = FakeHermes()
        failing_hermes.handle_message = _raise_submission  # type: ignore[method-assign]
        failing = make_pipeline(failing_hermes, FakeResolver())
        await failing.handle_event(
            load_fixture("events/message_receive.friend.no_message_seq.json")
        )
        await failing.wait_idle()
        return successful_cost, failing.reply_costs

    successful_cost, failed_cost = asyncio.run(scenario())

    assert successful_cost == 1
    assert failed_cost == 0


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
