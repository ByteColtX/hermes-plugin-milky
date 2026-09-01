"""验证基于规范化策略特征的 Will routing。"""

from __future__ import annotations

import builtins
import json
import random
import socket
from pathlib import Path

import pytest

from will import RoutingConfig, RoutingWillEngine, WillInput

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "will_routing"


def load_fixture() -> dict[str, object]:
    """读取脱敏 routing 策略和输入 fixture。"""

    return json.loads((FIXTURE_ROOT / "cases.json").read_text(encoding="utf-8"))


def make_input(
    *,
    scene: str = "group",
    mention_kinds: tuple[str, ...] = ("none",),
    has_reply: bool = False,
    has_image: bool = False,
    is_self_quote: bool = False,
    is_self_poke: bool = False,
    text: str = "合成文本",
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
        text=text,
        mention_kinds=mention_kinds,  # type: ignore[arg-type]
        has_reply=has_reply,
        reply_message_seq=1000 if has_reply else None,
        has_image=has_image,
        is_self_quote=is_self_quote,
        is_self_poke=is_self_poke,
    )


def test_routing_merges_all_matching_rules_without_priority() -> None:
    """routing 应评估所有命中规则并使用任一 trigger 的 OR 结果。"""

    config = RoutingConfig(
        direct="wait",
        mention="wait",
        mention_all="wait",
        quote="trigger",
        all_message="wait",
        keywords=("项目",),
    )
    engine = RoutingWillEngine(config)

    assert engine.decide(make_input(scene="friend", has_image=True)) == "wait"
    assert (
        engine.decide(
            make_input(
                mention_kinds=("self",),
                has_reply=True,
                is_self_quote=True,
            )
        )
        == "trigger"
    )
    assert engine.decide(make_input(text="请看项目进度")) == "trigger"
    assert engine.decide(make_input()) == "wait"


def test_routing_all_message_matches_friend_and_group_messages() -> None:
    """allMessage 为 trigger 时应触发所有普通 friend/group 消息。"""

    engine = RoutingWillEngine(RoutingConfig(all_message="trigger"))

    assert engine.decide(make_input(scene="friend")) == "trigger"
    assert engine.decide(make_input(scene="group")) == "trigger"


def test_routing_keeps_self_all_and_here_signals_independent() -> None:
    """self、all 和未来 here 信号应不互相替代。"""

    engine = RoutingWillEngine(
        RoutingConfig(mention="trigger", mention_all="wait", all_message="wait")
    )

    assert engine.decide(make_input(mention_kinds=("self",))) == "trigger"
    assert engine.decide(make_input(mention_kinds=("all",))) == "wait"
    assert engine.decide(make_input(mention_kinds=("here",))) == "wait"


def test_routing_accepts_fixture_cases() -> None:
    """脱敏 fixture 应覆盖 friend/group、mention、quote、关键词和图片边界。"""

    fixture = load_fixture()
    engine = RoutingWillEngine(
        RoutingConfig.from_mapping(fixture["routing_policy"])  # type: ignore[arg-type]
    )

    for case in fixture["cases"]:  # type: ignore[union-attr]
        assert isinstance(case, dict)
        assert (
            engine.decide(
                make_input(
                    scene=case["scene"],  # type: ignore[arg-type]
                    mention_kinds=tuple(case["mention_kinds"]),  # type: ignore[arg-type]
                    has_reply=case["has_reply"],  # type: ignore[arg-type]
                    has_image=case["has_image"],  # type: ignore[arg-type]
                    text=case["text"],  # type: ignore[arg-type]
                )
            )
            == case["expected"]
        )

    empty_engine = RoutingWillEngine(
        RoutingConfig.from_mapping(fixture["empty_keywords_policy"])  # type: ignore[arg-type]
    )
    empty_case = fixture["empty_keywords_case"]
    assert isinstance(empty_case, dict)
    assert (
        empty_engine.decide(
            make_input(text=empty_case["text"])  # type: ignore[arg-type]
        )
        == empty_case["expected"]
    )

    target_engine = RoutingWillEngine(
        RoutingConfig.from_mapping(fixture["target_signal_policy"])  # type: ignore[arg-type]
    )
    for case in fixture["target_signal_cases"]:  # type: ignore[union-attr]
        assert isinstance(case, dict)
        assert (
            target_engine.decide(
                make_input(
                    scene="friend" if case["event_type"] == "message_receive" else "group",
                    event_type=case["event_type"],  # type: ignore[arg-type]
                    mention_kinds=tuple(case["mention_kinds"]),  # type: ignore[arg-type]
                    has_reply=case["has_reply"],  # type: ignore[arg-type]
                    is_self_quote=case["is_self_quote"],  # type: ignore[arg-type]
                    is_self_poke=case["is_self_poke"],  # type: ignore[arg-type]
                    text=case["text"],  # type: ignore[arg-type]
                )
            )
            == case["expected"]
        )


@pytest.mark.parametrize("field_name", ["group", "image", "mentionHere"])
def test_routing_rejects_removed_fields(field_name: str) -> None:
    """routing 不应静默兼容已移除的配置字段。"""

    with pytest.raises(ValueError, match="unsupported"):
        RoutingConfig.from_mapping({field_name: "wait"})


@pytest.mark.parametrize("keywords", ["项目", [""], [1]])
def test_routing_rejects_invalid_keywords(keywords: object) -> None:
    """routing 关键词必须是非空字符串数组。"""

    with pytest.raises((TypeError, ValueError), match="keywords"):
        RoutingConfig.from_mapping({"keywords": keywords})


def test_routing_keeps_poke_and_system_nudge_observe_only() -> None:
    """poke/nudge 观察不得伪装成普通消息 trigger。"""

    engine = RoutingWillEngine(RoutingConfig(poke="trigger", all_message="trigger"))

    assert engine.decide(make_input(event_type="poke")) == "wait"
    assert engine.decide(make_input(event_type="friend_nudge")) == "wait"
    assert engine.decide(make_input(event_type="group_nudge")) == "wait"


def test_routing_only_accepts_explicit_self_poke_observations() -> None:
    """poke 只有在输入明确确认 Bot 为接收者时才命中。"""

    engine = RoutingWillEngine(RoutingConfig(poke="trigger"))

    assert engine.decide(make_input(event_type="group_nudge", is_self_poke=True)) == "trigger"
    assert engine.decide(make_input(event_type="friend_nudge", is_self_poke=True)) == "trigger"
    assert engine.decide(make_input(event_type="group_nudge")) == "wait"
    assert engine.decide(make_input(event_type="poke", is_self_poke=True)) == "trigger"


def test_routing_has_no_network_random_or_file_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """routing 只能消费输入和配置。"""

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("routing performed an external side effect")

    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(random, "random", fail)
    monkeypatch.setattr(builtins, "open", fail)

    engine = RoutingWillEngine({"allMessage": "wait", "keywords": ["提醒"]})

    assert engine.decide(make_input(text="请提醒我")) == "trigger"
