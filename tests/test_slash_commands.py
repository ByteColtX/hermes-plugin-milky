"""验证 Milky 斜杠命令通道、格式化诊断响应和生命周期边界。"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import load_config
from gates import GateRegistry
from inbound import canonicalize_event, is_slash_command, map_command_event, recognize_slash_command
from inbound.pipeline import InboundPipeline
from milky.client import MilkyClient, TransportResponse
from milky.resources import ResolvedMessage, ResolvedTriggerBatch
from session import ChatAdmissionCoordinator, TtlDeduplicator, WaitBuffer
from slash_commands import SlashCommandService, format_impl_info

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "slash_commands"
PROTOCOL_ROOT = Path(__file__).parent / "fixtures" / "protocol"


def load_fixture(path: Path) -> object:
    """读取脱敏命令 fixture。"""

    return json.loads(path.read_text(encoding="utf-8"))


class FakeMessageType:
    """提供命令和普通消息 mapper 所需的 Hermes 类型。"""

    TEXT = "text"
    COMMAND = "command"
    PHOTO = "photo"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


@dataclass
class FakeEvent:
    """保存交给 fake Hermes 的事件。"""

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


class FakeHermes:
    """记录命令/普通事件，不启动 Agent。"""

    def __init__(self) -> None:
        self.events: list[FakeEvent] = []

    def build_source(self, **values: object) -> object:
        """构造携带 namespaced chat key 的 source。"""

        return SimpleNamespace(
            platform="milky",
            chat_id=values["chat_id"],
            chat_type=values["chat_type"],
            user_id=values["user_id"],
            user_name=values["user_name"],
            message_id=values["message_id"],
        )

    async def handle_message(self, event: FakeEvent) -> None:
        """记录 Hermes 提交。"""

        self.events.append(event)


class DispatchingHermes(FakeHermes):
    """模拟 Hermes 既有内置、插件、未知和 Agent 分发边界。"""

    def __init__(self, plugin_handler: object | None = None) -> None:
        super().__init__()
        self.plugin_handler = plugin_handler
        self.routes: list[str] = []
        self.agent_inputs: list[str] = []
        self.plugin_results: list[object] = []
        self.agent_queue_creations = 0

    async def handle_message(self, event: FakeEvent) -> None:
        """按 command event 的控制标记模拟宿主分发。"""

        await super().handle_message(event)
        if event.allow_gateway_control and event.message_type == FakeMessageType.COMMAND:
            parts = event.text.lstrip().split(maxsplit=1)
            name = parts[0][1:].split("@", 1)[0].lower()
            args = parts[1] if len(parts) == 2 else ""
            if name in {"status", "model"}:
                self.routes.append("builtin")
            elif name == "milky" and callable(self.plugin_handler):
                self.routes.append("plugin")
                result = self.plugin_handler(args)
                if hasattr(result, "__await__"):
                    result = await result
                self.plugin_results.append(result)
            else:
                self.routes.append("unknown")
            return
        self.routes.append("agent")
        self.agent_inputs.append(event.text)


class RecordingResolver:
    """记录资源解析；命令测试可用它断言没有资源访问。"""

    def __init__(self) -> None:
        self.calls = 0

    async def resolve_batch(self, batch: object) -> ResolvedTriggerBatch:
        """只为普通消息返回没有附件的 resolved batch。"""

        self.calls += 1
        history = tuple(ResolvedMessage(item.body) for item in batch.history)
        current = ResolvedMessage(batch.current.body)
        return ResolvedTriggerBatch(batch.chat_key, history, current)


class RecordingWill:
    """记录 Will 调用并让普通正文立即 trigger。"""

    def __init__(self) -> None:
        self.decisions = 0
        self.reply_costs = 0

    def decide(self, _value: object) -> str:
        """返回普通消息的 trigger 决策。"""

        self.decisions += 1
        return "trigger"

    def on_reply_submitted(self, _chat_key: str) -> None:
        """记录 Hermes 提交后的 reply cost。"""

        self.reply_costs += 1


class UnmutedTracker:
    """为群消息提供已确认的可发言快照。"""

    def gate_snapshot(self, _group_id: int) -> tuple[str, str]:
        """返回两个 unmuted 状态。"""

        return "unmuted", "unmuted"


def make_pipeline(
    hermes: FakeHermes,
    resolver: RecordingResolver,
    will: object,
) -> InboundPipeline:
    """创建使用 fake 依赖的命令 pipeline。"""

    return InboundPipeline(
        self_id=900000001,
        hermes=hermes,
        resource_resolver=resolver,
        gate_registry=GateRegistry(),
        will_engine=will,
        wait_buffer=WaitBuffer(),
        admission=ChatAdmissionCoordinator(),
        deduplicator=TtlDeduplicator(),
        message_event_cls=FakeEvent,
        message_type_cls=FakeMessageType,
        mute_tracker=UnmutedTracker(),
    )


def canonical_command(path: str) -> object:
    """读取并 canonicalize 一条命令消息。"""

    result = canonicalize_event(
        load_fixture(FIXTURE_ROOT / "events" / path), expected_self_id=900000001
    )
    assert result.value is not None
    return result.value


@pytest.mark.parametrize(
    ("path", "name", "args"),
    [
        ("friend_builtin_status.json", "status", ""),
        ("group_plugin_milky.json", "milky", ""),
        ("group_plugin_milky_args.json", "milky", "extra"),
        ("group_unknown_command.json", "unknown", "neutral-argument"),
    ],
)
def test_recognizes_friend_group_commands_and_preserves_arguments(
    path: str, name: str, args: str
) -> None:
    """friend/group 命令应忽略前导空白并保留命令参数。"""

    command = recognize_slash_command(canonical_command(path))

    assert command is not None
    assert command.name == name
    assert command.args == args
    assert command.text == command.text.lstrip()


@pytest.mark.parametrize(
    "segments",
    [
        [
            {"type": "mention", "data": {"user_id": 900000001, "name": "合成机器人"}},
            {"type": "text", "data": {"text": "/status"}},
        ],
        [
            {
                "type": "reply",
                "data": {
                    "message_seq": 1000,
                    "sender_id": 800000003,
                    "time": 1700000005,
                    "segments": [],
                },
            },
            {"type": "text", "data": {"text": "/status"}},
        ],
        [
            {"type": "forward", "data": {"forward_id": "fixture-forward-id", "preview": []}},
            {"type": "text", "data": {"text": "/status"}},
        ],
        [
            {"type": "future_segment_extension", "data": {"opaque": "neutral"}},
            {"type": "text", "data": {"text": "/status"}},
        ],
        [{"type": "markdown", "data": {"content": "/status"}}],
    ],
)
def test_structured_or_non_plain_segments_are_not_commands(
    segments: list[dict[str, object]],
) -> None:
    """媒体、reply、forward、未知和 markdown segment 不得伪装成命令。"""

    payload = copy.deepcopy(load_fixture(FIXTURE_ROOT / "events/friend_builtin_status.json"))
    assert isinstance(payload, dict)
    payload["data"]["segments"] = segments

    result = canonicalize_event(payload, expected_self_id=900000001)

    assert result.value is not None
    assert is_slash_command(result.value) is False


def test_pipeline_routes_command_after_gate_before_will_and_resources() -> None:
    """合法命令只进入 Hermes command event，不改变 Will、buffer 或资源状态。"""

    async def scenario() -> tuple[InboundPipeline, RecordingResolver, RecordingWill, FakeHermes]:
        hermes = FakeHermes()
        resolver = RecordingResolver()
        will = RecordingWill()
        pipeline = make_pipeline(hermes, resolver, will)
        result = await pipeline.handle_event(
            load_fixture(FIXTURE_ROOT / "events/group_plugin_milky.json")
        )
        assert result.classification == "command"
        await pipeline.wait_idle()
        return pipeline, resolver, will, hermes

    pipeline, resolver, will, hermes = asyncio.run(scenario())

    event = hermes.events[0]
    assert event.text == "/milky"
    assert event.message_type == FakeMessageType.COMMAND
    assert event.allow_gateway_control is True
    assert event.source.chat_id == "group:700000001"
    assert event.source.platform == "milky"
    assert event.message_id == "1102"
    assert resolver.calls == 0
    assert will.decisions == 0
    assert will.reply_costs == 0
    assert pipeline.reply_costs == 0


def test_gate_temp_system_duplicate_and_plain_text_boundaries() -> None:
    """Gate、temp、系统事件和 dedup 必须在命令 handler 前生效。"""

    async def scenario() -> tuple[list[str], list[str], RecordingResolver, RecordingWill]:
        hermes = FakeHermes()
        resolver = RecordingResolver()
        will = RecordingWill()
        pipeline = make_pipeline(hermes, resolver, will)
        command = load_fixture(FIXTURE_ROOT / "events/friend_builtin_status.json")
        assert (await pipeline.handle_event(command)).classification == "command"
        assert (await pipeline.handle_event(command)).classification == "duplicate"

        denied = copy.deepcopy(command)
        denied["data"]["message_seq"] = 1199
        denied["data"]["sender_id"] = 900000001
        denied["data"]["peer_id"] = 900000001
        denied["data"]["friend"]["user_id"] = 900000001
        assert (await pipeline.handle_event(denied)).classification == "denied"
        assert (
            await pipeline.handle_event(
                load_fixture(PROTOCOL_ROOT / "events/message_receive.temp.json")
            )
        ).classification == "ignored_temp"
        assert (
            await pipeline.handle_event(
                load_fixture(PROTOCOL_ROOT / "events/system.message_recall.json")
            )
        ).classification == "observe_only"
        plain = load_fixture(FIXTURE_ROOT / "events/friend_plain_text.json")
        assert (await pipeline.handle_event(plain)).classification == "trigger"
        await pipeline.wait_idle()
        return (
            [event.message_id or "" for event in hermes.events],
            [event.text for event in hermes.events],
            resolver,
            will,
        )

    message_ids, texts, resolver, will = asyncio.run(scenario())

    assert message_ids == ["1101", "1105"]
    assert texts[0] == "/status"
    assert texts[1].endswith("普通 / 斜杠正文")
    assert resolver.calls == 1
    assert will.decisions == 1


def test_command_mapper_preserves_identity_without_normal_message_context() -> None:
    """命令 mapper 应保留 source/身份并关闭普通消息上下文。"""

    message = canonical_command("friend_builtin_status.json")
    source = SimpleNamespace(chat_id="dm:800000001", platform="milky")
    event = map_command_event(
        message,
        source=source,
        message_event_cls=FakeEvent,
        message_type_cls=FakeMessageType,
    )

    assert event.text == "/status"
    assert event.message_type == FakeMessageType.COMMAND
    assert event.allow_gateway_control is True
    assert event.channel_context is None
    assert event.message_id == "1101"
    assert event.user_id == "800000001"


@dataclass
class FakeTransport:
    """按顺序返回脱敏的 fake HTTP 响应。"""

    responses: list[TransportResponse | BaseException]

    def __post_init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.close_calls = 0

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse:
        """记录请求并返回 fixture 响应。"""

        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": json.loads(body),
                "timeout": timeout,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def close(self) -> None:
        """记录 transport 释放。"""

        self.close_calls += 1


def make_response(path: str, *, status_code: int = 200) -> TransportResponse:
    """把 Action fixture 转成 HTTP response。"""

    body = (FIXTURE_ROOT / "actions" / path).read_bytes()
    return TransportResponse(status_code, body, {})


def make_client(transport: FakeTransport) -> MilkyClient:
    """创建使用合成配置的 Milky client。"""

    return MilkyClient(
        load_config(
            {
                "MILKY_BASE_URL": "https://localhost:5500/milky",
                "MILKY_ACCESS_TOKEN": "fixture-token",
            }
        ),
        transport=transport,
    )


def test_get_impl_info_posts_empty_body_and_returns_exact_raw_json() -> None:
    """get_impl_info 应保留完整 JSON envelope 和扩展字段。"""

    async def scenario() -> tuple[str, FakeTransport]:
        transport = FakeTransport([make_response("get_impl_info.ok.json")])
        client = make_client(transport)
        raw = await client.get_impl_info()
        await client.close()
        return raw, transport

    raw, transport = asyncio.run(scenario())

    assert raw == (FIXTURE_ROOT / "actions/get_impl_info.ok.json").read_text(encoding="utf-8")
    request = transport.requests[0]
    assert request["method"] == "POST"
    assert request["url"] == "https://localhost:5500/milky/api/get_impl_info"
    assert request["body"] == {}
    assert request["headers"]["Authorization"] == "Bearer fixture-token"
    assert transport.close_calls == 1
    assert json.loads(raw)["top_extension"] == "preserve-me"
    assert json.loads(raw)["data"]["data_extension"] == "preserve-me"


def test_format_impl_info_returns_human_readable_summary_without_extensions() -> None:
    """get_impl_info 命令应将已知字段格式化为中文摘要并忽略扩展字段。"""

    raw = (FIXTURE_ROOT / "actions/get_impl_info.ok.json").read_text(encoding="utf-8")

    assert format_impl_info(raw) == (
        "Milky 信息\n"
        "实现: Synthetic Milky\n"
        "版本: fixture-1\n"
        "Milky 版本: 1.3\n"
        "QQ 协议: synthetic (fixture-qq-1)"
    )


@pytest.mark.parametrize(
    ("response", "status_code", "classification"),
    [
        ("get_impl_info.missing_field.json", 200, "malformed"),
        ("get_impl_info.rejected.json", 200, "rejected"),
        ("get_impl_info.non_json.txt", 200, "malformed"),
        ("get_impl_info.http_error.json", 503, "http_error"),
        ("get_impl_info.transport_unknown.json", 0, "transport_unknown"),
    ],
)
def test_get_impl_info_failures_are_classified_without_body_or_exception_text(
    response: str, status_code: int, classification: str
) -> None:
    """诊断失败不得把响应正文或底层异常带给命令用户。"""

    async def scenario() -> str:
        if classification == "transport_unknown":
            transport = FakeTransport([OSError("fixture secret transport detail")])
        else:
            transport = FakeTransport([make_response(response, status_code=status_code)])
        service = SlashCommandService()
        service.bind_client(make_client(transport))
        return await service.handle("")

    result = asyncio.run(scenario())

    assert result.startswith(classification)
    assert "fixture secret" not in result
    assert "synthetic service failure" not in result


def test_slash_service_rejects_arguments_and_requires_one_bound_client() -> None:
    """参数、未连接和多 client 均须在网络访问前 fail-closed。"""

    async def scenario() -> tuple[list[str], str, str, str]:
        transport = FakeTransport([make_response("get_impl_info.ok.json")])
        client = make_client(transport)
        service = SlashCommandService()
        with_args = await service.handle("extra")
        unbound = await service.handle("")
        service.bind_client(client)
        service.bind_client(object())
        multiple = await service.handle("")
        return [request["url"] for request in transport.requests], with_args, unbound, multiple

    requests, with_args, unbound, multiple = asyncio.run(scenario())

    assert requests == []
    assert with_args.startswith("invalid_input")
    assert unbound.startswith("unsupported")
    assert multiple.startswith("unsupported")


def test_fake_hermes_keeps_builtin_plugin_unknown_and_agent_paths_separate() -> None:
    """四类输入应由 Hermes 控制面区分，插件不创建第二个 Agent 队列。"""

    async def scenario() -> DispatchingHermes:
        hermes = DispatchingHermes(plugin_handler=lambda _args: "plugin result")
        resolver = RecordingResolver()
        will = RecordingWill()
        pipeline = make_pipeline(hermes, resolver, will)
        base = load_fixture(FIXTURE_ROOT / "events/friend_builtin_status.json")
        messages = [
            ("/status", 1201),
            ("/model gpt-5.5", 1202),
            ("/milky", 1203),
            ("/unknown", 1204),
            ("普通正文", 1205),
        ]
        for text, message_id in messages:
            event = copy.deepcopy(base)
            event["data"]["message_seq"] = message_id
            event["data"]["segments"][0]["data"]["text"] = text
            assert (await pipeline.handle_event(event)).classification in {"command", "trigger"}
        await pipeline.wait_idle()
        return hermes

    hermes = asyncio.run(scenario())

    assert hermes.routes == ["builtin", "builtin", "plugin", "unknown", "agent"]
    assert hermes.agent_inputs == ["<合成好友 uid 800000001 msg_id 1205> 普通正文"]
    assert hermes.agent_queue_creations == 0


def test_friend_group_pipeline_connects_command_service_to_one_fake_action_client() -> None:
    """friend/group 命令应经同一生命周期 client 调用只读 Action。"""

    async def scenario() -> tuple[
        DispatchingHermes, FakeTransport, RecordingResolver, RecordingWill
    ]:
        transport = FakeTransport(
            [
                make_response("get_impl_info.ok.json"),
                make_response("get_impl_info.ok.json"),
            ]
        )
        client = make_client(transport)
        service = SlashCommandService()
        service.bind_client(client)
        hermes = DispatchingHermes(plugin_handler=service.handle)
        resolver = RecordingResolver()
        will = RecordingWill()
        pipeline = make_pipeline(hermes, resolver, will)
        friend = load_fixture(FIXTURE_ROOT / "events/friend_builtin_status.json")
        friend["data"]["segments"][0]["data"]["text"] = "/milky"
        group = load_fixture(FIXTURE_ROOT / "events/group_plugin_milky.json")
        group["data"]["segments"][0]["data"]["text"] = "/milky"
        assert (await pipeline.handle_event(friend)).classification == "command"
        assert (await pipeline.handle_event(group)).classification == "command"
        await pipeline.wait_idle()
        await client.close()
        return hermes, transport, resolver, will

    hermes, transport, resolver, will = asyncio.run(scenario())

    assert hermes.routes == ["plugin", "plugin"]
    expected_result = (
        "Milky 信息\n"
        "实现: Synthetic Milky\n"
        "版本: fixture-1\n"
        "Milky 版本: 1.3\n"
        "QQ 协议: synthetic (fixture-qq-1)"
    )
    assert hermes.plugin_results == [expected_result, expected_result]
    assert [request["url"] for request in transport.requests] == [
        "https://localhost:5500/milky/api/get_impl_info",
        "https://localhost:5500/milky/api/get_impl_info",
    ]
    assert all(request["body"] == {} for request in transport.requests)
    assert resolver.calls == 0
    assert will.decisions == 0
    assert will.reply_costs == 0


def test_root_registers_one_command_and_injects_same_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """根入口只注册一个 /milky 命令，并把 service 注入 adapter factory。"""

    monkeypatch.setenv("MILKY_BASE_URL", "https://localhost:5500/milky")
    monkeypatch.setenv("MILKY_ACCESS_TOKEN", "fixture-token")
    module_name = "hermes_plugins.hermes_plugin_milky_slash_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        Path(__file__).parents[1] / "__init__.py",
        submodule_search_locations=[str(Path(__file__).parents[1])],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    class Context:
        """捕获命令、工具和平台注册。"""

        def __init__(self) -> None:
            self.commands: list[tuple[str, object, dict[str, object]]] = []
            self.platforms: list[dict[str, object]] = []

        def register_command(self, name: str, handler: object, **metadata: object) -> None:
            self.commands.append((name, handler, metadata))

        def register_tool(self, **kwargs: object) -> None:
            del kwargs

        def register_platform(self, **kwargs: object) -> None:
            self.platforms.append(kwargs)

    context = Context()
    import sys

    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        module.register(context)
        assert len(context.commands) == 1
        assert context.commands[0][0] == "milky"
        assert context.commands[0][2]["description"]
        assert "  - milky\n" not in (Path(__file__).parents[1] / "plugin.yaml").read_text()
        registration = context.platforms[0]
        adapter = registration["adapter_factory"](SimpleNamespace())
        assert adapter._slash_command_service is context.commands[0][1].__self__
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_slash_command_fixtures_are_synthetic_and_redacted() -> None:
    """命令 fixture 不得包含凭证、路径、live URL 或完整敏感响应。"""

    forbidden = (
        "Authorization",
        "Bearer ",
        "MILKY_ACCESS_TOKEN",
        "http://",
        "https://",
        "file://",
        "/Users/",
        "/home/",
        "live response",
    )
    for path in FIXTURE_ROOT.rglob("*"):
        if not path.is_file() or path.name == "README.md":
            continue
        contents = path.read_text(encoding="utf-8")
        assert not any(value in contents for value in forbidden), path
