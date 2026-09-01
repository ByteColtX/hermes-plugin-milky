"""验证 Milky home channel 的 registry、live 和 standalone 出站边界。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from adapter import MilkyAdapter
from config import load_config
from gates import GateRegistry
from inbound.pipeline import InboundPipeline
from milky.client import MilkyClient, TransportResponse
from outbound.sender import MilkyOutboundSender
from outbound.standalone import make_standalone_sender
from session import ChatAdmissionCoordinator, TtlDeduplicator, WaitBuffer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "home_channel"


def load_fixture(name: str) -> object:
    """读取 home channel 脱敏 fixture。"""

    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def make_config(home_channel: str | None = "group:700000001"):
    """创建只包含合成配置的 MilkyConfig。"""

    environment = {
        "MILKY_BASE_URL": "https://localhost:5500/milky",
        "MILKY_ACCESS_TOKEN": "standalone-test-token",
    }
    if home_channel is not None:
        environment["MILKY_HOME_CHANNEL"] = home_channel
    return load_config(environment)


@dataclass
class FakeContext:
    """捕获 Hermes registry 和 ToolSpec 注册参数。"""

    platforms: list[dict[str, object]] = field(default_factory=list)
    tools: list[dict[str, object]] = field(default_factory=list)

    def register_platform(self, **kwargs: object) -> None:
        """记录 platform entry。"""

        self.platforms.append(kwargs)

    def register_tool(self, **kwargs: object) -> None:
        """记录显式工具。"""

        self.tools.append(kwargs)


@dataclass
class FakeMilkyClient:
    """记录 live/standalone 文本 Action 并提供可控序号。"""

    sequences: list[int] = field(default_factory=lambda: [7001, 7002, 7003])
    calls: list[tuple[str, int, list[dict[str, Any]]]] = field(default_factory=list)
    close_calls: int = 0

    async def send_group_message(self, group_id: int, message: list[dict[str, Any]]) -> object:
        """记录群消息。"""

        self.calls.append(("group", group_id, message))
        return type("SendResult", (), {"message_id": str(self.sequences.pop(0))})()

    async def send_private_message(self, user_id: int, message: list[dict[str, Any]]) -> object:
        """记录私聊消息。"""

        self.calls.append(("dm", user_id, message))
        return type("SendResult", (), {"message_id": str(self.sequences.pop(0))})()

    async def close(self) -> None:
        """记录临时资源释放。"""

        self.close_calls += 1


@dataclass
class FakeTransport:
    """提供 standalone 协议回归需要的单响应 HTTP transport。"""

    response: TransportResponse | BaseException
    requests: int = 0
    close_calls: int = 0

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse:
        """记录请求并返回预置结果。"""

        del method, url, headers, body, timeout
        self.requests += 1
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    async def close(self) -> None:
        """记录 transport 关闭。"""

        self.close_calls += 1


class NeverResolver:
    """如果系统事件误入资源阶段则让测试失败。"""

    async def resolve_batch(self, _batch: object) -> object:
        """系统事件不应解析资源。"""

        raise AssertionError("observe-only event reached resource resolution")


class NeverWill:
    """如果系统事件误入 Will 阶段则让测试失败。"""

    def decide(self, _value: object) -> str:
        """系统事件不应调用 Will。"""

        raise AssertionError("observe-only event reached Will")


class NeverHermes:
    """如果系统事件创建 Agent turn 则让测试失败。"""

    async def handle_message(self, _event: object) -> None:
        """系统事件不应提交 MessageEvent。"""

        raise AssertionError("observe-only event reached Hermes")


class FakeLiveMediaSender:
    """记录 adapter 对结构化出站能力的委托。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def send_image(self, *args: object, **kwargs: object) -> object:
        """记录图片委托。"""

        self.calls.append(("send_image", args, kwargs))
        return type("Result", (), {"success": True, "message_id": "7401"})()

    async def send_document(self, *args: object, **kwargs: object) -> object:
        """记录文件委托。"""

        self.calls.append(("send_document", args, kwargs))
        return type("Result", (), {"success": True, "message_id": "7402"})()


def load_plugin_entry():
    """按 Hermes namespaced package 方式加载根入口。"""

    module_name = "hermes_plugins.hermes_plugin_milky_home_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module, module_name


def test_home_fixtures_are_synthetic_and_redacted() -> None:
    """home fixture 只包含合成路由和分类，不包含敏感输入。"""

    rendered = repr((load_fixture("routes.json"), load_fixture("events.json")))

    assert "group:700000001" in rendered
    assert "dm:800000001" in rendered
    for forbidden in ("Authorization", "Bearer", "media.example", "file://", "/Users/"):
        assert forbidden not in rendered


