"""验证 Milky adapter 的生命周期和根注册组装。"""

from __future__ import annotations

import asyncio
import importlib.util
import socket
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import adapter as adapter_module
from adapter import MilkyAdapter
from config import load_config
from outbound.tools import TOOL_SPECS
from session.identity import BotIdentity, BotIdentitySnapshot
from slash_commands import SlashCommandService

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    """记录生命周期关闭，不执行任何网络请求。"""

    def __init__(self) -> None:
        self.close_calls = 0

    async def close(self) -> None:
        """记录关闭调用。"""

        self.close_calls += 1


class LiveForwardClient(FakeClient):
    """记录真实 sender 使用的消息 Action 和身份查询。"""

    def __init__(self) -> None:
        super().__init__()
        self.login_calls = 0
        self.message_calls: list[tuple[str, dict[str, object]]] = []

    async def get_login_info(self) -> object:
        """记录不应由 live forward 路径重复触发的身份查询。"""

        self.login_calls += 1
        return SimpleNamespace(uin=900000002, nickname="重复查询身份")

    async def send_group_message(self, group_id: int, message: list[dict[str, object]]) -> object:
        """记录群消息并返回合成 message_seq。"""

        self.message_calls.append(
            ("send_group_message", {"group_id": group_id, "message": message})
        )
        return SimpleNamespace(message_seq="fixture-live-send")


class FakeMuteTracker:
    """模拟登录和禁言状态初始同步。"""

    def __init__(self, *, fail: bool = False, block: bool = False) -> None:
        self.fail = fail
        self.block = block
        self.initialized = False
        self.self_id: int | None = None
        self.nickname: str | None = None
        self.initialize_calls = 0
        self.start_calls = 0
        self.close_calls = 0
        self.initialize_started = asyncio.Event()

    async def initialize(self) -> bool:
        """完成或拒绝初始状态同步。"""

        self.initialize_calls += 1
        self.initialize_started.set()
        if self.block:
            await asyncio.Event().wait()
        if self.fail:
            raise RuntimeError("fake state sync failed")
        self.initialized = True
        self.self_id = 900000001
        self.nickname = "合成机器人"
        return True

    def start(self) -> None:
        """启动模拟 TTL 任务。"""

        self.start_calls += 1

    async def close(self) -> None:
        """停止模拟 TTL 任务。"""

        self.close_calls += 1


class FakeEventStream:
    """模拟持续运行、可取消的 SSE 事件流。"""

    def __init__(self) -> None:
        self.run_calls = 0
        self.close_calls = 0
        self.handler = None
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def run(self, handler: object) -> None:
        """保存 handler 并等待生命周期停止。"""

        assert callable(handler)
        self.run_calls += 1
        self.handler = handler
        self.started.set()
        await self.stopped.wait()

    async def emit(self, event: object) -> bool:
        """只有事件流启动后才向 pipeline 转发事件。"""

        if not callable(self.handler):
            return False
        result = self.handler(event)
        if asyncio.iscoroutine(result):
            await result
        return True

    async def close(self) -> None:
        """停止模拟事件流。"""

        self.close_calls += 1
        self.stopped.set()


class FakePipeline:
    """记录启动和 detached 任务清理。"""

    def __init__(self) -> None:
        self.start_calls = 0
        self.close_calls = 0
        self.handle_event_calls = 0

    def start(self) -> None:
        """允许接收普通事件。"""

        self.start_calls += 1

    async def close(self) -> None:
        """取消 pipeline 内部任务。"""

        self.close_calls += 1

    async def handle_event(self, event: object) -> object:
        """提供事件流所需的异步 handler。"""

        self.handle_event_calls += 1
        return event


class FakeSender:
    """验证停止后 adapter 不再进入出站 sender。"""

    def __init__(self, result: object | None = None) -> None:
        self.calls = 0
        self.close_calls = 0
        self.result = result
        self.requests: list[tuple[object, ...]] = []

    async def send(self, *args: object, **kwargs: object) -> object:
        """记录发送调用。"""

        self.calls += 1
        self.requests.append(args)
        del kwargs
        if self.result is not None:
            return self.result
        return SimpleNamespace(success=True, message_id="1")

    async def close(self) -> None:
        """记录 adapter 对出站刷新任务的清理。"""

        self.close_calls += 1


