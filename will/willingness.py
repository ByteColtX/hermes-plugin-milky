"""基于规范化策略特征的 willingness 状态和数值决策。"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from session.identity import validate_chat_key

from .input import WillInput
from .routing import RoutingWillEngine

Decision = Literal["wait", "trigger"]
_POKE_EVENTS = frozenset({"poke", "notice.poke"})


@dataclass(frozen=True, slots=True)
class WillingnessConfig:
    """保存 willingness 的内部数值配置。"""

    max_score: float = 100
    initial_score: float = 0
    decay_half_life_seconds: float = 600
    probability_threshold: float = 55
    probability_amplifier: float = 0.04
    reply_cost: float = 35
    text_gain: float = 12
    mention_gain: float = 100
    quote_gain: float = 15
    direct_gain: float = 40
    image_gain: float = 8
    poke_gain: float = 80
    keywords: tuple[str, ...] = field(default_factory=tuple)
    keyword_multiplier: float = 1.2
    default_multiplier: float = 1
    hot_window_seconds: float = 15
    warm_window_seconds: float = 60
    hot_decay_weight: float = 0.3
    warm_decay_weight: float = 0.7
    mention_force: bool = False
    quote_force: bool = False
    direct_force: bool = False

    def __post_init__(self) -> None:
        """校验直接构造的配置，避免公式出现除零或无限值。"""

        numeric_fields = (
            "max_score",
            "initial_score",
            "decay_half_life_seconds",
            "probability_threshold",
            "probability_amplifier",
            "reply_cost",
            "text_gain",
            "mention_gain",
            "quote_gain",
            "direct_gain",
            "image_gain",
            "poke_gain",
            "keyword_multiplier",
            "default_multiplier",
            "hot_window_seconds",
            "warm_window_seconds",
            "hot_decay_weight",
            "warm_decay_weight",
        )
        for name in numeric_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"willingness.{name} must be a number")
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"willingness.{name} must be finite and non-negative")
        if self.max_score <= 0:
            raise ValueError("willingness.max_score must be positive")
        if self.decay_half_life_seconds <= 0:
            raise ValueError("willingness.decay_half_life_seconds must be positive")
        if self.probability_threshold > 100:
            raise ValueError("willingness.probability_threshold must be at most 100")
        if self.probability_amplifier > 1:
            raise ValueError("willingness.probability_amplifier must be at most 1")
        if self.initial_score > self.max_score:
            raise ValueError("willingness.initial_score exceeds max_score")
        if not isinstance(self.keywords, tuple) or any(
            not isinstance(keyword, str) or not keyword.strip() for keyword in self.keywords
        ):
            raise TypeError("willingness.keywords must contain non-empty strings")
        for name in ("mention_force", "quote_force", "direct_force"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"willingness.{name} must be boolean")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object] | None = None) -> WillingnessConfig:
        """从外部 camelCase mapping 构造数值配置。"""

        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise TypeError("willingness must be an object")
        aliases = {
            "maxScore": "max_score",
            "initialScore": "initial_score",
            "decayHalfLifeSeconds": "decay_half_life_seconds",
            "probabilityThreshold": "probability_threshold",
            "probabilityAmplifier": "probability_amplifier",
            "replyCost": "reply_cost",
            "textGain": "text_gain",
            "mentionGain": "mention_gain",
            "quoteGain": "quote_gain",
            "directGain": "direct_gain",
            "imageGain": "image_gain",
            "pokeGain": "poke_gain",
            "keywords": "keywords",
            "keywordMultiplier": "keyword_multiplier",
            "defaultMultiplier": "default_multiplier",
            "hotWindowSeconds": "hot_window_seconds",
            "warmWindowSeconds": "warm_window_seconds",
            "hotDecayWeight": "hot_decay_weight",
            "warmDecayWeight": "warm_decay_weight",
            "mentionForce": "mention_force",
            "quoteForce": "quote_force",
            "directForce": "direct_force",
        }
        unknown = sorted(set(value) - set(aliases))
        if unknown:
            raise ValueError("willingness contains unsupported fields")
        values: dict[str, object] = {}
        for key, internal_name in aliases.items():
            if key in value:
                item = value[key]
                if internal_name == "keywords":
                    if not isinstance(item, Sequence) or isinstance(item, (str, bytes)):
                        raise TypeError("willingness.keywords must be an array")
                    item = tuple(item)
                values[internal_name] = item
        return cls(**values)  # type: ignore[arg-type]

    @property
    def maxScore(self) -> float:
        """返回外部 schema 的 maxScore 字段。"""

        return self.max_score

    @property
    def initialScore(self) -> float:
        """返回外部 schema 的 initialScore 字段。"""

        return self.initial_score

    @property
    def decayHalfLifeSeconds(self) -> float:
        """返回外部 schema 的 decayHalfLifeSeconds 字段。"""

        return self.decay_half_life_seconds


@dataclass(frozen=True, slots=True)
class WillingnessState:
    """保存一个 chat 的可丢失 willingness 状态。"""

    score: float
    last_message_at: float | None = None
    last_decay_at: float | None = None

    @property
    def lastMessageAt(self) -> float | None:
        """返回契约中的 lastMessageAt。"""

        return self.last_message_at

    @property
    def lastDecayAt(self) -> float | None:
        """返回契约中的 lastDecayAt。"""

        return self.last_decay_at


class WillingnessWillEngine:
    """按 chat 隔离状态并执行 willingness 决策。"""

    def __init__(
        self,
        config: WillingnessConfig | Mapping[str, object] | None = None,
        *,
        clock: Callable[[], float] | None = None,
        random_fn: Callable[[], float] | None = None,
    ) -> None:
        """创建可注入时钟和随机源的 willingness engine。"""

        if isinstance(config, WillingnessConfig):
            self.config = config
        elif config is None or isinstance(config, Mapping):
            self.config = WillingnessConfig.from_mapping(config)
        else:
            raise TypeError("config must be a WillingnessConfig or object")
        self._clock = clock or time.time
        self._random = random_fn or random.random
        self._states: dict[str, WillingnessState] = {}

    @property
    def states(self) -> Mapping[str, WillingnessState]:
        """返回不允许外部修改的状态快照。"""

        return MappingProxyType(dict(self._states))

    def get_state(self, chat_key: str) -> WillingnessState:
        """返回指定 chat 的状态，未知 chat 使用初始分数。"""

        normalized_key = validate_chat_key(chat_key)
        return self._states.get(normalized_key, self._initial_state())

    def get_current_willingness(self, chat_key: str | None = None) -> float:
        """返回指定 chat 的当前分数。"""

        if chat_key is None:
            if len(self._states) != 1:
                return self.config.initial_score
            return next(iter(self._states.values())).score
        return self.get_state(chat_key).score

    def decide(self, input_value: WillInput) -> Decision:
        """衰减、计算并抽样一次规范化输入。"""

        if not isinstance(input_value, WillInput):
            raise TypeError("input_value must be a WillInput")
        if input_value.event_type in _POKE_EVENTS:
            return self._decide_poke(input_value)
        if input_value.event_type != "message_receive":
            return "wait"

        chat_key = validate_chat_key(input_value.chat_key)
        state = self.get_state(chat_key)
        now = _read_clock(self._clock)
        if _is_clock_rollback(state, now):
            probability = calculate_probability(state.score, self.config)
            return (
                "trigger" if should_force(input_value, self.config) else self._sample(probability)
            )

        decayed = state.score
        if state.last_decay_at is not None and state.last_message_at is not None:
            decayed = decay_score(
                state.score,
                state.last_decay_at,
                state.last_message_at,
                now,
                self.config,
            )
        next_score = calculate_score(decayed, input_value, self.config)
        probability = calculate_probability(next_score, self.config)
        self._states[chat_key] = WillingnessState(next_score, now, now)
        if should_force(input_value, self.config):
            return "trigger"
        return self._sample(probability)

    def on_reply_submitted(self, chat_key: str | WillInput) -> None:
        """在 Hermes 正常接受 trigger 后扣除一次 reply cost。"""

        normalized_key = _chat_key_from_value(chat_key)
        state = self.get_state(normalized_key)
        self._states[normalized_key] = WillingnessState(
            max(0, state.score - self.config.reply_cost),
            state.last_message_at,
            state.last_decay_at,
        )

    def on_reply(self, chat_key: str | WillInput | None = None) -> None:
        """提供兼容名称，表示一次已提交的成功回复。"""

        if chat_key is None:
            if len(self._states) != 1:
                raise ValueError("chat_key is required when multiple chats exist")
            chat_key = next(iter(self._states))
        self.on_reply_submitted(chat_key)

    def reply_submitted(self, chat_key: str | WillInput) -> None:
        """提供语义化的成功回复反馈入口。"""

        self.on_reply_submitted(chat_key)

    def _decide_poke(self, input_value: WillInput) -> Decision:
        """只使用 poke 专用增益处理观察事件。"""

        chat_key = validate_chat_key(input_value.chat_key)
        state = self.get_state(chat_key)
        now = _read_clock(self._clock)
        if _is_clock_rollback(state, now):
            probability = calculate_probability(state.score, self.config)
            return self._sample(probability)
        decayed = state.score
        if state.last_decay_at is not None and state.last_message_at is not None:
            decayed = decay_score(
                state.score,
                state.last_decay_at,
                state.last_message_at,
                now,
                self.config,
            )
        next_score = add_gain(decayed, self.config.poke_gain, self.config)
        self._states[chat_key] = WillingnessState(next_score, now, now)
        return self._sample(calculate_probability(next_score, self.config))

    def _initial_state(self) -> WillingnessState:
        return WillingnessState(self.config.initial_score)

    def _sample(self, probability: float) -> Decision:
        return "trigger" if _read_random(self._random) < probability else "wait"


WillingnessEngine = WillingnessWillEngine


def build_engine(
    policy: Mapping[str, object] | None = None,
    *,
    clock: Callable[[], float] | None = None,
    random_fn: Callable[[], float] | None = None,
) -> RoutingWillEngine | WillingnessWillEngine:
    """根据完整嵌套策略选择 routing 或 willingness engine。"""

    if policy is None:
        root: Mapping[str, object] = {}
    elif isinstance(policy, Mapping):
        root = policy
    else:
        raise TypeError("will policy must be an object")
    engine_name = root.get("engine", "routing")
    if engine_name == "routing":
        routing = root.get("routing")
        if routing is not None and not isinstance(routing, Mapping):
            raise TypeError("will policy routing must be an object")
        return RoutingWillEngine(routing)
    if engine_name == "willingness":
        willingness = root.get("willingness")
        if willingness is not None and not isinstance(willingness, Mapping):
            raise TypeError("will policy willingness must be an object")
        return WillingnessWillEngine(willingness, clock=clock, random_fn=random_fn)
    raise ValueError("will policy engine must be routing or willingness")


def decay_score(
    score: float,
    last_decay_at: float,
    last_message_at: float,
    now: float,
    config: WillingnessConfig,
) -> float:
    """按热窗口、温窗口和阈值半速规则衰减分数。"""

    if now < last_decay_at:
        return score
    weighted_seconds = weighted_silence_seconds(last_decay_at, last_message_at, now, config)
    if score > config.probability_threshold and config.probability_threshold > 0:
        decayed = decay_high_score(
            score,
            weighted_seconds,
            config.probability_threshold,
            config.decay_half_life_seconds,
        )
    else:
        decayed = score * 0.5 ** (weighted_seconds / config.decay_half_life_seconds)
    if decayed < 0.01:
        return 0
    return max(0, decayed)


def weighted_silence_seconds(
    last_decay_at: float,
    last_message_at: float,
    now: float,
    config: WillingnessConfig,
) -> float:
    """计算 hot/warm 窗口加权后的静默秒数。"""

    hot_end = last_message_at + config.hot_window_seconds
    warm_end = last_message_at + config.warm_window_seconds

    def overlap(start: float, end: float) -> float:
        return max(0, min(now, end) - max(last_decay_at, start))

    return (
        overlap(last_message_at, hot_end) * config.hot_decay_weight
        + overlap(hot_end, warm_end) * config.warm_decay_weight
        + max(0, now - max(last_decay_at, warm_end))
    )


def decay_high_score(
    score: float,
    weighted_seconds: float,
    threshold: float,
    half_life: float,
) -> float:
    """对阈值以上的分数先使用阈值半速再使用完整半衰期。"""

    weighted_seconds_to_threshold = 2 * half_life * math.log2(score / threshold)
    if weighted_seconds <= weighted_seconds_to_threshold:
        return score * 0.5 ** ((0.5 * weighted_seconds) / half_life)
    return threshold * 0.5 ** ((weighted_seconds - weighted_seconds_to_threshold) / half_life)


def calculate_score(current: float, input_value: WillInput, config: WillingnessConfig) -> float:
    """按文本和显式策略特征计算下一次消息分数。"""

    current = _clamp_score(current, config)
    attributes = config.mention_gain if _has_mention(input_value) else 0
    attributes += config.quote_gain if input_value.has_reply else 0
    attributes += config.image_gain if input_value.has_image else 0
    attributes += config.direct_gain if input_value.is_direct else 0
    multiplier = (
        config.keyword_multiplier
        if has_keyword(input_value.text, config.keywords)
        else config.default_multiplier
    )
    ratio = current / config.max_score
    marginal_gain = max(0, 1 - ratio**2)
    gain = (
        (config.text_gain + attributes)
        * multiplier
        * marginal_gain
        * dynamic_gain_multiplier(ratio)
    )
    return _clamp_score(current + gain, config)


def add_gain(current: float, raw_gain: float, config: WillingnessConfig) -> float:
    """按 marginal gain 和 dynamic multiplier 增加专用事件分数。"""

    current = _clamp_score(current, config)
    ratio = current / config.max_score
    gain = raw_gain * max(0, 1 - ratio**2) * dynamic_gain_multiplier(ratio)
    return _clamp_score(current + gain, config)


def calculate_probability(score: float, config: WillingnessConfig) -> float:
    """将阈值以上分数转换为 0 到 1 的抽样概率。"""

    if score <= config.probability_threshold:
        return 0
    return min(
        1,
        max(0, (score - config.probability_threshold) * config.probability_amplifier),
    )


def dynamic_gain_multiplier(ratio: float) -> float:
    """返回分段 dynamic gain multiplier。"""

    if ratio < 0.2:
        return 1
    if ratio < 0.8:
        return max(1, -(((ratio - 0.5) * 2) ** 2) + 2)
    if ratio >= 1:
        return 0
    return max(0, 1 - (ratio - 0.8) / 0.2)


def has_keyword(text: str, keywords: Sequence[str]) -> bool:
    """在规范化策略文本中按顺序检查关键词。"""

    if not keywords or not isinstance(text, str):
        return False
    return any(keyword in text for keyword in keywords)


def should_force(input_value: WillInput, config: WillingnessConfig) -> bool:
    """按 direct、mention、quote 顺序判断是否绕过随机抽样。"""

    if config.direct_force and input_value.is_direct:
        return True
    if config.mention_force and _has_mention(input_value):
        return True
    return config.quote_force and input_value.has_reply


def _has_mention(input_value: WillInput) -> bool:
    return any(kind in {"self", "all", "here"} for kind in input_value.mention_kinds)


def _clamp_score(value: float, config: WillingnessConfig) -> float:
    return min(config.max_score, max(0, value))


def _chat_key_from_value(value: str | WillInput) -> str:
    if isinstance(value, WillInput):
        value = value.chat_key
    if not isinstance(value, str):
        raise TypeError("chat_key must be text")
    return validate_chat_key(value)


def _read_clock(clock: Callable[[], float]) -> float:
    value = clock()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("clock must return a number")
    if not math.isfinite(value):
        raise ValueError("clock must return a finite number")
    return float(value)


def _read_random(random_fn: Callable[[], float]) -> float:
    value = random_fn()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("random source must return a number")
    if not math.isfinite(value):
        raise ValueError("random source must return a finite number")
    return float(value)


def _is_clock_rollback(state: WillingnessState, now: float) -> bool:
    return state.last_decay_at is not None and now < state.last_decay_at


__all__ = [
    "WillingnessConfig",
    "WillingnessEngine",
    "WillingnessState",
    "WillingnessWillEngine",
    "add_gain",
    "build_engine",
    "calculate_probability",
    "calculate_score",
    "decay_high_score",
    "decay_score",
    "dynamic_gain_multiplier",
    "has_keyword",
    "should_force",
    "weighted_silence_seconds",
]
