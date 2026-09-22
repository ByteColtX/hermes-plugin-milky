"""验证规范化到三类 WILL 关键词的文本来源与片段边界。"""

from dataclasses import replace

import pytest

from inbound.normalizer import NormalizedMessage, normalize_event
from will import RoutingConfig, RoutingWillEngine, WillingnessConfig, WillingnessWillEngine
from will.willingness import calculate_score

SELF_ID = 900000001
OTHER_ID = 800000003


def text(value: str) -> dict[str, object]:
    """构造合成普通文本片段。"""

    return {"type": "text", "data": {"text": value}}


def markdown(value: str) -> dict[str, object]:
    """构造合成 Markdown 片段。"""

    return {"type": "markdown", "data": {"content": value}}


def mention(user_id: int = OTHER_ID, name: str = "提醒小助手") -> dict[str, object]:
    """构造合成结构化提及。"""

    return {"type": "mention", "data": {"user_id": user_id, "name": name}}


def normalize(segments: list[dict[str, object]]) -> NormalizedMessage:
    """通过真实规范化入口构造群消息。"""

    result = normalize_event(
        {
            "event_type": "message_receive",
            "time": 1700000000,
            "self_id": SELF_ID,
            "data": {
                "message_scene": "group",
                "peer_id": 700000001,
                "message_seq": 9901,
                "sender_id": 800000002,
                "time": 1700000000,
                "segments": segments,
            },
        }
    )
    assert result.value is not None
    return result.value


@pytest.mark.parametrize(
    ("segments", "keyword", "matched"),
    [
        pytest.param([mention()], "提醒", False, id="mention-name"),
        pytest.param([mention(name="")], "800000003", False, id="mention-id"),
        pytest.param([{"type": "mention_all", "data": {}}], "全体", False, id="mention-all"),
        pytest.param([text("@提醒小助手")], "提醒", True, id="authored-at-text"),
        pytest.param([markdown("@提醒小助手")], "提醒", True, id="authored-markdown"),
        pytest.param([mention(), text("请提醒我")], "提醒", True, id="mention-and-text"),
        pytest.param([text("提"), text("醒")], "提醒", True, id="adjacent-text"),
        pytest.param([text("提"), markdown("醒")], "提醒", True, id="adjacent-markdown"),
        pytest.param([text("提"), mention(), text("醒")], "提醒", False, id="mention-gap"),
        pytest.param(
            [text("提"), {"type": "mention_all", "data": {}}, markdown("醒")],
            "提醒",
            False,
            id="all-gap",
        ),
        pytest.param(
            [text("提"), {"type": "image", "data": {"resource_id": "fixture"}}, text("醒")],
            "提醒",
            False,
            id="image-gap",
        ),
        pytest.param(
            [text("提"), {"type": "future_extension", "data": {}}, text("醒")],
            "提醒",
            False,
            id="unknown-gap",
        ),
        pytest.param([text("提 "), mention(), text(" 醒")], "提  醒", False, id="space-gap"),
        pytest.param(
            [
                {
                    "type": "reply",
                    "data": {
                        "message_seq": 9900,
                        "sender_id": OTHER_ID,
                        "time": 1699999999,
                        "segments": [text("提醒")],
                    },
                }
            ],
            "提醒",
            False,
            id="nested-reply",
        ),
    ],
)
def test_three_keyword_rules_share_authored_text_boundaries(
    segments: list[dict[str, object]], keyword: str, matched: bool
) -> None:
    """三类关键词共同排除结构化展示，并保留普通文本和连续区间。"""

    value = normalize(segments).will_input
    routing = RoutingWillEngine(RoutingConfig(mention="wait", keywords=(keyword,)))
    force = WillingnessWillEngine(
        WillingnessConfig(force_keywords=(keyword,), probability_threshold=100),
        clock=lambda: 0.0,
        random_fn=lambda: 0.99,
    )
    interest = WillingnessConfig(
        interest_keywords=(keyword,),
        text_gain=10,
        image_gain=0,
        keyword_multiplier=2,
        default_multiplier=1,
    )
    expected = "trigger" if matched else "wait"
    assert routing.decide(value) == expected
    assert force.decide(value) == expected
    assert calculate_score(0, value, interest) == (20 if matched else 10)


@pytest.mark.parametrize("authored_keyword", [False, True])
def test_self_mention_keeps_signals_without_name_interest_multiplier(
    authored_keyword: bool,
) -> None:
    """Bot 提及信号保留，兴趣倍率仅在真实文本命中时计算。"""

    segments = [mention(SELF_ID)]
    if authored_keyword:
        segments.append(text("提醒"))
    normalized = normalize(segments)
    value = normalized.will_input
    assert normalized.body.startswith("@提醒小助手")
    assert value.mention_self is True
    assert RoutingWillEngine(RoutingConfig(mention="trigger")).decide(value) == "trigger"
    interest = WillingnessConfig(
        text_gain=10,
        mention_gain=20,
        interest_keywords=("提醒",),
        keyword_multiplier=2,
    )
    assert calculate_score(0, value, interest) == (60 if authored_keyword else 30)

    def fail_random() -> float:
        raise AssertionError("Bot mention force sampled random")

    engine = WillingnessWillEngine(
        replace(interest, mention_force=True), clock=lambda: 0.0, random_fn=fail_random
    )
    assert engine.decide(value) == "trigger"


def test_explicit_empty_keyword_texts_never_fall_back_to_display_text() -> None:
    """明确空区间不回退；未提供区间的旧显式输入仍可使用文本。"""

    normalized = normalize([mention()])
    assert normalized.body == "@提醒小助手"
    assert normalized.will_input.keyword_texts == ()
    value = replace(normalized.will_input, text="提醒")
    assert value.matches_keyword(("提醒",)) is False
    assert replace(value, keyword_texts=None).matches_keyword(("提醒",)) is True
