"""验证基于规范化策略特征的 willingness 状态和公式。"""

from __future__ import annotations

import math

import pytest

from will import (
    WillingnessConfig,
    WillingnessWillEngine,
    WillInput,
    build_engine,
    calculate_probability,
    calculate_score,
    decay_score,
    dynamic_gain_multiplier,
    has_keyword,
    weighted_silence_seconds,
)


def make_input(
    *,
    chat_key: str = "group:700000001",
    scene: str = "group",
    text: str = "合成文本",
    mention_kinds: tuple[str, ...] = ("none",),
    has_reply: bool = False,
    has_image: bool = False,
    event_type: str = "message_receive",
) -> WillInput:
    """构造只包含 T08 显式特征的输入，不重新解析 raw segment。"""

    return WillInput(
        event_type=event_type,
        scene=scene,
        self_id=900000001,
        chat_key=chat_key,
        channel=chat_key,
        timestamp=1700000000,
        segments=(),
        text=text,
        mention_kinds=mention_kinds,  # type: ignore[arg-type]
        has_reply=has_reply,
        reply_message_seq=1000 if has_reply else None,
        has_image=has_image,
    )


def test_willingness_uses_nested_defaults_and_explicit_strategy_text() -> None:
    """willingness 应消费规范化文本而不是重新解析 raw segment。"""

    config = WillingnessConfig.from_mapping(
        {
            "maxScore": 100,
            "initialScore": 0,
            "textGain": 10,
            "keywords": ["Hermes"],
            "keywordMultiplier": 2,
            "defaultMultiplier": 1,
        }
    )
    input_value = make_input(text="Hermes", scene="friend")

    assert has_keyword(input_value.text, config.keywords) is True
    assert calculate_score(0, input_value, config) == 100


def test_build_engine_selects_the_nested_policy_engine() -> None:
    """完整嵌套策略应选择对应 engine，而不展平配置。"""

    engine = build_engine(
        {
            "engine": "willingness",
            "routing": {"allMessage": "trigger"},
            "willingness": {"textGain": 7},
            "priority": 1000,
        },
        random_fn=lambda: 0.99,
    )

    assert isinstance(engine, WillingnessWillEngine)
    assert engine.config.text_gain == 7


def test_willingness_matches_weighted_decay_and_dynamic_gain_boundaries() -> None:
    """热温窗口、阈值衰减和 dynamic gain 的边界应稳定。"""

    config = WillingnessConfig()

    assert weighted_silence_seconds(0, 0, 15, config) == 4.5
    assert weighted_silence_seconds(0, 0, 60, config) == 36
    assert dynamic_gain_multiplier(0.1) == 1
    assert dynamic_gain_multiplier(0.2) == pytest.approx(1.64)
    assert dynamic_gain_multiplier(0.5) == 2
    assert dynamic_gain_multiplier(0.8) == 1
    assert dynamic_gain_multiplier(1) == 0
    assert decay_score(40, 0, 0, 624, config) == 20
    assert decay_score(0.005, 0, 0, 1, config) == 0


def test_willingness_formula_adds_message_attributes_and_clamps() -> None:
    """message 属性、marginal gain 和上限应按同一公式计算。"""

    config = WillingnessConfig(
        text_gain=10,
        mention_gain=20,
        quote_gain=30,
        image_gain=40,
        direct_gain=50,
        max_score=100,
        default_multiplier=1,
    )
    input_value = make_input(
        scene="friend",
        mention_kinds=("self",),
        has_reply=True,
        has_image=True,
    )

    assert calculate_score(0, input_value, config) == 100
    assert calculate_score(80, input_value, config) == 100
    assert calculate_score(100, input_value, config) == 100


def test_willingness_probability_is_thresholded_and_clamped() -> None:
    """抽样概率应在阈值以下为零并限制在 0 到 1。"""

    config = WillingnessConfig(probability_threshold=55, probability_amplifier=0.04)

    assert calculate_probability(55, config) == 0
    assert calculate_probability(54, config) == 0
    assert calculate_probability(80, config) == 1
    assert calculate_probability(-1, config) == 0

    high_amplifier = WillingnessConfig(probability_threshold=0, probability_amplifier=1)
    assert calculate_probability(2, high_amplifier) == 1


