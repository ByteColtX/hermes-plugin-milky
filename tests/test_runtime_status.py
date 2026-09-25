"""验证运行状态快照、可信归属和无主动探测边界。"""

import asyncio
from types import SimpleNamespace

import pytest

from milky.event_stream import SseEventStream
from slash_commands import SlashCommandService
from state.chat_policy import ChatPolicy
from state.runtime_status import UNAVAILABLE, RuntimeStatus, format_duration
from tests.test_milky_event_stream import CONFIG, BlockingResponse, FakeTransport


class Profile:
    """提供可控的只读有效配置，不提供保存接口。"""

    def __init__(self, rules):
        self.rules = rules
        self.current = True
        self.reads = 0
        self.hook = lambda: None

    def is_current(self):
        """返回注册作用域是否仍可信。"""
        return self.current

    def allowed_chats(self):
        """读取一次配置并模拟同期状态变化。"""
        self.reads += 1
        self.hook()
        if isinstance(self.rules, Exception):
            raise self.rules
        return self.rules


def setup(rules=("dm:*", "group:123")):
    """组装不访问配置、图库或网络的观察者。"""
    profile = Profile(rules)
    policy = ChatPolicy(rules)
    stream = SimpleNamespace(connection_state="connected")
    now = [1000.0]
    status = RuntimeStatus(policy, profile, lambda: stream, clock=lambda: now[0])
    status.starting()
    status.running()
    return status, profile, policy, stream, now


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "未知"),
        (59.99, "不足 1 分钟"),
        (60, "1 分钟"),
        (8289, "2 小时 18 分钟"),
        (90061, "1 天 1 小时 1 分钟"),
        (86400, "1 天"),
    ],
)
def test_duration_truncates_seconds(value, expected):
    """省略零单位和秒，不把缺失起点当成零。"""
    assert format_duration(value) == expected


def test_status_is_local_read_only_and_does_not_reveal_rules():
    """仅在可信 profile 中读取最新规则，字面通配符计一条。"""
    status, profile, _policy, _stream, now = setup()
    now[0] += 8289
    result = asyncio.run(status.status())
    assert (
        result
        == "Milky · 运行状态\n\n插件: 运行中\n事件流: 已连接\n本次运行: 2 小时 18 分钟\n\n运行白名单: 2 条规则\n白名单配置与当前运行一致。"
    )
    assert profile.reads == 1
    assert "group:123" not in result and "dm:*" not in result


@pytest.mark.parametrize("rules", [("dm:456", "group:123"), ()])
def test_latest_config_comparison_uses_sets_not_counts(rules):
    """Web 保存尚未应用时显示当前运行条数及集合差异。"""
    status, profile, policy, _stream, _now = setup()
    profile.rules = rules
    result = asyncio.run(status.status())
    assert "运行白名单: 2 条规则" in result
    assert "白名单配置与当前运行不同。" in result
    assert "请重启 Gateway" in result
    assert policy.rules == {"dm:*", "group:123"}


@pytest.mark.parametrize("value", [None, "dm:*", ["temp:123"], RuntimeError("secret-url-path")])
def test_invalid_configuration_is_unknown_only(value):
    """配置故障保持可信本地信息，不能伪造一致或零。"""
    status, profile, _policy, _stream, _now = setup()
    profile.rules = value
    result = asyncio.run(status.status())
    assert "插件: 运行中" in result and "运行白名单: 2 条规则" in result
    assert "白名单配置一致性未知。" in result and "secret" not in result


def test_rule_change_is_unknown_but_lifecycle_change_invalidates_whole_snapshot():
    """区分规则版本竞争与 profile/实例代次失效。"""
    status, profile, policy, _stream, _now = setup()
    profile.hook = lambda: policy.publish({"dm:123"})
    assert "白名单配置一致性未知。" in asyncio.run(status.status())
    profile.hook = status.starting
    assert asyncio.run(status.status()) == UNAVAILABLE
    profile.hook = lambda: setattr(profile, "current", False)
    assert asyncio.run(status.status()) == UNAVAILABLE


def test_empty_rules_and_missing_observers_remain_distinct():
    """空规则阻止普通消息；缺少事件观察或规则观察明确未知。"""
    status, _profile, policy, stream, _now = setup(())
    del stream.connection_state
    result = asyncio.run(status.status())
    assert "事件流: 未知" in result
    assert "运行白名单: 0 条规则" in result
    assert "当前不接收任何会话的普通消息。" in result
    policy.rules = None
    result = asyncio.run(status.status())
    assert "运行白名单: 未知" in result and "0 条" not in result


def test_run_clock_survives_reconnect_and_freezes_on_stop(monkeypatch):
    """墙钟变化和 SSE 重连不改变本次单调计时，重启重置。"""
    status, _profile, _policy, stream, now = setup()
    monkeypatch.setattr("time.time", lambda: -999999999)
    now[0] += 125
    stream.connection_state = "reconnecting"
    result = asyncio.run(status.status())
    assert "事件流: 重连中" in result and "本次运行: 2 分钟" in result
    status.stop()
    frozen = status.elapsed
    now[0] += 300
    assert status.elapsed == frozen == 125
    assert asyncio.run(status.status()) == UNAVAILABLE
    status.starting()
    assert "本次运行: 尚未开始" in asyncio.run(status.status())
    status.running()
    assert "本次运行: 不足 1 分钟" in asyncio.run(status.status())


def test_untrusted_profile_never_reads_configuration():
    """不能从客户端、环境或缺少身份能力的存储猜测 profile。"""
    status, profile, _policy, _stream, _now = setup()
    profile.current = False
    assert asyncio.run(status.status()) == UNAVAILABLE
    assert profile.reads == 0
    status.profile = SimpleNamespace(read=lambda: pytest.fail("不应读取"))
    assert asyncio.run(status.status()) == UNAVAILABLE


