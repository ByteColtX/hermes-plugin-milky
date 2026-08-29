"""验证基于规范化策略特征的 Will routing。"""

from __future__ import annotations

import builtins
import random
import socket

import pytest

from will import RoutingConfig, RoutingWillEngine, WillInput


def make_input(
    *,
    scene: str = "group",
    mention_kinds: tuple[str, ...] = ("none",),
    has_reply: bool = False,
    has_image: bool = False,
    event_type: str = "message_receive",
) -> WillInput:
    """构造只包含已规范化策略特征的输入。"""

    return WillInput(
        event_type=event_type,
        scene=scene,
        self_id=900000001,
        chat_key="dm:800000001" if scene == "friend" else "group:700000001",
        channel="dm:800000001" if scene == "friend" else "group:700000001",
        timestamp=1700000000,
        segments=(),
        text="合成文本",
        mention_kinds=mention_kinds,  # type: ignore[arg-type]
        has_reply=has_reply,
        reply_message_seq=1000 if has_reply else None,
        has_image=has_image,
    )


def test_routing_uses_direct_then_mention_quote_image_group_priority() -> None:
    """routing 应按固定优先级选择独立动作。"""

    config = RoutingConfig(
        direct="trigger",
        mention="trigger",
        mention_all="wait",
        mention_here="trigger",
        quote="trigger",
        image="wait",
        group="wait",
    )
    engine = RoutingWillEngine(config)

    assert engine.decide(make_input(scene="friend", has_image=True)) == "trigger"
    assert (
        engine.decide(
            make_input(
                mention_kinds=("self",),
                has_reply=True,
                has_image=True,
            )
        )
        == "trigger"
    )
    assert engine.decide(make_input(has_reply=True, has_image=True)) == "trigger"
    assert engine.decide(make_input(has_image=True)) == "wait"
    assert engine.decide(make_input()) == "wait"


def test_routing_keeps_self_all_and_here_actions_independent() -> None:
    """不同 mention 信号不得合并为同一个配置项。"""

    engine = RoutingWillEngine(
        RoutingConfig(mention="trigger", mention_all="wait", mention_here="trigger")
    )

    assert engine.decide(make_input(mention_kinds=("self",))) == "trigger"
    assert engine.decide(make_input(mention_kinds=("all",))) == "wait"
    assert engine.decide(make_input(mention_kinds=("here",))) == "trigger"


def test_routing_accepts_only_explicit_normalized_mention_signals() -> None:
    """routing 不应从正文猜测 v1.3 不存在的 mention here。"""

    engine = RoutingWillEngine(RoutingConfig(mention_here="trigger", group="wait"))
    ordinary = make_input(mention_kinds=("none",))

    assert ordinary.mention_here is False
    assert engine.decide(ordinary) == "wait"


def test_routing_keeps_poke_and_system_nudge_observe_only() -> None:
    """poke/nudge 观察不得伪装成普通消息 trigger。"""

    engine = RoutingWillEngine(RoutingConfig(poke="trigger"))

    assert engine.decide(make_input(event_type="poke")) == "wait"
    assert engine.decide(make_input(event_type="friend_nudge")) == "wait"
    assert engine.decide(make_input(event_type="group_nudge")) == "wait"


def test_routing_has_no_network_random_or_file_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """routing 只能消费输入和配置。"""

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("routing performed an external side effect")

    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(random, "random", fail)
    monkeypatch.setattr(builtins, "open", fail)

    assert RoutingWillEngine(RoutingConfig()).decide(make_input()) == "wait"
