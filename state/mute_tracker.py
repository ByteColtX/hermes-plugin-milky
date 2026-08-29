"""维护 Milky Bot 自身的群禁言二态快照。"""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol, runtime_checkable

from milky.models import Event, GroupList, GroupMemberInfo, LoginInfo
from milky.parser import ParseError, parse_event
from session.identity import normalize_chat_key

MuteState = Literal["muted", "unmuted"]


@runtime_checkable
class MuteSyncClient(Protocol):
    """定义 tracker 所需的 Milky 状态 Action。"""

    async def get_login_info(self) -> LoginInfo:
        """读取 Bot 登录身份。"""

    async def get_group_list(self) -> GroupList:
        """读取 Bot 当前群列表。"""

    async def get_group_member_info(self, group_id: int, user_id: int) -> GroupMemberInfo:
        """读取 Bot 在指定群的成员信息。"""


@dataclass(frozen=True, slots=True)
class MuteSnapshot:
    """保存一个群的成员、全体禁言和观测时间。"""

    group_id: int
    member_mute: MuteState = "muted"
    whole_mute: MuteState = "muted"
    member_mute_until: int | None = None
    observed_at: float | None = None
    refreshed_at: float | None = None

    @property
    def member_muted(self) -> bool:
        """返回成员禁言布尔视图。"""

        return self.member_mute == "muted"

    @property
    def whole_muted(self) -> bool:
        """返回全体禁言布尔视图。"""

        return self.whole_mute == "muted"


class MuteSyncError(RuntimeError):
    """表示必要的初始群状态没有全部成功维护。"""

    classification = "state_sync_failed"


Clock = Callable[[], float]