def test_willingness_state_isolated_by_chat_and_reply_cost_is_explicit() -> None:
    """每个 chat 独立维护状态，只有显式提交反馈才扣费。"""

    clock_values = iter((0.0, 0.0))
    engine = WillingnessWillEngine(
        WillingnessConfig(text_gain=12, reply_cost=35),
        clock=lambda: next(clock_values),
        random_fn=lambda: 0.99,
    )
    group = make_input(chat_key="group:700000001")
    dm = make_input(chat_key="dm:800000001", scene="friend")

    assert engine.decide(group) == "wait"
    assert engine.decide(dm) == "wait"
    assert engine.get_current_willingness("group:700000001") == 12
    assert engine.get_current_willingness("dm:800000001") == 52

    before_failed_submission = engine.get_current_willingness("dm:800000001")
    assert before_failed_submission == 52
    engine.on_reply_submitted("group:700000001")
    assert engine.get_current_willingness("group:700000001") == 0
    assert engine.get_current_willingness("dm:800000001") == before_failed_submission


def test_willingness_clock_rollback_does_not_change_score_or_timestamps() -> None:
    """时钟回拨不能产生负静默增益、衰减或时间戳倒退。"""

    clock_values = iter((100.0, 90.0))
    engine = WillingnessWillEngine(
        WillingnessConfig(text_gain=12), clock=lambda: next(clock_values), random_fn=lambda: 0.99
    )
    input_value = make_input()

    engine.decide(input_value)
    before = engine.get_state(input_value.chat_key)
    engine.decide(input_value)
    after = engine.get_state(input_value.chat_key)

    assert after.score == before.score
    assert after.last_message_at == before.last_message_at
    assert after.last_decay_at == before.last_decay_at


def test_willingness_force_bypasses_random_in_declared_order() -> None:
    """direct、mention、quote force 均应在随机抽样前直接 trigger。"""

    def fail_random() -> float:
        raise AssertionError("force path sampled random")

    direct = WillingnessWillEngine(WillingnessConfig(direct_force=True), random_fn=fail_random)
    mention = WillingnessWillEngine(WillingnessConfig(mention_force=True), random_fn=fail_random)
    quote = WillingnessWillEngine(WillingnessConfig(quote_force=True), random_fn=fail_random)

    assert direct.decide(make_input(scene="friend")) == "trigger"
    assert mention.decide(make_input(mention_kinds=("self",))) == "trigger"
    assert quote.decide(make_input(has_reply=True)) == "trigger"


def test_poke_uses_only_poke_gain_and_nudge_stays_observe_only() -> None:
    """poke 只能使用专用增益，系统 nudge 不创建普通消息决策状态。"""

    config = WillingnessConfig(
        text_gain=100,
        mention_gain=100,
        direct_gain=100,
        quote_gain=100,
        image_gain=100,
        poke_gain=10,
        probability_threshold=100,
    )
    engine = WillingnessWillEngine(config, random_fn=lambda: 0.99)

    poke = make_input(
        event_type="poke",
        text="Hermes",
        scene="friend",
        mention_kinds=("self",),
        has_reply=True,
        has_image=True,
    )
    nudge = make_input(event_type="friend_nudge")

    assert engine.decide(poke) == "wait"
    assert engine.get_current_willingness(poke.chat_key) == 10
    assert engine.decide(nudge) == "wait"
    assert engine.get_current_willingness(nudge.chat_key) == 10


def test_willingness_exports_finite_formula_results() -> None:
    """异常浮点输入不能从纯公式边界泄漏为无限值。"""

    config = WillingnessConfig(max_score=100, initial_score=0)
    result = calculate_score(0, make_input(), config)

    assert math.isfinite(result)
