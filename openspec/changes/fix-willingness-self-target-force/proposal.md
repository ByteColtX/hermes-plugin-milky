## Why

当前 willingness 的 force 判定和部分增益没有统一使用“明确指向当前 Bot”的目标语义：`mentionForce` 会把 `mention_all`、`here` 也视为命中，`quoteForce` 只要存在 reply 就会直接触发，`mentionGain`、`quoteGain` 和 `pokeGain` 也会消费非 Bot 目标信号。这样普通引用、全体提及、非目标提及或无法确认目标的消息可能绕过随机决策或增加不符合意图的 willingness 分数。

## What Changes

- 将 `mentionForce` 限定为消息直接提及当前 Bot（`mention.user_id == self_id`）时才直接返回 `trigger`。
- 将 `quoteForce` 限定为至少一个 `reply` segment 明确引用当前 Bot（`reply.data.sender_id == self_id`）时才直接返回 `trigger`。
- 将 `mentionGain` 限定为消息直接提及当前 Bot 时才加分；`mention_all`、`here`、他人提及和未知目标不产生该增益。
- 将 `quoteGain` 限定为至少一个 reply 明确引用当前 Bot 时才加分；`has_reply` 仍保留“存在 reply”的结构化事实，但不再单独产生该增益。
- 将 `pokeGain` 限定为协议明确确认 Bot 为接收者的 self-poke；非 Bot 或未知目标的 poke 不增加该增益，其余 poke 观察流程保持不变。
- 对引用他人、全体提及、`here` 提及、目标字段缺失或非法的消息，不得因对应 force 字段直接触发；继续执行其他 force 条件或概率抽样。
- 补充针对 Bot、非 Bot 和未知目标的 force/gain 单元测试，并同步当前 README 与 willingness spec 的可观察行为说明。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `will-willingness`: 修改 `mentionForce`、`quoteForce` 以及 `mentionGain`、`quoteGain`、`pokeGain` 的目标条件，使它们只消费明确指向当前 Bot 的结构化信号。

## Impact

- 影响 `will` 的 willingness force 决策、普通消息增益和 poke 增益，以及 `WillInput` 已有的 self mention/self quote/self poke 特征消费。
- 影响 `tests/test_will_willingness.py` 中 force/gain 行为的断言和测试输入构造。
- 影响 README 与 `openspec/specs/will-willingness/spec.md` 对 force/gain 语义的说明。
- 不改变 `routing`、`textGain`、`imageGain`、`directGain`、Gate、消息生命周期、Milky Action 或出站行为。
