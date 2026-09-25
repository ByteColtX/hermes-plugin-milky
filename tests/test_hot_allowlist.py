"""验证规则操作、提交边界、调用关联及群状态交错。"""

import asyncio
from contextvars import ContextVar
from types import SimpleNamespace

import pytest

from gates import GateRegistry
from management.allowlist import HELP, AllowlistManager, parse
from management.errors import ManagementError
from slash_commands import SlashCommandService
from state.chat_policy import ChatPolicy
from state.mute_tracker import MuteTracker
from tests.test_mute_tracker import FakeMuteClient

PLATFORM = ContextVar("HERMES_SESSION_PLATFORM")
CHAT = ContextVar("HERMES_SESSION_CHAT_ID")


class Store:
    """模拟有版本和单键核验的持久设置。"""

    def __init__(self, rules=()):
        self.rules = frozenset(rules)
        self.version = 0
        self.writes = []
        self.reads = 0
        self.writable = True
        self.result = "saved"
        self.after_save = lambda: None

    def read(self):
        """读取最新版本，不返回可修改的内部集合。"""
        self.reads += 1
        return {
            "effective": {"allowed_chats": sorted(self.rules)},
            "version": self.version,
            "sources": {"allowed_chats": "settings"},
            "writable": {"allowed_chats": self.writable},
        }

    def save(self, version, rules):
        """拒绝已知竞争，不重试。"""
        if version != self.version:
            raise ManagementError("conflict")
        self.writes.append(rules)
        if self.result == "saved":
            self.rules = frozenset(rules)
            self.version += 1
        self.after_save()
        return {"results": {"allowed_chats": self.result}}


class Tracker:
    """记录仅允许管理执行后出现的来源和目标准备。"""

    def __init__(self):
        self.calls = []
        self.muted = False
        self.prepare_ok = True
        self.prepare_hook = None

    async def prepare_group(self, group_id):
        """准备单群。"""
        self.calls.append(group_id)
        return self.prepare_ok

    def gate_snapshot(self, _group_id):
        """返回可控的来源状态。"""
        return ("muted" if self.muted else "unmuted", "unknown")

    def is_muted(self, _group_id):
        """返回目标确认禁言。"""
        return self.muted

    async def prepare_rules(self, rules):
        """提供保存前异步竞争窗口。"""
        self.calls.append(rules)
        if self.prepare_hook:
            await self.prepare_hook()
        return self.prepare_ok


def setup(rules=()):
    """组装无网络管理实例。"""
    policy, tracker, store = ChatPolicy(rules), Tracker(), Store(rules)
    manager = AllowlistManager(policy, store, policy.publish)
    manager.start()
    return manager, policy, tracker, store


async def invoke(manager, args, source="dm:123"):
    """模拟 core 分发时已绑定的任务上下文。"""
    platform_token, chat_token = PLATFORM.set("milky"), CHAT.set(source)
    try:
        return await manager.handle(parse(args), manager.invocation(source))
    finally:
        PLATFORM.reset(platform_token)
        CHAT.reset(chat_token)


@pytest.mark.parametrize(
    "raw",
    [
        "allowlist help extra",
        "allowlist help dm:123",
        "allowlist add 123",
        "allowlist add temp:123",
        "allowlist add dm:**",
        "allowlist del dm:1 dm:2",
        "allowlist list dm:1",
        "allowlist list --page 1",
        "allowlist list --page 2",
        "allowlist list --page 0",
        "allowlist list --page -1",
        "allowlist other",
    ],
)
def test_invalid_syntax_has_no_service_effects(raw):
    """畸形参数在服务选择前拒绝。"""
    manager, _policy, tracker, store = setup()
    service = SlashCommandService()
    service.bind_manager(manager)
    result = asyncio.run(service.handle(raw))
    assert result.startswith("指令格式不正确")
    assert store.reads == 0 and not store.writes and not tracker.calls