def test_register_exposes_fixed_home_metadata_and_cron_hooks_without_network(monkeypatch) -> None:
    """注册应固定启动时目标并暴露 Hermes 所需 hook。"""

    monkeypatch.setenv("MILKY_BASE_URL", "https://localhost:5500/milky")
    monkeypatch.setenv("MILKY_ACCESS_TOKEN", "registry-test-token")
    monkeypatch.setenv("MILKY_HOME_CHANNEL", "group:700000001")
    entry, module_name = load_plugin_entry()
    context = FakeContext()
    try:
        entry.register(context)
        registration = context.platforms[0]
        assert registration["name"] == "milky"
        assert registration["label"] == "Milky"
        assert registration["cron_deliver_env_var"] == "MILKY_HOME_CHANNEL"
        assert callable(registration["env_enablement_fn"])
        assert callable(registration["standalone_sender_fn"])
        assert [tool["name"] for tool in context.tools] == [
            "send_profile_like",
            "send_friend_nudge",
            "send_group_nudge",
            "recall_group_message",
            "get_group_info",
            "get_group_member_list",
            "get_group_member_info",
            "set_group_member_mute",
            "set_group_whole_mute",
            "get_forwarded_messages",
            "get_private_file_download_url",
            "kick_group_member",
            "quit_group",
            "delete_friend",
            "get_friend_requests",
            "accept_friend_request",
            "reject_friend_request",
        ]
        enablement = registration["env_enablement_fn"]
        assert enablement() == {
            "home_channel": {"chat_id": "group:700000001", "name": "Milky Home"}
        }

        monkeypatch.setenv("MILKY_HOME_CHANNEL", "dm:800000002")
        assert enablement() == {
            "home_channel": {"chat_id": "group:700000001", "name": "Milky Home"}
        }
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(f"{module_name}."):
                sys.modules.pop(name, None)


def test_home_config_does_not_change_inbound_allowlist_or_require_readiness() -> None:
    """home channel 是出站元数据，不改变入站白名单或 adapter 就绪门槛。"""

    config = make_config("group:700000001")

    assert config.allowed_chats == frozenset()
    assert config.redacted_summary() == {
        "base_url": "https://localhost:5500/milky",
        "allowed_chat_count": 0,
        "will_engine": "routing",
        "session_buffer_size": 20,
        "has_access_token": True,
        "has_home_channel": True,
    }


def test_live_home_send_reuses_outbound_routing_and_remote_sequence() -> None:
    """live 系统文本按 group/dm 路由并使用 Milky message_seq。"""

    client = FakeMilkyClient([7101, 7102, 7103, 8101])
    sender = MilkyOutboundSender(client, max_text_length=4)

    async def scenario() -> tuple[object, object]:
        group = await sender.send("group:700000001", "系统消息内容与告警")
        dm = await sender.send("dm:800000001", "cron")
        return group, dm

    group_result, dm_result = asyncio.run(scenario())

    assert group_result.success is True
    assert group_result.message_id == "7103"
    assert group_result.continuation_message_ids == ("7101", "7102")
    assert dm_result.success is True
    assert dm_result.message_id == "8101"
    assert [call[0] for call in client.calls] == ["group", "group", "group", "dm"]


def test_live_adapter_delegates_media_and_file_to_outbound_sender() -> None:
    """live adapter 不应落到宿主纯文本媒体或文件 fallback。"""

    outbound = FakeLiveMediaSender()
    adapter = MilkyAdapter(
        object(),
        milky_config=make_config(),
        client=object(),
        event_stream=object(),
        mute_tracker=object(),
        resource_resolver=object(),
        will_engine=object(),
        pipeline=object(),
        outbound_sender=outbound,
    )
    adapter._connected = True

    async def scenario() -> tuple[object, object]:
        image = await adapter.send_image(
            "group:700000001",
            "base64://synthetic-image",
            caption="synthetic caption",
        )
        document = await adapter.send_document(
            "dm:800000001",
            "base64://synthetic-file",
            file_name="synthetic.txt",
        )
        return image, document

    image, document = asyncio.run(scenario())

    assert image.success is True
    assert document.success is True
    assert [call[0] for call in outbound.calls] == ["send_image", "send_document"]
    assert outbound.calls[0][1][:2] == ("group:700000001", "base64://synthetic-image")
    assert outbound.calls[1][1][:2] == ("dm:800000001", "base64://synthetic-file")


def test_standalone_text_send_uses_same_sender_result_and_closes_client() -> None:
    """无 live adapter 时 standalone 仍复用 sender 且释放 client。"""

    config = make_config()
    client = FakeMilkyClient([7201])
    sender = make_standalone_sender(config, client_factory=lambda _config: client)

    result = asyncio.run(sender(object(), "group:700000001", "cron result"))

    assert result == {"success": True, "message_id": "7201"}
    assert client.calls[0][:2] == ("group", 700000001)
    assert client.close_calls == 1


def test_explicit_cron_target_wins_over_configured_home_target() -> None:
    """standalone 只发送 Hermes 已解析的显式目标，不读取 home fallback。"""

    config = make_config("group:700000001")
    client = FakeMilkyClient([7202])
    sender = make_standalone_sender(config, client_factory=lambda _config: client)

    result = asyncio.run(sender(object(), "dm:800000002", "explicit cron target"))

    assert result == {"success": True, "message_id": "7202"}
    assert client.calls[0][:2] == ("dm", 800000002)
    assert client.close_calls == 1