def make_config() -> object:
    """创建不含真实凭证的测试配置。"""

    return load_config(
        {
            "MILKY_BASE_URL": "https://localhost:5500/milky",
            "MILKY_ACCESS_TOKEN": "test-token",
        }
    )


def install_profile_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """为根入口测试提供显式的合成 profile 配置 API。"""

    hermes_cli = ModuleType("hermes_cli")
    hermes_cli.__path__ = []  # type: ignore[attr-defined]
    profiles = ModuleType("hermes_cli.profiles")
    profiles.get_active_profile_name = lambda: "default"  # type: ignore[attr-defined]
    core_config = ModuleType("hermes_cli.config")
    core_config.load_config_readonly = dict  # type: ignore[attr-defined]
    gateway = ModuleType("gateway")
    gateway.__path__ = []  # type: ignore[attr-defined]
    platforms = ModuleType("gateway.platforms")
    platforms.__path__ = []  # type: ignore[attr-defined]
    shared = ModuleType("gateway.platforms._shared")
    shared.get_scoped_secret = (  # type: ignore[attr-defined]
        lambda key, default=None: {
            "MILKY_BASE_URL": "https://localhost:5500/milky",
            "MILKY_ACCESS_TOKEN": "test-token",
        }.get(key, default)
    )
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.profiles", profiles)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", core_config)
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.platforms", platforms)
    monkeypatch.setitem(sys.modules, "gateway.platforms._shared", shared)


def make_adapter(
    *,
    tracker: FakeMuteTracker | None = None,
    stream: FakeEventStream | None = None,
    pipeline: FakePipeline | None = None,
    sender: FakeSender | None = None,
    client: FakeClient | None = None,
    slash_command_service: SlashCommandService | None = None,
    identity_snapshot: BotIdentitySnapshot | None = None,
) -> tuple[MilkyAdapter, FakeMuteTracker, FakeEventStream, FakePipeline, FakeSender, FakeClient]:
    """创建只使用 fake 依赖的 adapter。"""

    resolved_tracker = tracker or FakeMuteTracker()
    resolved_stream = stream or FakeEventStream()
    resolved_pipeline = pipeline or FakePipeline()
    resolved_sender = sender or FakeSender()
    resolved_client = client or FakeClient()
    adapter = MilkyAdapter(
        SimpleNamespace(),
        milky_config=make_config(),
        client=resolved_client,
        event_stream=resolved_stream,
        mute_tracker=resolved_tracker,
        pipeline=resolved_pipeline,
        outbound_sender=resolved_sender,
        slash_command_service=slash_command_service,
        identity_snapshot=identity_snapshot,
    )
    return (
        adapter,
        resolved_tracker,
        resolved_stream,
        resolved_pipeline,
        resolved_sender,
        resolved_client,
    )


def test_connect_syncs_state_before_starting_event_stream() -> None:
    """初次连接必须先完成状态同步，再启动 SSE 消费。"""

    async def scenario() -> None:
        adapter, tracker, stream, pipeline, _, _ = make_adapter()

        assert await adapter.connect() is True
        await stream.started.wait()

        assert tracker.initialize_calls == 1
        assert tracker.start_calls == 1
        assert pipeline.start_calls == 1
        assert stream.run_calls == 1
        assert adapter.ready is True
        assert adapter.self_id == 900000001

        await adapter.disconnect()
        assert tracker.close_calls == 1

    asyncio.run(scenario())


def test_live_sender_reuses_initial_identity_without_extra_login_request() -> None:
    """live adapter 应绑定初始同步身份，普通消息和 forward 都不重复查登录信息。"""

    async def scenario() -> None:
        client = LiveForwardClient()
        from outbound.sender import MilkyOutboundSender

        sender = MilkyOutboundSender(
            client,
            long_text_forward_threshold=1,
            identity_loader=client.get_login_info,
        )
        adapter, _, stream, _, _, _ = make_adapter(sender=sender, client=client)

        assert await adapter.connect() is True
        await stream.started.wait()

        ordinary = await adapter.send("group:700000001", "短")
        forwarded = await adapter.send("group:700000001", "超长文本")

        assert ordinary.success is True
        assert forwarded.success is True
        assert client.login_calls == 0
        forward = client.message_calls[1][1]["message"][0]
        assert forward["type"] == "forward"
        node = forward["data"]["messages"][0]
        assert (node["user_id"], node["sender_name"]) == (900000001, "合成机器人")

        await adapter.disconnect()

    asyncio.run(scenario())