@pytest.mark.parametrize("verb", ["del", "remove"])
@pytest.mark.parametrize("source", ["dm:123", "group:123"])
@pytest.mark.parametrize("target", [None, "dm:456", "group:*", "dm:*"])
def test_delete_aliases_are_single_literal_operations(verb, source, target):
    """主指令和别名对省略、具体和通配符目标只删除一次。"""
    rule = target or source
    manager, policy, _tracker, store = setup({rule, "group:456"})
    result = asyncio.run(
        invoke(manager, f"allowlist {verb}" + (f" {target}" if target else ""), source)
    )
    assert result.endswith("更改已保存并生效。")
    assert len(store.writes) == 1
    assert policy.rules == store.rules == {"group:456"}
    assert "会话已关闭" not in result
    assert asyncio.run(invoke(manager, f"allowlist {verb} {rule}", source)).startswith("规则不存在")
    assert len(store.writes) == 1


def test_literal_add_and_wildcard_revoke_generation():
    """通配符和具体条目独立，只有实际缩小授权才撤销旧批次。"""

    async def scenario():
        manager, policy, _tracker, store = setup({"dm:*"})
        generation = policy.generation("dm:123")
        assert (await invoke(manager, "allowlist add")).endswith("更改已保存并生效。")
        assert store.rules == {"dm:*", "dm:123"}
        assert (await invoke(manager, "allowlist del dm:123")).endswith("更改已保存并生效。")
        assert policy.generation("dm:123") == generation
        assert (await invoke(manager, "allowlist del dm:*")).endswith("更改已保存并生效。")
        assert policy.generation("dm:123") == generation + 1
        await invoke(manager, "allowlist add")
        assert policy.generation("dm:123") == generation + 1
        assert not policy.allows("group:123")

    asyncio.run(scenario())


@pytest.mark.parametrize("verb", ["list", "add", "del", "remove"])
def test_management_does_not_query_group_state(verb):
    """来源禁言或状态不可用不阻止规则管理，也不触发群查询。"""
    manager, policy, tracker, store = setup({"group:123"} if verb in {"del", "remove"} else ())
    tracker.muted, tracker.prepare_ok = True, False
    response = asyncio.run(invoke(manager, f"allowlist {verb}", "group:123"))
    assert "白名单" in response and "禁言" not in response
    assert not tracker.calls
    assert store.reads == 1
    if verb != "list":
        assert len(store.writes) == 1 and policy.rules == store.rules


def test_missing_stale_and_environment_context_is_unsupported(monkeypatch):
    """环境变量不能替代可信调用；旧实例和重复调用均拒绝。"""

    async def scenario():
        manager, _policy, _tracker, store = setup()
        invocation = manager.invocation("dm:123")
        monkeypatch.setenv("HERMES_SESSION_PLATFORM", "milky")
        monkeypatch.setenv("HERMES_SESSION_CHAT_ID", "dm:123")
        assert (await manager.handle(parse("allowlist list"), invocation)).startswith(
            "白名单管理暂不可用"
        )
        a, b = PLATFORM.set("milky"), CHAT.set("dm:123")
        try:
            assert "白名单" in await manager.handle(parse("allowlist list"), invocation)
            assert (await manager.handle(parse("allowlist list"), invocation)).startswith(
                "白名单管理暂不可用"
            )
            old = manager.invocation("dm:123")
            manager.stop()
            manager.start()
            assert (await manager.handle(parse("allowlist add"), old)).startswith(
                "白名单管理暂不可用"
            )
        finally:
            PLATFORM.reset(a)
            CHAT.reset(b)
        assert not store.writes

    asyncio.run(scenario())


def test_multiple_instances_do_not_select_arbitrarily():
    """同一命令注册下多个实例不能猜测操作对象。"""
    service = SlashCommandService()
    first, *_ = setup()
    second, *_ = setup()
    service.bind_manager(first)
    service.bind_manager(second)
    assert asyncio.run(service.handle("allowlist list")).startswith("白名单管理暂不可用")


@pytest.mark.parametrize("result", ["blocked", "conflict", "unknown", "failed"])
def test_failed_save_never_publishes_or_retries(result):
    """未确认持久化时保持旧在线快照。"""
    manager, policy, _tracker, store = setup()
    store.result = result
    response = asyncio.run(invoke(manager, "allowlist add"))
    assert response.startswith("无法修改白名单" if result == "blocked" else "无法确认操作结果")
    assert not policy.rules and len(store.writes) == 1