class MuteTracker:
    """以 fail-closed 方式维护 Bot 群禁言状态并限制主动刷新。"""

    def __init__(
        self,
        client: MuteSyncClient,
        *,
        clock: Clock | None = None,
        refresh_cooldown: float = 5.0,
        max_concurrent_refreshes: int = 2,
    ) -> None:
        """创建 tracker；所有状态仅保存在进程内。"""

        if (
            not isinstance(refresh_cooldown, (int, float))
            or isinstance(refresh_cooldown, bool)
            or refresh_cooldown < 0
        ):
            raise ValueError("refresh_cooldown must be a non-negative number")
        if (
            isinstance(max_concurrent_refreshes, bool)
            or not isinstance(max_concurrent_refreshes, int)
            or max_concurrent_refreshes <= 0
        ):
            raise ValueError("max_concurrent_refreshes must be a positive integer")
        if not isinstance(client, MuteSyncClient):
            raise TypeError("client must provide mute sync Actions")
        self._client = client
        self._clock = clock or time.time
        self._refresh_cooldown = float(refresh_cooldown)
        self._refresh_slots = asyncio.Semaphore(max_concurrent_refreshes)
        self._snapshots: dict[int, MuteSnapshot] = {}
        self._refresh_locks: dict[int, asyncio.Lock] = {}
        self._refresh_attempts: dict[int, float] = {}
        self._diagnostics: deque[str] = deque(maxlen=128)
        self._initialize_lock = asyncio.Lock()
        self._initialized = False
        self._self_id: int | None = None

    @property
    def initialized(self) -> bool:
        """返回是否已完成登录、群列表和全部成员查询。"""

        return self._initialized

    @property
    def is_initialized(self) -> bool:
        """返回 ``initialized`` 的语义化别名。"""

        return self._initialized

    @property
    def self_id(self) -> int | None:
        """返回最近一次成功读取的 Bot 身份。"""

        return self._self_id

    @property
    def group_ids(self) -> tuple[int, ...]:
        """返回当前群列表中的群 ID。"""

        return tuple(self._snapshots)

    @property
    def diagnostics(self) -> tuple[str, ...]:
        """返回不包含异常正文的有界诊断。"""

        return tuple(self._diagnostics)

    @property
    def snapshots(self) -> Mapping[int, MuteSnapshot]:
        """返回不可变的当前快照。"""

        return MappingProxyType(dict(self._snapshots))

    def get_snapshot(self, group_id: object) -> MuteSnapshot:
        """返回指定群的快照，未知群使用 fail-closed 默认值。"""

        value = _validate_id(group_id, "group_id")
        return self._snapshots.get(value, MuteSnapshot(value))

    def get_state(self, group_id: object) -> MuteSnapshot:
        """提供状态查询的语义化别名。"""

        return self.get_snapshot(group_id)

    def gate_snapshot(self, group_id: object) -> tuple[MuteState, MuteState]:
        """返回供 MutedGroupGate 使用的成员和全体二态快照。"""

        if not self._initialized:
            return "muted", "muted"
        snapshot = self.get_snapshot(group_id)
        return snapshot.member_mute, snapshot.whole_mute

    def is_muted(self, group_id: object) -> bool:
        """返回成员禁言或全体禁言是否会阻止该群发言。"""

        member_mute, whole_mute = self.gate_snapshot(group_id)
        return member_mute == "muted" or whole_mute == "muted"

    async def initialize(self) -> bool:
        """按登录、群列表、逐群成员查询顺序建立初始快照。"""

        async with self._initialize_lock:
            self._initialized = False
            try:
                login = await self._client.get_login_info()
                groups = await self._client.get_group_list()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._record("initial_state_action_failed")
                raise MuteSyncError("initial mute sync failed") from error

            if not isinstance(login, LoginInfo) or not isinstance(groups, GroupList):
                self._record("initial_state_shape_invalid")
                raise MuteSyncError("initial mute sync failed")
            self._self_id = _validate_id(login.uin, "self_id")
            group_ids = tuple(_validate_id(group.group_id, "group_id") for group in groups.groups)
            self._retain_current_groups(group_ids)

            failures = False
            for group_id in group_ids:
                try:
                    member_info = await self._client.get_group_member_info(group_id, self._self_id)
                    self._apply_member_info(group_id, member_info, self._read_clock())
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    failures = True
                    self._record("initial_member_query_failed")

            if failures:
                raise MuteSyncError("initial mute sync failed")
            self._initialized = True
            return True

    async def initial_sync(self) -> bool:
        """提供初始状态同步的语义化别名。"""

        return await self.initialize()

    async def sync_initial(self) -> bool:
        """提供初始状态同步的兼容别名。"""

        return await self.initialize()

    async def refresh_group(self, group_id: object) -> bool:
        """刷新一个已知群的 Bot 成员禁言状态并限制并发。"""

        try:
            normalized_id = _validate_id(group_id, "group_id")
        except (TypeError, ValueError):
            return False
        if not self._initialized or self._self_id is None:
            return False
        if normalized_id not in self._snapshots:
            return False

        lock = self._refresh_locks.setdefault(normalized_id, asyncio.Lock())
        if lock.locked():
            return False
        async with lock:
            now = self._read_clock()
            previous_attempt = self._refresh_attempts.get(normalized_id)
            if previous_attempt is not None and now - previous_attempt < self._refresh_cooldown:
                return False
            self._refresh_attempts[normalized_id] = now
            async with self._refresh_slots:
                try:
                    member_info = await self._client.get_group_member_info(
                        normalized_id, self._self_id
                    )
                    self._apply_member_info(normalized_id, member_info, now)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    self._record("member_refresh_failed")
                    return False
            return True

    async def refresh_after_send_failure(self, target: object) -> bool:
        """仅为明确的 group 目标触发受控刷新，dm 目标直接忽略。"""

        if not isinstance(target, str):
            return False
        try:
            normalized = normalize_chat_key(target)
        except (TypeError, ValueError):
            return False
        if not normalized.startswith("group:"):
            return False
        return await self.refresh_group(int(normalized.split(":", 1)[1]))

    async def on_send_failure(self, target: object) -> bool:
        """提供发送失败通知的兼容入口。"""

        return await self.refresh_after_send_failure(target)

    async def notify_send_failure(self, target: object) -> bool:
        """提供发送失败通知的语义化入口。"""

        return await self.refresh_after_send_failure(target)

    def apply_event(self, event: Event | object) -> bool:
        """应用已确认的 group_mute 或 group_whole_mute 事件。"""

        try:
            parsed = event if isinstance(event, Event) else parse_event(event)
        except ParseError:
            self._record("mute_event_malformed")
            return False
        if not self._initialized or self._self_id is None or parsed.self_id != self._self_id:
            return False
        if parsed.event_type == "group_mute":
            return self._apply_group_mute(parsed)
        if parsed.event_type == "group_whole_mute":
            return self._apply_group_whole_mute(parsed)
        return False

    def handle_event(self, event: Event | object) -> bool:
        """提供事件消费方使用的兼容入口。"""

        return self.apply_event(event)

    def _apply_group_mute(self, event: Event) -> bool:
        data = event.data
        group_id = _event_id(data, "group_id")
        user_id = _event_id(data, "user_id")
        duration = _event_id(data, "duration")
        if group_id is None or user_id is None or duration is None:
            self._record("mute_event_malformed")
            return False
        if user_id != self._self_id or group_id not in self._snapshots:
            return False
        current = self._snapshots[group_id]
        deadline = None if duration == 0 else event.time + duration
        self._snapshots[group_id] = MuteSnapshot(
            group_id=group_id,
            member_mute="unmuted" if duration == 0 else "muted",
            whole_mute=current.whole_mute,
            member_mute_until=deadline,
            observed_at=float(event.time),
            refreshed_at=current.refreshed_at,
        )
        return True

    def _apply_group_whole_mute(self, event: Event) -> bool:
        group_id = _event_id(event.data, "group_id")
        is_mute = event.data.get("is_mute")
        if group_id is None or not isinstance(is_mute, bool):
            self._record("mute_event_malformed")
            return False
        if group_id not in self._snapshots:
            return False
        current = self._snapshots[group_id]
        self._snapshots[group_id] = MuteSnapshot(
            group_id=group_id,
            member_mute=current.member_mute,
            whole_mute="muted" if is_mute else "unmuted",
            member_mute_until=current.member_mute_until,
            observed_at=float(event.time),
            refreshed_at=current.refreshed_at,
        )
        return True

    def _apply_member_info(
        self,
        group_id: int,
        member_info: GroupMemberInfo,
        observed_at: float,
    ) -> None:
        if not isinstance(member_info, GroupMemberInfo):
            raise TypeError("member response is malformed")
        member = member_info.member
        if member.group_id != group_id or member.user_id != self._self_id:
            raise ValueError("member identity disagrees with requested group")
        until = member.shut_up_end_time
        muted = until is not None and until > observed_at
        current = self._snapshots[group_id]
        self._snapshots[group_id] = MuteSnapshot(
            group_id=group_id,
            member_mute="muted" if muted else "unmuted",
            whole_mute=current.whole_mute,
            member_mute_until=until if muted else None,
            observed_at=observed_at,
            refreshed_at=observed_at,
        )

    def _retain_current_groups(self, group_ids: tuple[int, ...]) -> None:
        previous = self._snapshots
        self._snapshots = {
            group_id: previous.get(group_id, MuteSnapshot(group_id)) for group_id in group_ids
        }

    def _read_clock(self) -> float:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("clock must return a number")
        if not math.isfinite(value):
            raise ValueError("clock must return a finite number")
        return float(value)

    def _record(self, reason: str) -> None:
        self._diagnostics.append(reason)


def _validate_id(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _event_id(data: Mapping[str, object], field_name: str) -> int | None:
    value = data.get(field_name)
    try:
        return _validate_id(value, field_name)
    except (TypeError, ValueError):
        return None


__all__ = ["MuteSnapshot", "MuteState", "MuteSyncClient", "MuteSyncError", "MuteTracker"]