def test_standalone_has_no_empty_or_home_target_fallback() -> None:
    """空目标、空内容和 home 标记必须在 client 创建前拒绝。"""

    factory_calls = 0

    def factory(_config):
        nonlocal factory_calls
        factory_calls += 1
        return FakeMilkyClient()

    sender = make_standalone_sender(make_config(), client_factory=factory)

    empty = asyncio.run(sender(object(), "", "no target"))
    implicit = asyncio.run(sender(object(), "home", "no implicit target"))
    blank_message = asyncio.run(sender(object(), "group:700000001", ""))

    assert empty["classification"] == "invalid_input"
    assert implicit["classification"] == "invalid_input"
    assert blank_message["classification"] == "invalid_input"
    assert factory_calls == 0


@pytest.mark.parametrize("field", ["media_files", "thread_id", "force_document"])
def test_standalone_rejects_unsafe_or_unsupported_inputs_before_client_creation(field: str) -> None:
    """standalone 不支持附件时不得直传路径、URL 或线程参数。"""

    config = make_config()
    factory_calls = 0

    def factory(_config):
        nonlocal factory_calls
        factory_calls += 1
        return FakeMilkyClient()

    sender = make_standalone_sender(config, client_factory=factory)
    kwargs = {
        "media_files": None,
        "thread_id": None,
        "force_document": False,
    }
    kwargs[field] = (
        ["opaque-attachment"]
        if field == "media_files"
        else ("thread" if field == "thread_id" else True)
    )

    result = asyncio.run(sender(object(), "group:700000001", "cron", **kwargs))

    assert result["classification"] == "unsupported"
    assert factory_calls == 0


@pytest.mark.parametrize(
    ("response", "classification"),
    [
        (
            TransportResponse(
                200,
                b'{"status":"ok","retcode":0,"data":{"message_seq":7301}}',
                {},
            ),
            None,
        ),
        (
            TransportResponse(200, b'{"status":"failed","retcode":100,"data":{}}', {}),
            "rejected",
        ),
        (TransportResponse(200, b"not-json", {}), "malformed"),
        (TransportResponse(500, b"{}", {}), "http_error"),
        (TimeoutError(), "transport_unknown"),
    ],
)
def test_standalone_protocol_outcomes_are_classified_and_closed(
    response: TransportResponse | BaseException, classification: str | None
) -> None:
    """standalone 应保留协议分类，不重试并始终关闭 HTTP transport。"""

    transport = FakeTransport(response)
    sender = make_standalone_sender(
        make_config(),
        client_factory=lambda parsed: MilkyClient(parsed, transport=transport),
    )

    result = asyncio.run(sender(object(), "dm:800000001", "cron"))

    assert transport.requests == 1
    assert transport.close_calls == 1
    if classification is None:
        assert result == {"success": True, "message_id": "7301"}
    else:
        assert result["classification"] == classification
        assert result["success"] is False
        assert "standalone send failed" in result["error"]
        assert "standalone-test-token" not in repr(result)


def test_standalone_cancellation_closes_transport_without_retry() -> None:
    """取消 standalone 时应释放 transport，且不得再次发送。"""

    transport = FakeTransport(asyncio.CancelledError())
    sender = make_standalone_sender(
        make_config(),
        client_factory=lambda parsed: MilkyClient(parsed, transport=transport),
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(sender(object(), "group:700000001", "cron"))

    assert transport.requests == 1
    assert transport.close_calls == 1


def test_home_event_fixture_remains_observe_only() -> None:
    """Milky 入站系统事件 fixture 不因 home channel 配置而触发出站。"""

    fixture = load_fixture("events.json")

    assert fixture["expected_pipeline_classification"] == "observe_only"
    assert fixture["expected_outbound_calls"] == 0
    assert fixture["expected_agent_turns"] == 0


def test_home_channel_does_not_turn_milky_system_events_into_agent_work() -> None:
    """配置 home channel 仍保持 Milky 入站系统事件 observe-only。"""

    fixture = load_fixture("events.json")
    observed: list[str] = []
    pipeline = InboundPipeline(
        self_id=900000001,
        hermes=NeverHermes(),
        resource_resolver=NeverResolver(),
        gate_registry=GateRegistry(),
        will_engine=NeverWill(),
        wait_buffer=WaitBuffer(20),
        admission=ChatAdmissionCoordinator(),
        deduplicator=TtlDeduplicator(),
        observer=lambda event: observed.append(event.event_type),
    )

    async def scenario() -> list[str]:
        for event_type in fixture["observe_only_event_types"]:
            result = await pipeline.handle_event(
                {
                    "event_type": event_type,
                    "time": 1700000000,
                    "self_id": 900000001,
                    "data": {},
                }
            )
            assert result.classification == "observe_only"
        return observed

    assert asyncio.run(scenario()) == fixture["observe_only_event_types"]