def test_external_conflict_and_serial_commands():
    """并发命令读最新设置；准备期间 Web 修改产生 conflict。"""

    async def scenario():
        manager, policy, _tracker, store = setup()
        results = await asyncio.gather(
            invoke(manager, "allowlist add dm:1"), invoke(manager, "allowlist add dm:2")
        )
        assert all(result.endswith("更改已保存并生效。") for result in results)
        assert store.rules == policy.rules == {"dm:1", "dm:2"}

        save = store.save

        def conflict(version, rules):
            store.rules = frozenset({"dm:9"})
            store.version += 1
            return save(version, rules)

        store.save = conflict
        result = await invoke(manager, "allowlist add dm:3")
        assert result.startswith("更改未保存")
        assert policy.rules == {"dm:1", "dm:2"} and store.rules == {"dm:9"}
        assert len(store.writes) == 2

    asyncio.run(scenario())


def test_persisted_but_not_published_and_unchanged_does_not_reload():
    """已保存后停止或发布异常不回滚；重复操作不隐式同步。"""
    manager, policy, _tracker, store = setup()
    store.after_save = manager.stop
    assert asyncio.run(invoke(manager, "allowlist add")).startswith("更改已保存，尚未生效")
    assert store.rules == {"dm:123"} and not policy.rules
    manager.start()
    assert "请重启 Gateway" in asyncio.run(invoke(manager, "allowlist add"))
    assert len(store.writes) == 1 and not policy.rules
    store.after_save = lambda: None

    def fail(_rules):
        raise RuntimeError("synthetic")

    manager._publish = fail
    assert asyncio.run(invoke(manager, "allowlist add dm:456")).startswith("更改已保存，尚未生效")
    assert store.rules == {"dm:123", "dm:456"}


def test_complete_list_and_empty_rules():
    """完整输出所有规则，保留原始来源，区分配置与运行且不查询群状态。"""
    manager, policy, tracker, store = setup()
    empty = asyncio.run(invoke(manager, "allowlist list"))
    assert "当前不接收任何会话的普通消息。" in empty
    assert "Source: settings" in empty
    store.rules = frozenset(f"dm:{number}" for number in range(101))
    policy.publish({"group:123"})
    result = asyncio.run(invoke(manager, "allowlist list"))
    assert [line for line in result.splitlines() if line.startswith("dm:")] == sorted(store.rules)
    assert "当前配置" in result and "当前运行\ngroup:123" in result
    assert "请重启 Gateway" in result and not tracker.calls
    policy.publish(store.rules)
    result = asyncio.run(invoke(manager, "allowlist list"))
    assert "共 101 条规则" in result and "配置与当前运行一致。" in result
    assert len([line for line in result.splitlines() if line.startswith("dm:")]) == 101


def test_stop_during_lock_wait_cancels_owned_work():
    """关闭取消并等待排队修改，旧调用不能提交。"""

    async def scenario():
        manager, policy, _tracker, store = setup()
        await manager._lock.acquire()
        task = asyncio.create_task(invoke(manager, "allowlist add"))
        await asyncio.sleep(0)
        await manager.close()
        assert task.cancelled() and not store.writes and not policy.rules
        manager._lock.release()
        await manager.close()

    asyncio.run(scenario())


def test_empty_initial_scan_and_dynamic_event_during_prepare(caplog):
    """空名单零成员查询，动态准备保留查询期间新禁言。"""

    async def scenario():
        client = FakeMuteClient([700000001])
        tracker = MuteTracker(client, clock=lambda: 100, refresh_cooldown=0)
        await tracker.initialize()
        assert tracker.group_ids == () and not client.started_member_groups
        assert not await tracker.refresh_group(700000001)
        original = client.get_group_member_info

        async def query(*args, **kwargs):
            tracker.apply_event(
                {
                    "time": 100,
                    "self_id": 900000001,
                    "event_type": "group_mute",
                    "data": {
                        "group_id": 700000001,
                        "user_id": 900000001,
                        "duration": 60,
                        "operator_id": 800000001,
                    },
                }
            )
            return await original(*args, **kwargs)

        client.get_group_member_info = query
        assert await tracker.prepare_group(700000001)
        assert tracker.gate_snapshot(700000001)[0] == "muted"
        assert not await tracker.prepare_group(123)
        await tracker.close()

    asyncio.run(scenario())


