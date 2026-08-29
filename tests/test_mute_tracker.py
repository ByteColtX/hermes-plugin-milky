"""验证 Milky Bot 群禁言状态的同步、事件更新和刷新边界。"""

from __future__ import annotations

import asyncio
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
    delay: float = 0

    def __post_init__(self) -> None:
        self.login = LoginInfo(900000001, "合成机器人")
        self.inflight = 0
        self.max_inflight = 0

    async def get_login_info(self) -> LoginInfo:
        """返回合成登录身份。"""

        self.calls.append(("login", None, None))
        return self.login

    async def get_group_list(self) -> GroupList:
        """返回当前群列表。"""

        self.calls.append(("groups", None, None))
        return GroupList(tuple(GroupEntity(group_id=group_id) for group_id in self.group_ids))

    async def get_group_member_info(self, group_id: int, user_id: int) -> GroupMemberInfo:
        """返回成员状态或安全的 fake Action 错误。"""

        self.calls.append(("member", group_id, user_id))
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
    assert tracker.get_snapshot(700000001).member_mute == "unmuted"
    assert tracker.get_snapshot(700000002).member_mute == "unmuted"
    assert tracker.get_snapshot(700000001).whole_mute == "muted"


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
