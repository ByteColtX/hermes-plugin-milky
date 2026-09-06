## MODIFIED Requirements

### Requirement: 消息增益和概率遵循本项目定义的参考语义

每次普通消息 SHALL 按 text、mention、quote、image、direct 的属性增益、
`interestKeywords` 命中时的 `keywordMultiplier`、`max(0, 1-ratio²)` marginal gain 和
分段 dynamic gain multiplier 更新 score；`forceKeywords` SHALL NOT 作为增益关键词，
也 SHALL NOT 改变 score 计算本身。概率 SHALL 在阈值以下为 0，以上按 amplifier 计算并
clamp 到 0..1。

#### Scenario: 关键词命中

- **WHEN** 所有可用 content 按顺序拼接后包含 `interestKeywords` 中任意关键词
- **THEN** 增益 SHALL 使用 `keywordMultiplier`
- **AND** SHALL 不因兴趣关键词命中直接返回 `trigger`

#### Scenario: 强制关键词不参与增益

- **WHEN** 规范化正文只包含 `forceKeywords` 中的关键词而不包含
  `interestKeywords` 中的关键词
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
命中 `forceKeywords` 作为额外的强制条件；任一 force 条件满足即 trigger，否则才使用
`random < probability` 抽样。`forceKeywords` MUST 只对通过 Gate 的合法普通
`message_receive` 生效，并 MUST 使用规范化正文的直接子串匹配。对于通过 Gate 且得到
`trigger` 的普通消息，系统 SHALL 在该次 trigger 决策完成后立即扣除一次 `replyCost`，
不等待资源解析、Hermes `handle_message()` 或最终 QQ 发送；该扣分不因后续处理失败回滚。

#### Scenario: direct force

- **WHEN** direct 消息且 `directForce` 为 true
- **THEN** Will SHALL 直接返回 trigger
- **AND** SHALL 不依赖随机抽样

#### Scenario: 强制关键词命中

- **WHEN** 合法 friend 或 group `message_receive` 通过 Gate，规范化正文包含
  `forceKeywords` 中任意非空关键词，且其他 force 条件均未满足
- **THEN** Will SHALL 直接返回 trigger
- **AND** SHALL 不调用随机抽样
- **AND** SHALL 按一次普通 trigger 执行一次 `replyCost`

#### Scenario: 强制关键词为空或未命中

- **WHEN** `forceKeywords` 为空，或规范化正文不包含其中任何关键词
- **THEN** forceKeywords SHALL 不产生强制 trigger
- **AND** Will SHALL 继续依据现有 force 条件或概率抽样返回 `wait` 或 `trigger`

#### Scenario: Gate deny 或 wait

- **WHEN** 消息被 Gate 拒绝或 Will 返回 wait
- **THEN** score SHALL 不执行 reply cost 扣除

#### Scenario: Hermes trigger 交接失败

- **WHEN** 消息通过 Gate、Will 返回 trigger，且后续资源解析、映射或 Hermes 交接失败
- **THEN** 系统 SHALL 保留该次已经执行的 reply cost 扣除
- **AND** SHALL NOT 因失败恢复该次扣分