def test_prepare_failure_and_cancellation_keep_group_closed():
    """首次准备失败后遵守冷却，取消不能提交候选或假装已准备。"""

    async def scenario():
        now = [100]
        client = FakeMuteClient([700000001], member_results={700000001: RuntimeError("synthetic")})
        tracker = MuteTracker(client, clock=lambda: now[0])
        await tracker.initialize()
        assert not await tracker.prepare_group(700000001)
        count = len(client.calls)
        assert not await tracker.prepare_group(700000001)
        assert len(client.calls) == count
        assert tracker.is_muted(700000001)
        client.member_results.clear()
        now[0] = 106
        assert await tracker.prepare_group(700000001)
        assert not tracker.is_muted(700000001)
        await tracker.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("readd", [False, True])
def test_revocation_during_resource_wait_drops_detached_batch(readd):
    """补全等待时撤销旧批次，重新添加也不能复活正文。"""
    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, load_fixture, make_pipeline

    async def scenario():
        hermes, resolver = FakeHermes(), FakeResolver()
        pipeline = make_pipeline(hermes, resolver)
        policy = ChatPolicy({"dm:*"})
        pipeline._chat_policy = policy
        pipeline._gates = GateRegistry(policy)
        started, release = asyncio.Event(), asyncio.Event()
        original = resolver.resolve_batch

        async def blocked(batch):
            started.set()
            await release.wait()
            return await original(batch)

        resolver.resolve_batch = blocked
        assert (
            await pipeline.handle_event(load_fixture("events/message_receive.friend.json"))
        ).classification == "trigger"
        await started.wait()
        pipeline.revoke(policy.publish([]))
        if readd:
            policy.publish(["dm:800000001"])
        release.set()
        await pipeline.wait_idle()
        assert not hermes.events
        assert "authorization_revoked" in pipeline.diagnostics
        await pipeline.close()

    asyncio.run(scenario())


def test_removing_covered_rule_keeps_pending_batch():
    """删除仍被通配符覆盖的条目不误撤销。"""
    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, load_fixture, make_pipeline

    async def scenario():
        hermes, resolver = FakeHermes(), FakeResolver()
        pipeline = make_pipeline(hermes, resolver)
        policy = ChatPolicy({"dm:*", "dm:800000001"})
        pipeline._chat_policy = policy
        pipeline._gates = GateRegistry(policy)
        await pipeline.handle_event(load_fixture("events/message_receive.friend.json"))
        pipeline.revoke(policy.publish({"dm:*"}))
        await pipeline.wait_idle()
        assert len(hermes.events) == 1
        pipeline.revoke(policy.publish([]))
        assert len(hermes.events) == 1
        await pipeline.close()

    asyncio.run(scenario())


def test_revoke_clears_wait_context_and_willingness():
    """清除等待正文、系统上下文及累计 Will，不复用旧轮次状态。"""
    from session.context import ContextOnlyEvent
    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, load_fixture, make_pipeline
    from will.willingness import WillingnessConfig, WillingnessWillEngine

    async def scenario():
        engine = WillingnessWillEngine(WillingnessConfig(probability_threshold=100))
        pipeline = make_pipeline(FakeHermes(), FakeResolver(), will_engine=engine)
        policy = ChatPolicy({"group:*"})
        pipeline._chat_policy = policy
        pipeline._gates = GateRegistry(policy)
        event = load_fixture("events/message_receive.group.all_segments.json")
        await pipeline.handle_event(event)
        chat = "group:700000001"
        policy.generation(chat)
        pipeline._system_context.append(ContextOnlyEvent(chat, "group_recall", "合成上下文"))
        pipeline.revoke(policy.publish([]))
        assert pipeline._buffer.size(chat) == 0
        assert pipeline._system_context.size(chat) == 0
        assert chat not in engine.states
        await pipeline.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("verb", ["", "help", "add", "del", "remove", "list"])