def test_connect_publishes_confirmed_identity_once_after_ready() -> None:
    """连接完成普通消息就绪后才发布账号身份，并在重连时复用快照。"""

    async def scenario() -> None:
        snapshot = BotIdentitySnapshot()
        adapter, tracker, stream, _, _, _ = make_adapter(identity_snapshot=snapshot)

        assert snapshot.read() is None
        assert await adapter.connect() is True
        await stream.started.wait()
        assert snapshot.read() == BotIdentity(900000001, "合成机器人")

        await adapter.connect(is_reconnect=True)
        assert tracker.initialize_calls == 1
        assert snapshot.read() == BotIdentity(900000001, "合成机器人")
        await adapter.disconnect()

    asyncio.run(scenario())


def test_slash_command_service_follows_adapter_client_lifecycle() -> None:
    """命令 service 必须绑定连接中的 client，停止后解除绑定。"""

    async def scenario() -> None:
        service = SlashCommandService()
        adapter, _, stream, _, _, _ = make_adapter(slash_command_service=service)

        assert service.active_client_count == 0
        assert await adapter.connect() is True
        await stream.started.wait()
        assert service.active_client_count == 1

        await adapter.disconnect()
        assert service.active_client_count == 0

    asyncio.run(scenario())


def test_reconnect_does_not_rescan_mute_state_or_duplicate_stream() -> None:
    """同一 adapter 的重连只恢复事件流，不重新扫描禁言状态。"""

    async def scenario() -> None:
        adapter, tracker, stream, pipeline, _, _ = make_adapter()

        assert await adapter.connect() is True
        await stream.started.wait()
        assert await adapter.connect(is_reconnect=True) is True

        assert tracker.initialize_calls == 1
        assert pipeline.start_calls == 1
        assert stream.run_calls == 1

        await adapter.disconnect()

    asyncio.run(scenario())


def test_initial_sync_failure_keeps_message_entry_not_ready() -> None:
    """初始同步失败时不得启动 SSE 或开放消息入口。"""

    async def scenario() -> None:
        tracker = FakeMuteTracker(fail=True)
        adapter, _, stream, pipeline, _, _ = make_adapter(tracker=tracker)

        assert await adapter.connect() is False
        assert adapter.ready is False
        assert stream.run_calls == 0
        assert pipeline.start_calls == 0
        assert adapter.identity_snapshot.read() is None

        await adapter.disconnect()

    asyncio.run(scenario())


def test_pending_initial_sync_keeps_message_and_sse_ingress_closed(monkeypatch) -> None:
    """登录、群列表或成员状态仍在同步时，普通消息和 SSE 都不得进入 pipeline。"""

    class PendingMuteTracker(FakeMuteTracker):
        """等待测试明确放行初始状态同步。"""

        def __init__(self) -> None:
            super().__init__()
            self.release_initial_sync = asyncio.Event()

        async def initialize(self) -> bool:
            """挂起于初始同步门槛，随后发布合成身份。"""

            self.initialize_calls += 1
            self.initialize_started.set()
            await self.release_initial_sync.wait()
            self.initialized = True
            self.self_id = 900000001
            self.nickname = "合成机器人"
            return True

    from adapter import BasePlatformAdapter

    ordinary_messages: list[object] = []

    async def host_message_handler(_adapter: object, event: object) -> None:
        ordinary_messages.append(event)

    monkeypatch.setattr(
        BasePlatformAdapter,
        "handle_message",
        host_message_handler,
        raising=False,
    )

    async def scenario() -> None:
        tracker = PendingMuteTracker()
        adapter, _, stream, pipeline, _, _ = make_adapter(tracker=tracker)
        ordinary_event = SimpleNamespace(
            source=SimpleNamespace(chat_id="group:700000001"),
            metadata={"gateway_session_key": "fixture-session"},
        )
        sse_event = SimpleNamespace(event_type="message_receive")
        connect_task = asyncio.create_task(adapter.connect())
        await tracker.initialize_started.wait()

        assert adapter.ready is False
        assert adapter.is_connected is False
        assert adapter._initial_sync_complete is False
        assert adapter._event_task is None
        assert stream.run_calls == 0
        assert stream.handler is None
        assert pipeline.start_calls == 0

        await adapter.handle_message(ordinary_event)
        assert ordinary_messages == []
        assert await stream.emit(sse_event) is False
        assert pipeline.handle_event_calls == 0

        tracker.release_initial_sync.set()
        assert await connect_task is True
        await stream.started.wait()
        assert adapter.ready is True

        await adapter.handle_message(ordinary_event)
        assert ordinary_messages == [ordinary_event]
        assert await stream.emit(sse_event) is True
        assert pipeline.handle_event_calls == 1
        await adapter.disconnect()

    asyncio.run(scenario())


