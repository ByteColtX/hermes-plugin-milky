## MODIFIED Requirements

### Requirement: force 顺序和 trigger reply cost 不得改变

force 判断 MUST 按 directForce、mentionForce、quoteForce 顺序语义处理；任一满足即 trigger，否则才使用 `random < probability` 抽样。对于通过 Gate 且得到 `trigger` 的普通消息，系统 SHALL 在该次 trigger 决策完成后立即扣除一次 `replyCost`，不等待资源解析、Hermes `handle_message()` 或最终 QQ 发送；该扣分不因后续处理失败回滚。

#### Scenario: direct force

- **WHEN** direct 消息且 `directForce` 为 true
- **THEN** Will SHALL 直接返回 trigger
- **AND** SHALL 不依赖随机抽样
- **AND** SHALL 立即扣除一次 `replyCost`

#### Scenario: Gate deny 或 wait

- **WHEN** 消息被 Gate 拒绝或 Will 返回 wait
- **THEN** score SHALL 不执行 reply cost 扣除

#### Scenario: Hermes trigger 交接失败

- **WHEN** 消息通过 Gate、Will 返回 trigger，且后续资源解析、映射或 Hermes 交接失败
- **THEN** 系统 SHALL 保留该次已经执行的 reply cost 扣除
- **AND** SHALL NOT 因失败恢复该次扣分