@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("scene", ["friend", "group"])
def test_management_route_reaches_core_without_resources(verb, allowed, scene):
    """白名单内外固定管理语法均交宿主，自身和普通命令仍拒绝。"""
    from tests.test_slash_commands import (
        FIXTURE_ROOT,
        FakeHermes,
        RecordingResolver,
        load_fixture,
        make_pipeline,
    )

    async def scenario():
        hermes, resolver = FakeHermes(), RecordingResolver()
        will = SimpleNamespace(decide=lambda _value: pytest.fail("management entered Will"))
        pipeline = make_pipeline(hermes, resolver, will)
        pipeline._gates = GateRegistry({"group:*", "dm:*"} if allowed else ())
        pipeline._mute_tracker = SimpleNamespace(
            gate_snapshot=lambda _: pytest.fail("management checked group state"),
            prepare_group=lambda _: pytest.fail("management queried group state"),
        )
        fixture = "friend_plain_text.json" if scene == "friend" else "group_plugin_milky.json"
        event = load_fixture(FIXTURE_ROOT / "events" / fixture)
        event["data"]["segments"] = [{"type": "text", "data": {"text": f"/milky allowlist {verb}"}}]
        result = await pipeline.handle_event(event)
        assert result.classification == "command"
        await pipeline.wait_idle()
        assert len(hermes.events) == 1
        assert (await pipeline.handle_event(event)).classification == "duplicate"
        await pipeline.close()

    asyncio.run(scenario())


def test_prepare_cancel_retains_events_but_not_send_permission():
    """准备取消即使收到解禁事件仍保持拒绝，重试受冷却保护。"""

    async def scenario():
        now = [100]
        client = FakeMuteClient([700000001], block_members=True)
        tracker = MuteTracker(client, clock=lambda: now[0])
        await tracker.initialize()
        task = asyncio.create_task(tracker.prepare_group(700000001))
        await client.all_members_started.wait()
        tracker.apply_event(
            {
                "time": 100,
                "self_id": 900000001,
                "event_type": "group_mute",
                "data": {
                    "group_id": 700000001,
                    "user_id": 900000001,
                    "duration": 0,
                    "operator_id": 800000001,
                },
            }
        )
        tracker.apply_event(
            {
                "time": 100,
                "self_id": 900000001,
                "event_type": "group_whole_mute",
                "data": {"group_id": 700000001, "is_mute": True, "operator_id": 800000001},
            }
        )
        assert not await tracker.prepare_group(700000001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert tracker.get_snapshot(700000001).whole_mute == "muted"
        assert tracker.gate_snapshot(700000001)[0] == "muted"
        assert not await tracker.prepare_group(700000001)
        now[0] = 106
        client.block_members = False
        assert await tracker.prepare_group(700000001)
        assert tracker.gate_snapshot(700000001) == ("unmuted", "muted")
        await tracker.close()

    asyncio.run(scenario())


def test_wildcard_edit_does_not_prepare_members():
    """规则修改无需目标状态，群通配符与具体条目独立保存。"""

    async def scenario():
        client = FakeMuteClient([700000001, 700000002], block_members=True)
        tracker = MuteTracker(client)
        await tracker.initialize()
        store, policy = Store(), ChatPolicy()
        manager = AllowlistManager(policy, store, policy.publish)
        manager.start()
        for args in ["add group:700000002", "add group:*", "del group:*"]:
            assert (await invoke(manager, "allowlist " + args)).endswith("更改已保存并生效。")
        assert store.rules == policy.rules == {"group:700000002"}
        assert not client.all_members_started.is_set()
        assert tracker.gate_snapshot(700000002)[0] == "muted"
        await manager.close()
        await tracker.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "outcome", ["ready", "failed", "muted", "revoked", "readded", "denied", "self"]
)
def test_new_group_prepares_only_on_allowed_inbound(outcome):
    """热添加后首次入站准备状态；拒绝、自身及撤销消息不能进入 Will 或宿主。"""
    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, load_fixture, make_pipeline
    from tests.test_mute_tracker import member

    async def scenario():
        client = FakeMuteClient([700000001])
        release = asyncio.Event()
        original_query = client.get_group_member_info

        async def blocked_query(*args, **kwargs):
            client.all_members_started.set()
            await release.wait()
            return await original_query(*args, **kwargs)

        if outcome in {"revoked", "readded"}:
            client.get_group_member_info = blocked_query
        if outcome == "failed":
            client.member_results[700000001] = RuntimeError("synthetic")
        elif outcome == "muted":
            client.member_results[700000001] = member(700000001, shut_up_end_time=200)
        tracker = MuteTracker(client, clock=lambda: 100)
        await tracker.initialize()
        hermes, resolver = FakeHermes(), FakeResolver()
        pipeline = make_pipeline(hermes, resolver)
        policy = ChatPolicy() if outcome == "denied" else ChatPolicy({"group:*"})
        pipeline._chat_policy, pipeline._gates = policy, GateRegistry(policy)
        pipeline._mute_tracker = tracker
        event = load_fixture("events/message_receive.group.all_segments.json")
        if outcome == "self":
            event["data"]["sender_id"] = pipeline._self_id
            event["data"]["group_member"]["user_id"] = pipeline._self_id
        task = asyncio.create_task(pipeline.handle_event(event))
        if outcome in {"revoked", "readded"}:
            await client.all_members_started.wait()
            pipeline.revoke(policy.publish([]))
            if outcome == "readded":
                policy.publish({"group:*"})
            release.set()
        result = await task
        await pipeline.wait_idle()
        if outcome == "ready":
            assert result.classification == "trigger"
            assert len(hermes.events) == 1
        else:
            assert result.classification == "denied"
            assert not hermes.events and pipeline.reply_costs == 0
        if outcome in {"self", "denied"}:
            assert not client.all_members_started.is_set()
        await pipeline.close()
        await tracker.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("threshold", [0, 100])
