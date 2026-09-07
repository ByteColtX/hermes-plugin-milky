## MODIFIED Requirements

### Requirement: 消息增益和概率遵循本项目定义的参考语义

每次普通消息 SHALL 按 text、mention、quote、image、direct 的属性增益、
`interestKeywords` 命中时的 `keywordMultiplier`、`max(0, 1-ratio²)` marginal gain 和
分段 dynamic gain multiplier 更新 score；`mentionGain` 仅在消息明确直接提及当前 Bot 时
生效，`quoteGain` 仅在至少一个 reply 明确指向当前 Bot 时生效，普通 `has_reply` 的存在性
不得单独产生 `quoteGain`。`forceKeywords` SHALL NOT 作为增益关键词，也 SHALL NOT 改变
score 计算本身。概率 SHALL 在阈值以下为 0，以上按 amplifier 计算并 clamp 到 0..1。

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

- **WHEN** 所有可用 content 按顺序拼接后包含 `interestKeywords` 中任意关键词
- **THEN** 增益 SHALL 使用 `keywordMultiplier`
- **AND** SHALL 不因兴趣关键词命中直接返回 `trigger`

#### Scenario: 强制关键词不参与增益

- **WHEN** 规范化正文只包含 `forceKeywords` 中的关键词而不包含 `interestKeywords` 中的关键词
- **THEN** 该消息 SHALL 使用 `defaultMultiplier` 计算增益
- **AND** 强制触发结果 SHALL 由 force 规则单独决定

#### Scenario: ratio 位于中间分段

- **WHEN** score/maxScore 位于 0.2（含）到 0.8（不含）之间
- **THEN** dynamic gain multiplier SHALL 使用规范定义的抛物线公式

#### Scenario: 概率 clamp

- **WHEN** amplifier 计算出的概率小于 0 或大于 1
- **THEN** 对外抽样概率 SHALL 分别 clamp 为 0 或 1

### Requirement: force 顺序和 trigger reply cost 不得改变

force 判断 MUST 保持 `directForce`、`mentionForce`、`quoteForce` 的既有顺序语义，并将
命中 `forceKeywords` 作为额外的强制条件；`directForce` 仅在 direct 消息成立时命中，
`mentionForce` 仅在消息明确直接提及当前 Bot 时命中，`quoteForce` 仅在至少一个 `reply`
segment 明确指向当前 Bot 时命中。任一 force 条件满足即 trigger，否则才使用
`random < probability` 抽样。普通 reply 的存在性不得单独使 `quoteGain` 或 `quoteForce` 命中；
只有明确引用当前 Bot 的 reply 才能满足对应目标条件。`forceKeywords` MUST 只对通过 Gate 的合法普通 `message_receive` 生效，
并 MUST 使用规范化正文的直接子串匹配。对于通过 Gate 且得到 `trigger` 的普通消息，系统
SHALL 在该次 trigger 决策完成后立即扣除一次 `replyCost`，不等待资源解析、Hermes
`handle_message()` 或最终 QQ 发送；该扣分不因后续处理失败回滚。

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

- **WHEN** 合法 friend 或 group `message_receive` 通过 Gate，规范化正文包含
  `forceKeywords` 中任意非空关键词，且其他 force 条件均未满足
- **THEN** Will SHALL 直接返回 trigger
- **AND** SHALL 不调用随机抽样
- **AND** SHALL 按一次普通 trigger 执行一次 `replyCost`

#### Scenario: 强制关键词为空或未命中

- **WHEN** `forceKeywords` 为空，或规范化正文不包含其中任何关键词
- **THEN** `forceKeywords` SHALL 不产生强制 trigger
- **AND** Will SHALL 继续依据现有 force 条件或概率抽样返回 `wait` 或 `trigger`

#### Scenario: Gate deny 或 wait

- **WHEN** 消息被 Gate 拒绝或 Will 返回 wait
- **THEN** score SHALL 不执行 `replyCost` 扣除

#### Scenario: Hermes trigger 交接失败

- **WHEN** 消息通过 Gate、Will 返回 trigger，且后续资源解析、映射或 Hermes 交接失败
- **THEN** 系统 SHALL 保留该次已经执行的 `replyCost` 扣除
- **AND** SHALL NOT 因失败恢复该次扣分

### Requirement: poke 增益不混入普通消息属性

受支持且明确指向当前 Bot 的 poke 观察 SHALL 只使用 `pokeGain`、marginal gain 和 dynamic multiplier 参与 Will 概率，不得额外增加 text、mention 或 direct gain。非 Bot 或目标未知的 poke SHALL NOT 增加 `pokeGain`，其余 poke 观察流程保持不变。

#### Scenario: poke 事件计算

- **WHEN** poke 事件明确确认 Bot 为接收者并进入 Will 观察
- **THEN** score SHALL 按 poke 专用增益更新并按概率抽样
- **AND** SHALL 不创建普通消息正文

#### Scenario: non-Bot or unknown poke does not gain

- **WHEN** poke 事件的接收者不是 Bot，或接收方向缺失、非法或无法确认
- **THEN** score SHALL NOT 增加 `pokeGain`
- **AND** SHALL 不得从发送者、正文或其他未知字段推断 Bot 接收目标
