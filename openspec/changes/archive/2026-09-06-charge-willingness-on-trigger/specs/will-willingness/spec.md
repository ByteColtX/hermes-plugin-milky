## MODIFIED Requirements

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
- **AND** SHALL 立即扣除一次 `replyCost`

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
