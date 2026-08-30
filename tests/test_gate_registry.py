"""验证 T09 三道 Gate 的固定顺序和无副作用边界。"""

from __future__ import annotations

import builtins
import random
import socket

import pytest

from gates import (
    GateContext,
    GateRegistry,
    MutedGroupGate,
)


def make_context(**overrides: object) -> GateContext:
    """创建最小的规范化 Gate 上下文。"""

    values: dict[str, object] = {
        "self_id": "100",
        "sender_id": "200",
        "scene": "group",
        "chat_key": "group:300",
        "member_mute": "unmuted",
        "whole_mute": "unmuted",
    }
    values.update(overrides)
    return GateContext(**values)  # type: ignore[arg-type]


def test_registry_uses_fixed_order_and_stops_at_first_denial() -> None:
    """Self、allowlist、mute 应按固定顺序短路。"""

    registry = GateRegistry(allowed_chats={"group:300"})

    self_result = registry.check(make_context(sender_id="100", chat_key="group:blocked"))
    assert self_result.allow is False
    assert self_result.reason == "self_message"

    allowlist_result = registry.check(make_context(chat_key="group:blocked", member_mute="muted"))
    assert allowlist_result.allow is False
    assert allowlist_result.reason == "chat_not_allowed"

    mute_result = registry.check(make_context(member_mute="muted"))
    assert mute_result.allow is False
    assert mute_result.reason == "member_muted"

    allowed_result = registry.check(make_context())
    assert allowed_result == registry.evaluate(make_context())
    assert allowed_result.allow is True
    assert allowed_result.reason == "allowed"
    assert registry.gate_names == ("self_message", "chat_allowlist", "muted_group")


def test_allowlist_matches_complete_namespaced_chat_key() -> None:
    """白名单必须区分 group 和 dm 的完整命名空间。"""

    registry = GateRegistry(allowed_chats={"group:300"})

    group = registry.check(make_context(scene="group", chat_key="group:300"))
    dm = registry.check(
        make_context(scene="friend", chat_key="dm:300", member_mute="muted", whole_mute="muted")
    )

    assert group.allow is True
    assert dm.allow is False
    assert dm.reason == "chat_not_allowed"


def test_empty_allowlist_allows_friend_and_unmuted_group() -> None:
    """空白名单放行可识别的 friend/group，群仍需通过禁言门禁。"""

    registry = GateRegistry()

    assert registry.check(make_context(scene="friend", chat_key="dm:300")).allow is True
    assert registry.check(make_context(scene="group", chat_key="group:300")).allow is True


def test_muted_group_gate_uses_confirmed_state_and_does_not_block_friend() -> None:
    """只阻止已确认的群禁言，未知全体状态和私聊不误拦截。"""

    gate = MutedGroupGate()

    assert gate.check(make_context(member_mute="muted")).reason == "member_muted"
    assert gate.check(make_context(member_mute="unmuted", whole_mute="muted")).reason == (
        "whole_muted"
    )
    assert gate.check(make_context(member_mute="unmuted", whole_mute="unknown")).allow is True
    assert gate.check(make_context(member_mute="unverified")).reason == "mute_state_unknown"
    assert gate.check(
        make_context(scene="friend", chat_key="dm:300", member_mute="muted", whole_mute="muted")
    ).allow


def test_registry_default_group_state_is_fail_closed() -> None:
    """没有 MuteTracker 成功快照时，群消息必须保持拒绝。"""

    result = GateRegistry().check(
        GateContext(
            self_id="100",
            sender_id="200",
            scene="group",
            chat_key="group:300",
        )
    )

    assert result == type(result)(allow=False, reason="member_muted")


def test_gate_registry_has_no_network_random_or_file_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gate 判断只能读取上下文，不能触发外部副作用。"""

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("gate performed an external side effect")

    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(random, "random", fail)
    monkeypatch.setattr(builtins, "open", fail)

    result = GateRegistry().check(make_context())

    assert result.allow is True


def test_gate_deny_does_not_touch_downstream_buffer_or_will() -> None:
    """拒绝结果应在下游副作用之前终止。"""

    registry = GateRegistry(allowed_chats={"group:300"})
    downstream = {"buffer": 0, "will": 0}

    result = registry.check(make_context(chat_key="group:301"))
    if result.allow:
        downstream["buffer"] += 1
        downstream["will"] += 1

    assert downstream == {"buffer": 0, "will": 0}
