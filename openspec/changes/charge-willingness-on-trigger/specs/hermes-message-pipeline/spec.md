## MODIFIED Requirements

### Requirement: trigger 提交后反馈 Will

对于通过 Gate 且被 Will 判定为 `trigger` 的普通消息，系统 SHALL 在 trigger 决策完成后立即通知 Will 执行一次 `replyCost`；该通知 SHALL 发生在资源解析、mapper、Hermes `handle_message()` 和最终 QQ 发送之前。每次 trigger SHALL 最多通知一次；资源解析、映射、Hermes 交接失败或后续任务取消 SHALL NOT 撤销已经执行的扣分。Gate deny、wait、命令、temp 和系统事件 SHALL NOT 扣费。系统 SHALL 不等待 Agent 最终 turn 完成。

#### Scenario: Hermes 接受提交

- **WHEN** 合法 friend 或 group 消息通过 Gate 且 Will 返回 trigger
- **THEN** Will SHALL 立即执行一次 reply cost 扣除
- **AND** 后续资源解析和 Hermes 交接 SHALL 不影响该次扣分

#### Scenario: Hermes 提交失败

- **WHEN** trigger 决策已经完成，但资源解析、mapper 或 Hermes `handle_message()` 抛出异常
- **THEN** 系统 SHALL 保留已经执行的 reply cost 扣除
- **AND** SHALL NOT 再次扣费或回滚该次扣费

#### Scenario: Gate、wait 和非普通消息

- **WHEN** 消息被 Gate 拒绝、Will 返回 wait，或事件属于命令、temp 或系统事件
- **THEN** 系统 SHALL 不执行 reply cost 扣除
- **AND** SHALL 不因这些事件创建普通 trigger 的扣费记录