def test_connect_cancellation_keeps_adapter_unready_until_client_cleanup() -> None:
    """连接取消时不得启动 SSE 或入口，后续停止仍应关闭 client。"""

    async def scenario() -> None:
        tracker = FakeMuteTracker(block=True)
        adapter, _, stream, pipeline, _, client = make_adapter(tracker=tracker)
        connect_task = asyncio.create_task(adapter.connect())
        await tracker.initialize_started.wait()

        connect_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await connect_task

        assert adapter.ready is False
        assert stream.run_calls == 0
        assert pipeline.start_calls == 0
        await adapter.disconnect()
        assert tracker.close_calls == 1
        assert client.close_calls == 1

    asyncio.run(scenario())


def test_section_renderer_keeps_identity_single_line_without_network() -> None:
    """异常昵称不能破坏身份首行，也不应通过快照触发网络。"""

    snapshot = BotIdentitySnapshot()
    assert snapshot.publish(900000001, "  合成\n机器人\t  ") is True
    assert snapshot.read() == BotIdentity(900000001, "合成 机器人")


def test_failed_connect_never_leaves_a_command_client_binding() -> None:
    """初始同步失败时命令 service 不得观察到半连接 client。"""

    async def scenario() -> None:
        service = SlashCommandService()
        adapter, _, stream, _, _, _ = make_adapter(
            tracker=FakeMuteTracker(fail=True),
            slash_command_service=service,
        )

        assert await adapter.connect() is False
        assert service.active_client_count == 0
        assert stream.run_calls == 0
        await adapter.disconnect()

    asyncio.run(scenario())


def test_event_stream_stop_unbinds_command_client_before_reconnect() -> None:
    """事件流结束后命令调用必须先进入未连接边界。"""

    async def scenario() -> None:
        service = SlashCommandService()
        adapter, _, stream, _, _, _ = make_adapter(slash_command_service=service)

        assert await adapter.connect() is True
        await stream.started.wait()
        stream.stopped.set()
        event_task = adapter._event_task
        assert event_task is not None
        await event_task
        assert service.active_client_count == 0
        await adapter.disconnect()

    asyncio.run(scenario())


def test_disconnect_is_idempotent_and_closes_all_owned_resources() -> None:
    """重复停止不得继续消费、发送或重复释放生命周期资源。"""

    async def scenario() -> None:
        adapter, tracker, stream, pipeline, sender, client = make_adapter()
        assert await adapter.connect() is True
        await stream.started.wait()
        event_task = adapter._event_task
        assert event_task is not None

        await adapter.disconnect()
        await adapter.disconnect()
        result = await adapter.send("dm:800000001", "停止后不发送")

        assert event_task.done()
        assert adapter._event_task is None
        assert stream.close_calls == 1
        assert pipeline.close_calls == 1
        assert client.close_calls == 1
        assert sender.close_calls == 1
        assert tracker.close_calls == 1
        assert sender.calls == 0
        assert result.success is False
        assert adapter.ready is False

    asyncio.run(scenario())


def test_adapter_returns_unknown_send_outcome_without_host_fallback() -> None:
    """Milky adapter 必须在宿主 fallback 前原样结束未知发送结果。"""

    unknown_result = SimpleNamespace(
        success=False,
        error="transport_unknown: request outcome is unknown",
        error_kind="transport_unknown",
        retryable=False,
    )

    async def scenario() -> None:
        sender = FakeSender(unknown_result)
        adapter, _, stream, _, _, _ = make_adapter(sender=sender)
        assert await adapter.connect() is True
        await stream.started.wait()

        result = await adapter._send_with_retry(
            "group:700000001",
            "原始回复",
            max_retries=2,
            base_delay=0,
        )

        assert result is unknown_result
        assert sender.calls == 1
        assert sender.requests == [("group:700000001", "原始回复", None, None)]
        await adapter.disconnect()

    asyncio.run(scenario())


