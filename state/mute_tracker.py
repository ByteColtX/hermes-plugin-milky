"""维护 Milky Bot 自身的群禁言二态快照。"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol, runtime_checkable

from milky.models import Event, GroupList, GroupMemberInfo, LoginInfo
from milky.parser import ParseError, parse_event
from session.identity import normalize_chat_key

MuteState = Literal["muted", "unmuted", "unknown"]

logger = logging.getLogger(__name__)


@runtime_checkable
class MuteSyncClient(Protocol):
    """定义 tracker 所需的 Milky 状态 Action。"""

    async def get_login_info(self) -> LoginInfo:
        """读取 Bot 登录身份。"""

    async def get_group_list(self) -> GroupList:
        """读取 Bot 当前群列表。"""

    async def get_group_member_info(
        self, group_id: int, user_id: int, *, no_cache: bool = False
    ) -> GroupMemberInfo:
        """读取 Bot 在指定群的成员信息，并支持绕过服务端缓存。"""


@dataclass(frozen=True, slots=True)
class MuteSnapshot:
    """保存一个群的成员、全体禁言和观测时间。"""

    group_id: int
    member_mute: MuteState = "muted"
    whole_mute: MuteState = "unknown"
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
        allowed_chats: Collection[str] | None = None,
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
        self._expiry_task: asyncio.Task[None] | None = None
        self._expiry_wakeup: asyncio.Event | None = None
        self._initialized = False
        self._self_id: int | None = None
        self._nickname: str | None = None
        self._allowed_chats = _normalize_allowed_chats(allowed_chats)

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
    def nickname(self) -> str | None:
        """返回最近一次成功读取的 Bot 昵称。"""

        return self._nickname

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

        self._expire_member_mutes_if_ready()
        return MappingProxyType(dict(self._snapshots))

    def get_snapshot(self, group_id: object) -> MuteSnapshot:
        """返回指定群的快照，未知群使用 fail-closed 默认值。"""

        value = _validate_id(group_id, "group_id")
        self._expire_member_mute_if_ready(value)
        return self._snapshots.get(value, MuteSnapshot(value))

    def get_state(self, group_id: object) -> MuteSnapshot:
        """提供状态查询的语义化别名。"""

        return self.get_snapshot(group_id)

    def gate_snapshot(self, group_id: object) -> tuple[MuteState, MuteState]:
        """返回供 MutedGroupGate 使用的成员和全体禁言快照。"""

        if not self._initialized:
            return "muted", "muted"
        snapshot = self.get_snapshot(group_id)
        return snapshot.member_mute, snapshot.whole_mute

    def is_muted(self, group_id: object) -> bool:
        """返回已确认的成员或全体禁言是否会阻止该群发言。"""

        member_mute, whole_mute = self.gate_snapshot(group_id)
        return member_mute == "muted" or whole_mute == "muted"

    def start(self) -> None:
        """启动个人禁言 TTL 到期任务；重复启动不会创建重复任务。"""

        if not self._initialized:
            return
        if self._expiry_task is not None and not self._expiry_task.done():
            return
        self._expiry_wakeup = asyncio.Event()
        self._expiry_task = asyncio.create_task(
            self._run_expiry_loop(),
            name="milky-mute-expiry",
        )

    async def close(self) -> None:
        """取消个人禁言 TTL 到期任务。"""

        await self._stop_expiry_task()

    async def initialize(self) -> bool:
        """按登录、群列表、逐群成员查询顺序建立初始快照。"""

        async with self._initialize_lock:
            await self._stop_expiry_task()
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
            self._nickname = login.nickname
            group_ids = self._select_group_ids(groups)
            self._retain_current_groups(group_ids)

            logger.info(
                "Milky cold-start identity uid=%s nickname=%s",
                _mask_identifier(self._self_id),
                _safe_log_text(self._nickname),
            )

            failures = False
            successful_count = 0
            muted_count = 0
            unmuted_count = 0
            unknown_count = 0
            for group_id in group_ids:
                try:
                    member_info = await self._client.get_group_member_info(
                        group_id, self._self_id, no_cache=True
                    )
                    self._apply_member_info(group_id, member_info, self._read_clock())
                    successful_count += 1
                    snapshot = self._snapshots[group_id]
                    state = _effective_mute_state(snapshot)
                    if state == "muted":
                        muted_count += 1
                        logger.info(
                            "Milky muted group group=%s member=%s whole=%s",
                            _mask_identifier(group_id),
                            snapshot.member_mute,
                            snapshot.whole_mute,
                        )
                    elif state == "unmuted":
                        unmuted_count += 1
                    else:
                        unknown_count += 1
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    failures = True
                    self._record("initial_member_query_failed")

            logger.info(
                "Milky mute scan completed scope=%s total=%d succeeded=%d failed=%d muted=%d "
                "unmuted=%d unknown=%d",
                "allowlist" if self._allowed_chats else "all_groups",
                len(group_ids),
                successful_count,
                len(group_ids) - successful_count,
                muted_count,
                unmuted_count,
                unknown_count,
            )

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
                        normalized_id, self._self_id, no_cache=True
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
        self._wake_expiry_loop()
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
        self._wake_expiry_loop()

    def _retain_current_groups(self, group_ids: tuple[int, ...]) -> None:
        previous = self._snapshots
        self._snapshots = {
            group_id: previous.get(group_id, MuteSnapshot(group_id)) for group_id in group_ids
        }

    def _select_group_ids(self, groups: GroupList) -> tuple[int, ...]:
        """按白名单选择需要查询禁言状态的群。"""

        group_ids = tuple(_validate_id(group.group_id, "group_id") for group in groups.groups)
        if not self._allowed_chats:
            return group_ids
        allowed_group_ids = {
            int(chat_key.split(":", 1)[1])
            for chat_key in self._allowed_chats
            if chat_key.startswith("group:")
        }
        return tuple(group_id for group_id in group_ids if group_id in allowed_group_ids)

    def _read_clock(self) -> float:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("clock must return a number")
        if not math.isfinite(value):
            raise ValueError("clock must return a finite number")
        return float(value)

    async def _stop_expiry_task(self) -> None:
        """停止已有 TTL 任务，避免重新同步时复制后台任务。"""

        task = self._expiry_task
        self._expiry_task = None
        self._expiry_wakeup = None
        if task is None or task is asyncio.current_task():
            return
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _run_expiry_loop(self) -> None:
        """等待最早的个人禁言截止时间并更新本地成员状态。"""

        wakeup = self._expiry_wakeup
        if wakeup is None:
            return
        while self._initialized:
            deadline = self._next_member_mute_deadline()
            if deadline is None:
                await wakeup.wait()
                wakeup.clear()
                continue
            delay = max(0.0, deadline - self._read_clock())
            try:
                await asyncio.wait_for(wakeup.wait(), timeout=delay)
            except TimeoutError:
                self._expire_member_mutes_if_ready()
            else:
                wakeup.clear()

    def _next_member_mute_deadline(self) -> int | None:
        """返回当前最早的个人禁言截止时间。"""

        deadlines = tuple(
            snapshot.member_mute_until
            for snapshot in self._snapshots.values()
            if snapshot.member_mute == "muted" and snapshot.member_mute_until is not None
        )
        return min(deadlines) if deadlines else None

    def _expire_member_mute_if_ready(self, group_id: int) -> None:
        """在已初始化状态下按本地 TTL 惰性修正一个群。"""

        if self._initialized:
            self._expire_member_mutes(self._read_clock(), group_id)

    def _expire_member_mutes_if_ready(self) -> None:
        """在已初始化状态下按本地 TTL 惰性修正所有群。"""

        if self._initialized:
            self._expire_member_mutes(self._read_clock())

    def _expire_member_mutes(self, now: float, group_id: int | None = None) -> None:
        """将已到期的个人禁言更新为 unmuted。"""

        group_ids = (group_id,) if group_id is not None else tuple(self._snapshots)
        for current_group_id in group_ids:
            snapshot = self._snapshots.get(current_group_id)
            if snapshot is None:
                continue
            until = snapshot.member_mute_until
            if snapshot.member_mute != "muted" or until is None or until > now:
                continue
            self._snapshots[current_group_id] = MuteSnapshot(
                group_id=current_group_id,
                member_mute="unmuted",
                whole_mute=snapshot.whole_mute,
                member_mute_until=None,
                observed_at=now,
                refreshed_at=snapshot.refreshed_at,
            )
            logger.info(
                "Milky mute TTL expired group=%s member=unmuted whole=%s",
                _mask_identifier(current_group_id),
                snapshot.whole_mute,
            )

    def _wake_expiry_loop(self) -> None:
        """通知 TTL 任务重新计算最近截止时间。"""

        if self._expiry_wakeup is not None:
            self._expiry_wakeup.set()

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


def _effective_mute_state(snapshot: MuteSnapshot) -> MuteState:
    """计算汇总使用的有效群禁言状态。"""

    if snapshot.member_mute == "muted" or snapshot.whole_mute == "muted":
        return "muted"
    if snapshot.member_mute == "unmuted" and snapshot.whole_mute == "unmuted":
        return "unmuted"
    return "unknown"


def _normalize_allowed_chats(allowed_chats: Collection[str] | None) -> frozenset[str]:
    """校验并保存群禁言扫描使用的完整 chat key 白名单。"""

    if allowed_chats is None:
        return frozenset()
    if isinstance(allowed_chats, (str, bytes)):
        raise TypeError("allowed_chats must be a collection of chat keys")
    try:
        return frozenset(normalize_chat_key(chat_key) for chat_key in allowed_chats)
    except (TypeError, ValueError) as error:
        raise ValueError("allowed_chats contains an invalid chat key") from error


def _mask_identifier(value: int) -> str:
    """保留数字标识前后三位并隐藏中间部分。"""

    text = str(value)
    if len(text) <= 6:
        return f"{text[:1]}{'*' * max(1, len(text) - 2)}{text[-1:]}"
    return f"{text[:3]}{'*' * (len(text) - 6)}{text[-3:]}"


def _safe_log_text(value: str) -> str:
    """转义昵称中的控制字符并限制日志长度。"""

    escaped = value.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")
    return escaped[:64] or "<empty>"


__all__ = ["MuteSnapshot", "MuteState", "MuteSyncClient", "MuteSyncError", "MuteTracker"]