def test_complete_list_uses_existing_long_message_delivery(threshold):
    """完整名单经普通分块或合并转发发送，所有规则保持顺序且不截断。"""
    from outbound.sender import MilkyOutboundSender
    from tests.test_long_text_forwarding import ForwardClient, _forward_body, _text_content

    async def scenario():
        manager, _policy, _tracker, _store = setup({f"dm:{n}" for n in range(200)})
        text = await invoke(manager, "allowlist list")
        client = ForwardClient()
        sender = MilkyOutboundSender(
            client,
            max_text_length=100,
            long_text_forward_threshold=threshold,
            identity_loader=client.get_login_info,
        )
        result = await sender.send("dm:800000001", text)
        assert result.success
        if threshold:
            delivered = _text_content(_forward_body(client)["messages"])
        else:
            assert len(client.calls) > 1
            delivered = "".join(
                segment["data"]["text"]
                for _, body in client.calls
                for segment in body["message"]
                if segment["type"] == "text"
            )
        assert delivered == text

    asyncio.run(scenario())


@pytest.mark.parametrize("raw", ["allowlist", "allowlist help", "ALLOWLIST HELP"])
@pytest.mark.parametrize("manager_count", [0, 1, 2])
def test_help_does_not_require_runtime_or_read_settings(raw, manager_count):
    """帮助在 core 分发后独立返回，不依赖实例归属或触发管理副作用。"""
    service = SlashCommandService()
    managers = [setup() for _ in range(manager_count)]
    for manager, *_ in managers:
        service.bind_manager(manager)
    assert asyncio.run(service.handle(raw)) == HELP
    for manager, policy, tracker, store in managers:
        assert not store.reads and not store.writes and not tracker.calls
        assert not policy.rules
        assert asyncio.run(manager.handle(parse(raw), None)) == HELP
        assert not store.reads and not store.writes