def test_adapter_maps_plugin_result_to_hermes_send_result(monkeypatch) -> None:
    """插件兼容结果必须补全目标 SendResult 的发送回执字段。"""

    import adapter as adapter_module
    from outbound.sender import OutboundSendResult

    class HermesSendResult:
        """记录目标 SendResult 构造值。"""

        def __init__(self, **kwargs: object) -> None:
            self.__dict__.update(kwargs)

    monkeypatch.setattr(adapter_module, "_HermesSendResult", HermesSendResult)
    result = adapter_module._platform_send_result(
        OutboundSendResult(
            success=False,
            error="transport_unknown: request outcome is unknown",
            retryable=False,
            error_kind="transport_unknown",
            continuation_message_ids=("fixture-prior",),
        )
    )

    assert isinstance(result, HermesSendResult)
    assert result.success is False
    assert result.error_kind == "transport_unknown"
    assert result.retryable is False
    assert result.retry_after is None
    assert result.continuation_message_ids == ("fixture-prior",)


def test_member_notification_forwards_profile_scoped_origin() -> None:
    """adapter 只把已校验 origin 交给公开 PluginContext 注入 API。"""

    class InjectionContext:
        """记录已授权会话注入调用。"""

        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict[str, str]]] = []

        def inject_message(self, content: str, role: str, *, origin: dict[str, str]) -> bool:
            """记录宿主注入参数并返回接受。"""

            self.calls.append((content, role, dict(origin)))
            return True

    adapter, _, _, _, _, _ = make_adapter()
    context = InjectionContext()
    adapter._plugin_context = context
    origin = {
        "platform": "milky",
        "chat_id": "group:700000001",
        "chat_type": "group",
    }
    assert (
        adapter.inject_message(
            "<event group_member_increase> fixture",
            origin=origin,
        )
        is True
    )
    assert adapter.inject_message("incomplete", origin=None) is False
    assert context.calls == [
        (
            "<event group_member_increase> fixture",
            "user",
            origin,
        )
    ]


def test_adapter_does_not_probe_private_gateway_session_store() -> None:
    """成员事件的 origin 路由不读取 runner 私有 session store。"""

    class PrivateSessionStoreProbe:
        """在 runner 的私有 store 被读取时令测试失败。"""

        @property
        def async_session_store(self) -> object:
            raise AssertionError("private Gateway session store was accessed")

    async def scenario() -> None:
        adapter, _, stream, _, _, _ = make_adapter()
        adapter.gateway_runner = PrivateSessionStoreProbe()

        assert await adapter.connect() is True
        await stream.started.wait()
        await adapter.disconnect()

    asyncio.run(scenario())


def test_adapter_drops_hermes_implicit_reply_anchor_before_delivery() -> None:
    """adapter 交接不应把 Hermes 当前消息 anchor 传给 Milky sender。"""

    result_from_sender = SimpleNamespace(success=True, message_id="fixture-send")

    async def scenario() -> None:
        sender = FakeSender(result_from_sender)
        adapter, _, stream, _, _, _ = make_adapter(sender=sender)
        assert await adapter.connect() is True
        await stream.started.wait()

        result = await adapter._send_with_retry(
            "group:700000001",
            "[CQ:reply,id=9001]显式引用",
            reply_to="implicit-9002",
        )

        assert result is result_from_sender
        assert sender.calls == 1
        assert sender.requests == [("group:700000001", "[CQ:reply,id=9001]显式引用", None, None)]
        await adapter.disconnect()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("success", "error_kind"),
    [
        (True, None),
        (False, "invalid_input"),
        (False, "rejected"),
        (False, "malformed"),
    ],
)
def test_adapter_delegates_each_delivery_once(success: bool, error_kind: str | None) -> None:
    """所有 Milky 发送终态都不得进入宿主 fallback 或重试。"""

    result_from_sender = SimpleNamespace(
        success=success,
        error=None if success else f"{error_kind}: fixture failure",
        error_kind=error_kind,
        retryable=False,
    )

    async def scenario() -> None:
        sender = FakeSender(result_from_sender)
        adapter, _, stream, _, _, _ = make_adapter(sender=sender)
        assert await adapter.connect() is True
        await stream.started.wait()

        result = await adapter._send_with_retry("dm:800000001", "原始回复")

        assert result is result_from_sender
        assert sender.calls == 1
        assert sender.requests == [("dm:800000001", "原始回复", None, None)]
        await adapter.disconnect()

    asyncio.run(scenario())


