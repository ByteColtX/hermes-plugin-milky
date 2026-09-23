# Spec Delta

## MODIFIED Requirements

### Requirement: 消息增益和概率遵循本项目定义的参考语义

每次普通消息 SHALL 按 text、mention、quote、image、direct 的属性增益、
`interestKeywords` 命中时的 `keywordMultiplier`、`max(0, 1-ratio²)` marginal gain 和
分段 dynamic gain multiplier 更新 score；`mentionGain` 仅在消息明确直接提及当前 Bot 时
生效，`quoteGain` 仅在至少一个 reply 明确指向当前 Bot 时生效，普通 `has_reply` 的存在性
不得单独产生 `quoteGain`。`forceKeywords` SHALL NOT 作为增益关键词，也 SHALL NOT 改变
score 计算本身。概率 SHALL 在阈值以下为 0，以上按 amplifier 计算并 clamp 到 0..1。

关键词匹配 MUST 只使用当前消息顶层 text 与 markdown 的内容，连续文本片段 SHALL 按顺序拼接；任意非文本片段 MUST 隔断匹配，不得跨越该片段拼造关键词。结构化 mention 的名称、回退 QQ 号、mention_all 的展示文字、其他结构化展示与引用嵌套内容 MUST NOT 参与关键词匹配。用户手动输入普通文本形式的 @名称 SHALL 仍按文本匹配。展示正文和独立提及信号 MUST 保持原语义。

#### Scenario: Bot direct mention gain

- **WHEN** 消息包含明确 `mention.user_id == self_id` 的直接提及
- **THEN** 本条消息 SHALL 计算一次 `mentionGain`
- **AND** 多个 self mention SHALL NOT 重复叠加该增益

#### Scenario: non-Bot mention does not gain

- **WHEN** 消息只包含他人提及、`mention_all`、`here` 或无法确认目标的提及
- **THEN** 本条消息 SHALL NOT 计算 `mentionGain`

#### Scenario: Bot quote gain

- **WHEN** 消息至少包含一个 reply，且至少一个 `reply.data.sender_id == self_id`
- **THEN** 本条消息 SHALL 计算一次 `quoteGain`
- **AND** 多个 self quote SHALL NOT 重复叠加该增益

#### Scenario: non-Bot or unknown quote does not gain

- **WHEN** 消息的 reply 只指向他人，或 `reply.data.sender_id` 缺失、非法或无法确认
- **THEN** 本条消息 SHALL NOT 计算 `quoteGain`
- **AND** `has_reply` SHALL 仍保留为独立的 reply 存在性事实

#### Scenario: 关键词命中

- **WHEN** 当前消息的可匹配连续文本包含 `interestKeywords` 中任意关键词
- **THEN** 增益 SHALL 使用 `keywordMultiplier`
- **AND** SHALL 不因兴趣关键词命中直接返回 `trigger`

#### Scenario: 强制关键词不参与增益

- **WHEN** 当前消息的可匹配连续文本只包含 `forceKeywords` 中的关键词而不包含 `interestKeywords` 中的关键词
- **THEN** 该消息 SHALL 使用 `defaultMultiplier` 计算增益
- **AND** 强制触发结果 SHALL 由 force 规则单独决定

#### Scenario: ratio 位于中间分段

- **WHEN** score/maxScore 位于 0.2（含）到 0.8（不含）之间
- **THEN** dynamic gain multiplier SHALL 使用规范定义的抛物线公式

#### Scenario: 概率 clamp

- **WHEN** amplifier 计算出的概率小于 0 或大于 1
- **THEN** 对外抽样概率 SHALL 分别 clamp 为 0 或 1

#### Scenario: 结构化提及文字不产生关键词命中

- **WHEN** 关键词仅出现在结构化提及的名称、QQ 号或全体提及展示文字中
- **THEN** 该内容 SHALL 不命中任何关键词规则
- **AND** 普通文本和 Markdown 内的相同关键词 SHALL 仍可命中

#### Scenario: 非文本片段隔断关键词

- **WHEN** 当前消息为文本“提”、结构化提及、文本“醒”，关键词为“提醒”
- **THEN** 系统 SHALL 不因拼接两侧文本命中“提醒”
- **AND** 相邻 text 与 markdown 片段组成的“提醒” SHALL 正常命中

#### Scenario: 提及名称不提高兴趣增益

- **WHEN** 仅提及名称含兴趣关键词，且普通文本没有兴趣关键词
- **THEN** 增益 SHALL 使用 defaultMultiplier
- **AND** 明确提及 Bot 时原有 mentionGain SHALL 仍正常计算

### Requirement: force 顺序和 trigger reply cost 不得改变