def test_slash_runtime_binding_and_extra_arguments():
    """未知、多实例、额外参数及读期间解绑均不报告可信摘要。"""

    async def scenario():
        service = SlashCommandService()
        status, profile, *_ = setup()
        assert (await service.handle("status")).startswith("运行状态暂不可用")
        service.bind_status_provider(status)
        assert "插件: 运行中" in await service.handle("STATUS")
        reads = profile.reads
        assert (await service.handle("status --refresh")).startswith("指令格式不正确")
        assert profile.reads == reads
        second, *_ = setup()
        service.bind_status_provider(second)
        assert (await service.handle("status")).startswith("运行状态暂不可用")
        service.unbind_status_provider(second)
        profile.hook = lambda: service.unbind_status_provider(status)
        assert (await service.handle("status")).startswith("运行状态暂不可用")

    asyncio.run(scenario())


def test_stream_observes_first_connection_failure_retry_and_stop():
    """首次连接失败进入重连，只有实际连接成功后显示已连接。"""

    async def scenario():
        release = asyncio.Event()
        connecting = asyncio.Event()
        sleeping = asyncio.Event()
        response = BlockingResponse([])

        class Transport(FakeTransport):
            async def connect(self, *args):
                connecting.set()
                await release.wait()
                return await super().connect(*args)

        async def sleep(_delay):
            sleeping.set()
            await release.wait()

        transport = Transport([OSError("secret"), response])
        stream = SseEventStream(CONFIG, transport, sleep=sleep)
        assert stream.connection_state == "stopped"
        task = asyncio.create_task(stream.run(lambda event: None))
        await connecting.wait()
        assert stream.connection_state == "connecting"
        release.set()
        await sleeping.wait()
        assert stream.connection_state == "reconnecting"
        await response.read_started.wait()
        assert stream.connection_state == "connected"
        await stream.close()
        assert stream.connection_state == "stopped"
        await task
        assert stream.connection_state == "stopped"

    asyncio.run(scenario())


def test_adapter_binds_starting_then_running_and_restarts_timer():
    """adapter 生命周期驱动观察者，未知 SSE 能力不伪造已连接。"""
    from adapter import MilkyAdapter
    from tests.test_adapter_lifecycle import (
        FakeClient,
        FakeEventStream,
        FakeMuteTracker,
        FakePipeline,
        FakeSender,
        make_config,
    )

    async def scenario():
        now = [50.0]
        profile = Profile(())
        service = SlashCommandService()
        release = asyncio.Event()

        class Tracker(FakeMuteTracker):
            async def initialize(self):
                self.initialize_started.set()
                await release.wait()
                return await super().initialize()

        tracker, stream = Tracker(), FakeEventStream()
        adapter = MilkyAdapter(
            SimpleNamespace(),
            milky_config=make_config(),
            client=FakeClient(),
            event_stream=stream,
            mute_tracker=tracker,
            pipeline=FakePipeline(),
            outbound_sender=FakeSender(),
            slash_command_service=service,
            profile_settings=profile,
            status_clock=lambda: now[0],
        )
        task = asyncio.create_task(adapter.connect())
        await tracker.initialize_started.wait()
        starting = await service.handle("status")
        assert "插件: 启动中" in starting and "本次运行: 尚未开始" in starting
        assert "事件流: 未知" in starting
        release.set()
        assert await task
        await stream.started.wait()
        now[0] += 125
        result = await service.handle("status")
        assert "插件: 运行中" in result and "本次运行: 2 分钟" in result
        assert "事件流: 未知" in result
        await adapter.disconnect()
        assert (await service.handle("status")).startswith("运行状态暂不可用")
        now[0] += 600
        assert adapter._runtime_status.elapsed == 125
        stream.stopped.clear()
        assert await adapter.connect()
        assert "本次运行: 不足 1 分钟" in await service.handle("status")
        await adapter.disconnect()

    asyncio.run(scenario())


def test_adapter_initialization_failure_invalidates_observer():
    """初始化失败不能留下可用于生成状态的运行实例。"""
    from tests.test_adapter_lifecycle import FakeMuteTracker, make_adapter

    async def scenario():
        service = SlashCommandService()
        adapter, *_ = make_adapter(
            tracker=FakeMuteTracker(fail=True), slash_command_service=service
        )
        assert not await adapter.connect()
        assert adapter._runtime_status.phase == "failed"
        assert adapter._runtime_status.started_at is None
        assert (await service.handle("status")).startswith("运行状态暂不可用")
        await adapter.disconnect()

    asyncio.run(scenario())


def test_adapter_status_before_sse_task_is_scheduled_is_connecting():
    """connect 返回后的同步查询不能把尚未调度的首次连接显示为停止。"""
    from adapter import MilkyAdapter
    from tests.test_adapter_lifecycle import (
        FakeClient,
        FakeMuteTracker,
        FakePipeline,
        FakeSender,
        make_config,
    )

    async def scenario():
        service = SlashCommandService()
        stream = SseEventStream(CONFIG, FakeTransport([BlockingResponse([])]))
        adapter = MilkyAdapter(
            SimpleNamespace(),
            milky_config=make_config(),
            client=FakeClient(),
            event_stream=stream,
            mute_tracker=FakeMuteTracker(),
            pipeline=FakePipeline(),
            outbound_sender=FakeSender(),
            slash_command_service=service,
            profile_settings=Profile(()),
        )
        assert await adapter.connect()
        assert "事件流: 连接中" in await service.handle("status")
        await adapter.disconnect()

    asyncio.run(scenario())