def test_actual_hermes_delivery_hook_returns_unknown_result_once() -> None:
    """已安装 Hermes 时，真实基类必须分派到 Milky 的一次性 hook。"""

    host_root = next(
        (
            Path(entry or ".").resolve()
            for entry in sys.path
            if (Path(entry or ".") / "gateway" / "platforms" / "base.py").is_file()
        ),
        None,
    )
    if host_root is None:
        pytest.skip("Hermes host is unavailable")
    original_path = list(sys.path)
    module_name = "_milky_adapter_actual_host_test"
    try:
        sys.path[:] = [
            str(host_root),
            *(entry for entry in original_path if Path(entry or ".").resolve() != host_root),
            str(PROJECT_ROOT),
        ]
        host_base = pytest.importorskip("gateway.platforms.base")
        spec = importlib.util.spec_from_file_location(module_name, PROJECT_ROOT / "adapter.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        actual_adapter_type = module.MilkyAdapter
        unknown_result = host_base.SendResult(
            success=False,
            error="transport_unknown: request outcome is unknown",
            error_kind="transport_unknown",
            retryable=False,
        )

        async def scenario() -> None:
            sender = FakeSender(unknown_result)
            adapter = object.__new__(actual_adapter_type)
            adapter._connected = True
            adapter._closed = False
            adapter._outbound = sender

            result = await adapter._send_with_retry("group:700000001", "原始回复")

            assert result is unknown_result
            assert sender.calls == 1
            assert sender.requests == [("group:700000001", "原始回复", None, None)]

        assert issubclass(actual_adapter_type, host_base.BasePlatformAdapter)
        assert (
            actual_adapter_type._send_with_retry
            is not host_base.BasePlatformAdapter._send_with_retry
        )
        asyncio.run(scenario())
    finally:
        sys.modules.pop(module_name, None)
        sys.path[:] = original_path


def _load_root_entry() -> object:
    """按 Hermes namespaced directory plugin 方式加载根入口。"""

    module_name = "hermes_plugins.hermes_plugin_milky_lifecycle_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class FakePluginContext:
    """记录根入口注册的平台和工具。"""

    def __init__(self) -> None:
        self.platforms: list[dict[str, object]] = []
        self.tools: list[dict[str, object]] = []
        self.system_prompt_sections: list[dict[str, object]] = []

    def register_platform(self, **kwargs: object) -> None:
        """保存平台注册参数。"""

        self.platforms.append(kwargs)

    def register_tool(self, **kwargs: object) -> None:
        """保存显式工具注册参数。"""

        self.tools.append(kwargs)

    def register_system_prompt_section(self, **kwargs: object) -> None:
        """保存 system prompt section 注册参数。"""

        self.system_prompt_sections.append(kwargs)


def test_root_register_assembles_platform_without_network_or_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """根入口只组装工厂，不在注册阶段创建连接或任务。"""

    monkeypatch.setenv("MILKY_BASE_URL", "https://localhost:5500/milky")
    monkeypatch.setenv("MILKY_ACCESS_TOKEN", "test-token")
    install_profile_api(monkeypatch)

    def fail_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("注册阶段不应访问网络")

    def fail_task(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("注册阶段不应创建后台任务")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(asyncio, "create_task", fail_task)
    entry = _load_root_entry()
    context = FakePluginContext()

    try:
        entry.register(context)  # type: ignore[attr-defined]
        assert len(context.platforms) == 1
        registration = context.platforms[0]
        assert registration["name"] == "milky"
        assert registration["adapter_factory"]
        assert [item["name"] for item in context.tools] == [
            spec["name"] for spec in TOOL_SPECS
        ]
        adapter = registration["adapter_factory"](SimpleNamespace())
        assert adapter.__class__.__name__ == "MilkyAdapter"
    finally:
        for name in list(sys.modules):
            if name == entry.__name__ or name.startswith(f"{entry.__name__}."):
                sys.modules.pop(name, None)


def test_root_section_renders_identity_published_by_ready_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """根入口 section 应读取同一注册实例 adapter 连接后发布的身份。"""

    monkeypatch.setenv("MILKY_BASE_URL", "https://localhost:5500/milky")
    monkeypatch.setenv("MILKY_ACCESS_TOKEN", "test-token")
    install_profile_api(monkeypatch)
    entry = _load_root_entry()
    context = FakePluginContext()
    try:
        entry.register(context)  # type: ignore[attr-defined]
        registration = context.platforms[0]
        registered_adapter = registration["adapter_factory"](SimpleNamespace())
        snapshot = registered_adapter.identity_snapshot
        callback = context.system_prompt_sections[0]["content"]

        adapter, _, stream, _, _, _ = make_adapter(identity_snapshot=snapshot)

        async def scenario() -> None:
            assert await adapter.connect() is True
            await stream.started.wait()
            rendered = callback(
                {"profile_name": "default", "self_id": 101, "nickname": "untrusted"}
            )
            assert rendered.startswith(
                "- Your QQ uid is 900000001, and your nickname is 合成机器人.\n"
            )
            await adapter.disconnect()

        asyncio.run(scenario())
    finally:
        for name in list(sys.modules):
            if name == entry.__name__ or name.startswith(f"{entry.__name__}."):
                sys.modules.pop(name, None)


def test_full_reconnect_reads_latest_allowlist_without_reloading_other_config():
    """同实例完整重连重新读取名单，幂等连接不重读。"""

    async def scenario():
        adapter, tracker, _stream, _pipeline, _sender, _client = make_adapter()
        values = {"rules": {"group:123"}, "reads": 0}
        deduplicator = adapter._deduplicator

        def read():
            values["reads"] += 1
            return values["rules"]

        adapter._allowed_chats_reader = read
        initial_config = adapter._config
        assert await adapter.connect()
        assert adapter._chat_policy.rules == {"group:123"}
        assert await adapter.connect()
        assert values["reads"] == 1
        await adapter.disconnect()
        values["rules"] = set()
        assert await adapter.connect()
        assert not adapter._chat_policy.rules
        assert values["reads"] == 2 and tracker.initialize_calls == 2
        assert adapter._config is initial_config
        assert adapter._deduplicator is deduplicator
        await adapter.disconnect()
        await adapter.disconnect()

    asyncio.run(scenario())


def test_hermes_canonical_dedup_survives_adapter_replacement_and_keeps_limits(
    monkeypatch: pytest.MonkeyPatch,
    target_hermes_helpers,
) -> None:
    """目标 Gateway 替换 helper 继承 canonical key，并保持容量和 TTL。"""

    helpers = target_hermes_helpers
    monkeypatch.setattr(adapter_module, "_HermesMessageDeduplicator", helpers.MessageDeduplicator)
    monkeypatch.setattr(adapter_module, "_HERMES_PLATFORM_AVAILABLE", True)
    from adapter import _new_canonical_deduplicator

    now = [1_000.0]
    monkeypatch.setattr(helpers.time, "time", lambda: now[0])
    previous = SimpleNamespace(_deduplicator=_new_canonical_deduplicator())
    replacement = SimpleNamespace(_deduplicator=_new_canonical_deduplicator())
    key = "milky:900000001:group:700000001:1001"
    assert previous._deduplicator.is_duplicate(key) is False
    assert previous._deduplicator._max_size == 10_000
    assert previous._deduplicator._ttl == 300

    helpers.carry_inbound_dedup(previous, replacement)

    assert replacement._deduplicator.is_duplicate(key) is True
    assert replacement._deduplicator.is_duplicate("milky:900000001:group:700000001:1002") is False
    now[0] += 300
    assert replacement._deduplicator.is_duplicate(key) is False

    bounded = _new_canonical_deduplicator()
    for index in range(10_001):
        assert bounded.is_duplicate(f"capacity:{index}") is False
    assert bounded.contains("capacity:0") is False
    assert bounded.contains("capacity:1") is True


def test_allowlist_read_failure_never_starts_sync_or_sse():
    """读取失败不得回退注册值或进入 ready。"""

    async def scenario():
        adapter, tracker, stream, _pipeline, _sender, _client = make_adapter()

        def fail():
            raise ValueError("synthetic read failure")

        adapter._allowed_chats_reader = fail
        assert not await adapter.connect()
        assert tracker.initialize_calls == 0 and stream.run_calls == 0
        assert not adapter._connected
        await adapter.disconnect()

    asyncio.run(scenario())
