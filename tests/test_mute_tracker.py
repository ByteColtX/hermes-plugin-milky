"""验证 Milky Bot 群禁言状态的同步、事件更新和刷新边界。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import pytest

from milky.client import ActionError
from milky.models import (
    GroupEntity,
    GroupList,
    GroupMemberEntity,
    GroupMemberInfo,
    LoginInfo,
)
from outbound.sender import MilkyOutboundSender
from state import MuteTracker


def member(
    group_id: int,
    *,
    user_id: int = 900000001,
    shut_up_end_time: int | None = None,
) -> GroupMemberInfo:
    """构造最小的 Milky 成员查询结果。"""

    return GroupMemberInfo(
        GroupMemberEntity(
            user_id=user_id,
            group_id=group_id,
            nickname="合成机器人",
            shut_up_end_time=shut_up_end_time,
        )
    )


@dataclass
class FakeMuteClient:
    """记录状态同步请求并提供可控的 fake 结果。"""

    group_ids: list[int]
    member_results: dict[int, GroupMemberInfo | BaseException] = field(default_factory=dict)
    calls: list[tuple[str, int | None, int | None]] = field(default_factory=list)
    member_no_cache: list[bool] = field(default_factory=list)
    delay: float = 0

    def __post_init__(self) -> None:
        self.login = LoginInfo(900000001, "合成机器人")
        self.inflight = 0
        self.max_inflight = 0
        self.send_calls: list[tuple[str, int]] = []

    async def get_login_info(self) -> LoginInfo:
        """返回合成登录身份。"""

        self.calls.append(("login", None, None))
        return self.login

    async def get_group_list(self) -> GroupList:
        """返回当前群列表。"""

        self.calls.append(("groups", None, None))
        return GroupList(tuple(GroupEntity(group_id=group_id) for group_id in self.group_ids))

    async def get_group_member_info(
        self, group_id: int, user_id: int, *, no_cache: bool = False
    ) -> GroupMemberInfo:
        """返回成员状态或安全的 fake Action 错误。"""

        self.calls.append(("member", group_id, user_id))
        self.member_no_cache.append(no_cache)
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            result = self.member_results.get(group_id, member(group_id))
            if isinstance(result, BaseException):
                raise result
            return result
        finally:
            self.inflight -= 1

    async def send_group_message(self, group_id: int, message: list[dict[str, object]]) -> object:
        """模拟已进入网络边界但结果未知的群发送。"""

        del message
        self.send_calls.append(("group", group_id))
        raise ActionError("transport_unknown", "send_group_message", "synthetic detail")

    async def send_private_message(self, user_id: int, message: list[dict[str, object]]) -> object:
        """模拟已进入网络边界但结果未知的私聊发送。"""

        del message
        self.send_calls.append(("dm", user_id))
        raise ActionError("transport_unknown", "send_private_message", "synthetic detail")


def test_tracker_fails_closed_before_ordered_initial_sync() -> None:
    """未完成登录、群列表和成员扫描前不得放行群状态。"""

    client = FakeMuteClient([700000001, 700000002])
    tracker = MuteTracker(client, clock=lambda: 100)

    assert tracker.initialized is False
    assert tracker.is_muted(700000001) is True

    asyncio.run(tracker.initialize())

    assert tracker.initialized is True
    assert client.calls == [
        ("login", None, None),
        ("groups", None, None),
        ("member", 700000001, 900000001),
        ("member", 700000002, 900000001),
    ]
    assert client.member_no_cache == [True, True]
    assert tracker.get_snapshot(700000001).member_mute == "unmuted"
    assert tracker.get_snapshot(700000002).member_mute == "unmuted"
    assert tracker.get_snapshot(700000001).whole_mute == "unknown"
    assert tracker.is_muted(700000001) is False


def test_tracker_treats_null_and_omitted_mute_end_as_unmuted() -> None:
    """成功响应的 null 或省略字段都表示当前没有成员禁言。"""

    client = FakeMuteClient(
        [700000001, 700000002],
        member_results={700000001: member(700000001), 700000002: member(700000002)},
    )
    tracker = MuteTracker(client, clock=lambda: 100)

    asyncio.run(tracker.initialize())

    assert all(
        tracker.get_snapshot(group_id).member_mute == "unmuted" for group_id in client.group_ids
    )


def test_tracker_expires_member_mute_from_end_time_without_remote_refresh() -> None:
    """个人禁言 TTL 到期后应本地转为 unmuted，不依赖下一次 Action。"""

    current_time = 100
    client = FakeMuteClient(
        [700000001],
        member_results={700000001: member(700000001, shut_up_end_time=130)},
    )
    tracker = MuteTracker(client, clock=lambda: current_time)
    asyncio.run(tracker.initialize())

    assert tracker.get_snapshot(700000001).member_mute == "muted"
    member_calls_before = len([call for call in client.calls if call[0] == "member"])

    current_time = 130
    expired = tracker.get_snapshot(700000001)

    assert expired.member_mute == "unmuted"
    assert expired.member_mute_until is None
    assert tracker.is_muted(700000001) is False
    assert len([call for call in client.calls if call[0] == "member"]) == member_calls_before


def test_tracker_expiry_task_updates_state_and_closes_cleanly() -> None:
    """TTL 任务应在截止时间后更新状态，并可被生命周期安全取消。"""

    current_time = 100
    client = FakeMuteClient([700000001])
    tracker = MuteTracker(client, clock=lambda: current_time)

    async def scenario() -> None:
        nonlocal current_time
        await tracker.initialize()
        tracker.apply_event(
            {
                "event_type": "group_mute",
                "time": 100,
                "self_id": 900000001,
                "data": {
                    "group_id": 700000001,
                    "user_id": 900000001,
                    "duration": 1,
                },
            }
        )
        tracker.start()
        current_time = 101
        await asyncio.sleep(0.01)

        assert tracker._snapshots[700000001].member_mute == "unmuted"
        await tracker.close()
        assert tracker._expiry_task is None

    asyncio.run(scenario())


def test_tracker_scans_only_group_allowlist_and_logs_raw_identity_and_results(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """冷启动日志应显示身份和白名单群结果。"""

    client = FakeMuteClient([700000001, 700000002])
    tracker = MuteTracker(
        client,
        allowed_chats={"group:700000001", "dm:800000001"},
        clock=lambda: 100,
    )

    with caplog.at_level(logging.INFO, logger="state.mute_tracker"):
        asyncio.run(tracker.initialize())

    member_calls = [call for call in client.calls if call[0] == "member"]
    assert member_calls == [("member", 700000001, 900000001)]
    assert client.member_no_cache == [True]
    assert tracker.group_ids == (700000001,)
    assert "[Milky] Cold-start identity" in caplog.text
    assert "冷启动" not in caplog.text
    assert "群禁言" not in caplog.text
    assert "Milky muted group" not in caplog.text
    assert "900000001" in caplog.text
    assert "700000002" not in caplog.text
    records = [
        record
        for record in caplog.records
        if record.name == "state.mute_tracker" and hasattr(record, "event_name")
    ]
    identity = next(
        record for record in records if record.event_name == "milky_mute_initial_sync_started"
    )
    summary = next(
        record for record in records if record.event_name == "milky_mute_initial_sync_succeeded"
    )
    assert identity.uid == 900000001
    assert identity.nickname == "合成机器人"
    assert identity.getMessage().count("uid=900000001") == 1
    assert identity.getMessage().count("nickname=合成机器人") == 1
    assert summary.scope == "allowlist"
    assert (summary.total, summary.succeeded, summary.failed) == (1, 1, 0)
    assert (summary.muted, summary.unmuted, summary.unknown) == (0, 0, 1)
    assert summary.getMessage().count("scope=allowlist") == 1
    assert summary.getMessage().count("total=1") == 1


def test_tracker_logs_only_muted_groups_and_summarizes_all_states(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """逐群日志只显示禁言群，汇总应区分所有成功状态。"""

    client = FakeMuteClient(
        [700000001, 700000002, 700000003],
        member_results={700000001: member(700000001, shut_up_end_time=200)},
    )
    tracker = MuteTracker(client, clock=lambda: 100)

    with caplog.at_level(logging.INFO, logger="state.mute_tracker"):
        asyncio.run(tracker.initialize())

    records = [
        record
        for record in caplog.records
        if record.name == "state.mute_tracker" and hasattr(record, "event_name")
    ]
    muted_records = [record for record in records if record.event_name == "milky_mute_group_muted"]
    assert len(muted_records) == 1
    assert muted_records[0].group_id == 700000001
    assert muted_records[0].member_mute == "muted"
    assert muted_records[0].whole_mute == "unknown"
    assert muted_records[0].getMessage().count("group_id=700000001") == 1
    assert muted_records[0].getMessage().count("member_mute=muted") == 1
    assert muted_records[0].getMessage().count("whole_mute=unknown") == 1
    summary = next(
        record for record in records if record.event_name == "milky_mute_initial_sync_succeeded"
    )
    assert summary.scope == "all_groups"
    assert (summary.total, summary.succeeded, summary.failed) == (3, 3, 0)
    assert (summary.muted, summary.unmuted, summary.unknown) == (1, 0, 2)
    assert summary.getMessage().count("scope=all_groups") == 1
    assert summary.getMessage().count("total=3") == 1


def test_tracker_initial_failure_keeps_not_ready_and_muted() -> None:
    """必要查询失败时保持未就绪，失败群不得被解释为 unmuted。"""

    client = FakeMuteClient(
        [700000001, 700000002],
        member_results={700000002: ActionError("rejected", "member", "denied")},
    )
    tracker = MuteTracker(client, clock=lambda: 100)

    with pytest.raises(Exception, match="initial mute sync failed"):
        asyncio.run(tracker.initialize())

    assert tracker.initialized is False
    assert tracker.get_snapshot(700000001).member_mute == "unmuted"
    assert tracker.is_muted(700000001) is True
    assert tracker.gate_snapshot(700000001) == ("muted", "muted")
    assert tracker.is_muted(700000002) is True


def test_tracker_refresh_failure_preserves_existing_two_state_values() -> None:
    """刷新失败只能保留原状态，不能清空或改成 unmuted。"""

    client = FakeMuteClient(
        [700000001], member_results={700000001: member(700000001, shut_up_end_time=200)}
    )
    current_time = 100
    tracker = MuteTracker(client, clock=lambda: current_time, refresh_cooldown=0)
    asyncio.run(tracker.initialize())
    tracker.apply_event(
        {
            "event_type": "group_whole_mute",
            "time": 100,
            "self_id": 900000001,
            "data": {"group_id": 700000001, "is_mute": False},
        }
    )
    before = tracker.get_snapshot(700000001)
    client.member_results[700000001] = ActionError("transport_unknown", "member", "failed")

    assert asyncio.run(tracker.refresh_group(700000001)) is False
    after = tracker.get_snapshot(700000001)

    assert after.member_mute == before.member_mute == "muted"
    assert after.whole_mute == before.whole_mute == "unmuted"
    assert client.member_no_cache == [True, True]


def test_tracker_full_sync_cleans_groups_missing_from_new_list() -> None:
    """全量群列表变化时应清理已经离开的群。"""

    client = FakeMuteClient([700000001, 700000002])
    tracker = MuteTracker(client, clock=lambda: 100)
    asyncio.run(tracker.initialize())
    client.group_ids[:] = [700000002, 700000003]

    asyncio.run(tracker.initialize())

    assert tracker.group_ids == (700000002, 700000003)
    assert tracker.get_snapshot(700000001).member_mute == "muted"


def test_tracker_applies_mute_events_using_milky_duration_and_is_mute() -> None:
    """成员 duration=0 应解除禁言，全体状态应直接使用 is_mute。"""

    client = FakeMuteClient([700000001])
    tracker = MuteTracker(client, clock=lambda: 100)
    asyncio.run(tracker.initialize())

    tracker.apply_event(
        {
            "event_type": "group_mute",
            "time": 100,
            "self_id": 900000001,
            "data": {
                "group_id": 700000001,
                "user_id": 900000001,
                "duration": 30,
            },
        }
    )
    active = tracker.get_snapshot(700000001)
    assert active.member_mute == "muted"
    assert active.member_mute_until == 130

    tracker.apply_event(
        {
            "event_type": "group_mute",
            "time": 131,
            "self_id": 900000001,
            "data": {
                "group_id": 700000001,
                "user_id": 900000001,
                "duration": 0,
            },
        }
    )
    tracker.apply_event(
        {
            "event_type": "group_whole_mute",
            "time": 132,
            "self_id": 900000001,
            "data": {"group_id": 700000001, "is_mute": True},
        }
    )
    muted = tracker.get_snapshot(700000001)
    assert muted.member_mute == "unmuted"
    assert muted.whole_mute == "muted"

    tracker.apply_event(
        {
            "event_type": "group_whole_mute",
            "time": 133,
            "self_id": 900000001,
            "data": {"group_id": 700000001, "is_mute": False},
        }
    )
    assert tracker.is_muted(700000001) is False


def test_tracker_limits_same_group_refresh_and_never_refreshes_dm() -> None:
    """同群刷新受锁和冷却合并，私聊失败不访问成员 Action。"""

    now = 100
    client = FakeMuteClient([700000001], delay=0.01)
    tracker = MuteTracker(
        client,
        clock=lambda: now,
        refresh_cooldown=0,
        max_concurrent_refreshes=1,
    )
    asyncio.run(tracker.initialize())
    member_calls_before = len([call for call in client.calls if call[0] == "member"])
    client.member_results[700000001] = member(700000001, shut_up_end_time=200)

    async def refreshes() -> list[bool]:
        """并发发起同群刷新和一个私聊失败通知。"""

        results = await asyncio.gather(
            tracker.refresh_group(700000001),
            tracker.refresh_group(700000001),
            tracker.refresh_after_send_failure("dm:800000001"),
        )
        return results

    results = asyncio.run(refreshes())

    assert results.count(True) == 1
    assert results.count(False) == 2
    member_calls_after = len([call for call in client.calls if call[0] == "member"])
    assert member_calls_after == member_calls_before + 1
    assert client.member_no_cache[-1] is True


def test_sender_concurrent_failures_use_one_refresh_and_keep_dm_isolated() -> None:
    """并发群发送失败只触发一次刷新，私聊未知结果不扫描群成员。"""

    now = 100
    client = FakeMuteClient([700000001], delay=0.01)
    tracker = MuteTracker(
        client,
        clock=lambda: now,
        refresh_cooldown=0,
        max_concurrent_refreshes=1,
    )
    asyncio.run(tracker.initialize())
    initial_member_calls = len([call for call in client.calls if call[0] == "member"])
    sender = MilkyOutboundSender(client, mute_tracker=tracker)

    async def scenario() -> None:
        results = await asyncio.gather(
            *(sender.send("group:700000001", f"失败 {index}") for index in range(20))
        )
        assert all(result.error_kind == "transport_unknown" for result in results)
        for _ in range(100):
            member_calls = len([call for call in client.calls if call[0] == "member"])
            if member_calls >= initial_member_calls + 1:
                break
            await asyncio.sleep(0.001)
        await sender.close()

    asyncio.run(scenario())

    member_calls = len([call for call in client.calls if call[0] == "member"])
    assert member_calls == initial_member_calls + 1
    assert client.member_no_cache[-1] is True
    assert len(client.send_calls) == 20

    before_dm = member_calls
    dm_sender = MilkyOutboundSender(client, mute_tracker=tracker)
    dm_result = asyncio.run(dm_sender.send("dm:800000001", "私聊失败"))
    asyncio.run(dm_sender.close())
    assert dm_result.error_kind == "transport_unknown"
    assert len([call for call in client.calls if call[0] == "member"]) == before_dm


def test_tracker_refreshes_different_groups_with_global_limit() -> None:
    """不同群允许并行刷新，但不超过全局并发上限。"""

    now = 100
    client = FakeMuteClient([700000001, 700000002, 700000003], delay=0.01)
    tracker = MuteTracker(
        client,
        clock=lambda: now,
        refresh_cooldown=0,
        max_concurrent_refreshes=2,
    )
    asyncio.run(tracker.initialize())
    now = 200

    async def refreshes() -> list[bool]:
        """并行刷新三个群。"""

        return await asyncio.gather(
            tracker.refresh_group(700000001),
            tracker.refresh_group(700000002),
            tracker.refresh_group(700000003),
        )

    assert asyncio.run(refreshes()) == [True, True, True]
    assert client.max_inflight <= 2
