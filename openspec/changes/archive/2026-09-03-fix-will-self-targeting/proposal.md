## Why

当前 `routing.quote` 只要发现消息包含引用就会命中，因此引用其他用户消息也可能触发
Bot；`mention`、`poke` 的目标语义也没有在统一的 routing 输入契约中明确表达。需要把这
三类规则统一定义为“明确涉及 Bot 自身”的信号，避免普通群聊中的他人互动误触发。

## What Changes

- 将 `routing.quote` 的命中条件收窄为：遍历消息中的 `reply` segment，仅当 `reply.data.sender_id == self_id` 时命中；当前消息的 `message.sender_id` 只表示引用者，不参与判断；缺少或无法确认 `reply.data.sender_id` 时不命中。
- 明确 `routing.mention` 只匹配 `mention.user_id == self_id` 的直接提及；他人提及、`mention_all` 和未知 mention 不使用该规则。
- 明确 `routing.poke` 只匹配协议已确认 Bot 为接收者的 poke/nudge；戳他人、Bot 发出的戳或目标字段缺失时不命中。
- 为规范化 Will 输入提供独立的 self-mention、self-quote 和 self-poke 特征，禁止 routing 从正文、名称、`reply.data.segments` 中的 mention 或未确认 raw 字段推断目标。
- 保持 `direct`、`mentionAll`、`allMessage`、关键词、willingness 数值公式以及系统事件的 observe-only/上下文边界不变；不新增配置字段或改变 `wait`/`trigger` 值。
- 增加脱敏消息与系统事件 fixture、routing 回归和组合信号测试，覆盖 Bot 自身目标、他人目标、缺失作者/接收者、多个信号合并及无副作用路径。

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `will-routing`: 只让明确面向 Bot 自身的 mention、quote 和 poke 信号命中对应 routing 动作。
- `message-segments`: 为直接提及和 reply 提供可独立判断 Bot 目标的规范化策略特征，并在目标未知时安全降级。
- `system-events-and-safety`: 按 Milky nudge 事件的接收者/自身方向字段识别 self-poke，同时保持非目标事件不触发普通 Agent 流程。

## Impact

- 影响 `inbound/extractor.py`、`inbound/normalizer.py`、`inbound/system_events.py`、`will/input.py` 和
  `will/routing.py` 的特征传递与 routing 决策，以及相关测试和脱敏 fixture。
- 不改变 Milky HTTP Action、SSE 传输、chat key、Gate 顺序、关键词规则、配置 schema 或出站能力。
- 目标身份只能来自已解析的 `self_id`、mention 的 `user_id`、`reply.data.sender_id` 及协议确认的
  nudge 接收者字段；不从正文、名称、显示文本或未知扩展字段补全。
- 目标能力仍需在后续 apply workflow 中实现和验证；本 proposal 不表示运行时已经具备该行为。