force 判断 MUST 保持 `directForce`、`mentionForce`、`quoteForce` 的既有顺序语义，并将
命中 `forceKeywords` 作为额外的强制条件；`directForce` 仅在 direct 消息成立时命中，
`mentionForce` 仅在消息明确直接提及当前 Bot 时命中，`quoteForce` 仅在至少一个 `reply`
segment 明确指向当前 Bot 时命中。任一 force 条件满足即 trigger，否则才使用
`random < probability` 抽样。普通 reply 的存在性不得单独使 `quoteGain` 或 `quoteForce` 命中；
只有明确引用当前 Bot 的 reply 才能满足对应目标条件。`forceKeywords` MUST 只对通过 Gate 的合法普通
`message_receive` 生效，并 MUST 使用当前消息的可匹配连续文本的直接子串匹配。对于通过 Gate 且得到
`trigger` 的普通消息，系统 SHALL 在该次 trigger 决策完成后立即扣除一次 `replyCost`，
不等待资源解析、Hermes `handle_message()` 或最终 QQ 发送；该扣分不因后续处理失败回滚。

关键词匹配 MUST 只使用当前消息顶层 text 与 markdown 的内容，连续文本片段 SHALL 按顺序拼接；任意非文本片段 MUST 隔断匹配，不得跨越该片段拼造关键词。结构化 mention 的名称、回退 QQ 号、mention_all 的展示文字、其他结构化展示与引用嵌套内容 MUST NOT 参与关键词匹配。用户手动输入普通文本形式的 @名称 SHALL 仍按文本匹配。展示正文和独立提及信号 MUST 保持原语义。

#### Scenario: direct force

- **WHEN** direct 消息且 `directForce` 为 true
- **THEN** Will SHALL 直接返回 trigger
- **AND** SHALL 不依赖随机抽样
- **AND** SHALL 立即扣除一次 `replyCost`

#### Scenario: Bot direct mention force

- **WHEN** 消息包含明确 `mention.user_id == self_id` 的直接提及且 `mentionForce` 为 true
- **THEN** Will SHALL 直接返回 trigger
- **AND** SHALL 不依赖随机抽样
- **AND** SHALL 立即扣除一次 `replyCost`

#### Scenario: non-Bot mention does not force

- **WHEN** 消息只包含他人提及、`mention_all` 或 `here` 提及且 `mentionForce` 为 true
- **THEN** `mentionForce` SHALL 不产生强制 trigger
- **AND** Will SHALL 继续依据其他 force 条件或概率抽样返回 `wait` 或 `trigger`

#### Scenario: Bot quote force

- **WHEN** 消息至少包含一个 `reply` segment，且其 `reply.data.sender_id == self_id`，同时
  `quoteForce` 为 true
- **THEN** Will SHALL 直接返回 trigger
- **AND** SHALL 不依赖随机抽样
- **AND** SHALL 立即扣除一次 `replyCost`

#### Scenario: non-Bot or unknown quote does not force

- **WHEN** 消息的 reply 只指向他人，或 `reply.data.sender_id` 缺失、非法或无法确认，且
  `quoteForce` 为 true
- **THEN** `quoteForce` SHALL 不产生强制 trigger
- **AND** Will SHALL 继续依据其他 force 条件或概率抽样返回 `wait` 或 `trigger`
- **AND** SHALL 不从引用正文、显示名称或其他未知字段推断 Bot 目标

#### Scenario: multiple replies with one Bot target

- **WHEN** 消息包含多个 reply segment，其中至少一个 reply 的
  `reply.data.sender_id == self_id`，且 `quoteForce` 为 true
- **THEN** `quoteForce` SHALL 命中并直接返回 trigger
- **AND** SHALL 不依赖随机抽样

#### Scenario: 强制关键词命中

- **WHEN** 合法 friend 或 group `message_receive` 通过 Gate，当前消息的可匹配连续文本包含
  `forceKeywords` 中任意非空关键词，且其他 force 条件均未满足
- **THEN** Will SHALL 直接返回 trigger
- **AND** SHALL 不调用随机抽样
- **AND** SHALL 按一次普通 trigger 执行一次 `replyCost`

#### Scenario: 强制关键词为空或未命中

- **WHEN** `forceKeywords` 为空，或当前消息的可匹配连续文本不包含其中任何关键词
- **THEN** forceKeywords SHALL 不产生强制 trigger
- **AND** Will SHALL 继续依据现有 force 条件或概率抽样返回 `wait` 或 `trigger`

#### Scenario: Gate deny 或 wait

- **WHEN** 消息被 Gate 拒绝或 Will 返回 wait
- **THEN** score SHALL 不执行 reply cost 扣除

#### Scenario: Hermes trigger 交接失败

- **WHEN** 消息通过 Gate、Will 返回 trigger，且后续资源解析、映射或 Hermes 交接失败
- **THEN** 系统 SHALL 保留该次已经执行的 reply cost 扣除
- **AND** SHALL NOT 因失败恢复该次扣分

#### Scenario: 结构化提及文字不产生关键词命中

- **WHEN** 关键词仅出现在结构化提及的名称、QQ 号或全体提及展示文字中
- **THEN** 该内容 SHALL 不命中任何关键词规则
- **AND** 普通文本和 Markdown 内的相同关键词 SHALL 仍可命中

#### Scenario: 非文本片段隔断关键词

- **WHEN** 当前消息为文本“提”、结构化提及、文本“醒”，关键词为“提醒”
- **THEN** 系统 SHALL 不因拼接两侧文本命中“提醒”
- **AND** 相邻 text 与 markdown 片段组成的“提醒” SHALL 正常命中
