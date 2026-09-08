## ADDED Requirements

### Requirement: 关系观察必须位于 canonical、dedup 和 Gate 之后

普通 `message_receive` 的关系活跃度观察 MUST 发生在 canonical、稳定 dedup 和既有 Gate
全部通过之后，并且在 wait/trigger 分流前完成；关系观察不得绕过 `SelfMessageGate`、
`ChatAllowlistGate` 或 `MutedGroupGate`。命令、temp、未知事件和非 nudge 系统事件 MUST 不
进入普通关系事件路径；经过 parser 验证且明确戳向 Bot 的 nudge 只允许进入独立活跃度观察，
不得进入普通 Agent 路径。现有 Will、buffer、资源 materialization 和 Hermes handoff 顺序
MUST 保持不变。

#### Scenario: 通过 Gate 的 wait 消息观察关系

- **WHEN** 合法用户消息通过 Gate 且 Will 返回 `wait`
- **THEN** 系统 SHALL 先为对应 friend 用户或 group 成员记录一次活跃度观察
- **AND** SHALL 继续使用既有 wait buffer 行为
- **AND** SHALL 不因此创建 Agent turn

#### Scenario: 关系观察不改变 trigger 交接顺序

- **WHEN** 合法用户消息通过 Gate 且 Will 返回 `trigger`
- **THEN** 系统 SHALL 在正常 trigger 决策后继续执行既有 reply cost、资源解析、mapper 和
  `handle_message()` 顺序
- **AND** 关系观察 SHALL 不等待 Agent turn，也不得创建插件侧 Agent 队列

#### Scenario: Gate deny 不产生关系副作用

- **WHEN** 消息被 Self、allowlist 或 mute Gate 拒绝
- **THEN** 系统 SHALL 不写入 activity 或关系事件
- **AND** SHALL 保持既有“不进入 buffer、Will、资源和 Hermes”的结果

#### Scenario: Bot-directed nudge 只更新活跃度

- **WHEN** 合法系统事件是明确由用户戳向 Bot 的 friend/group nudge
- **THEN** 系统 SHALL 只为对应用户或群成员执行一次 activity 观察
- **AND** SHALL 不创建 canonical、Will、reply cost、buffer 或 Hermes turn
- **AND** 方向缺失、目标不是 Bot 或 chat key 无法确认的 nudge SHALL 不更新关系

### Requirement: 关系旁路失败不得改变消息管线结果

关系存储不可用、配置缺失、关系服务异常或关系旁路任务超时 MUST 被分类记录并隔离，
不得回滚已完成的 canonical/dedup/Gate，也不得阻止一个本来允许的用户消息进入既有 wait、
Will 或 trigger 流程。关系旁路不得报告未提交的关系更新为成功。

#### Scenario: 活跃度存储失败时消息仍可交接

- **WHEN** 消息已通过 Gate，但关系数据库在记录 activity 时提交失败
- **THEN** 系统 SHALL 记录 `persistence_error` 类诊断
- **AND** SHALL 按原有 Will 结果继续处理消息
- **AND** SHALL 不创建伪造的关系 event 或状态快照

#### Scenario: 关系服务超时不阻塞 Agent

- **WHEN** 关系观察没有在插件规定的短事务边界内完成
- **THEN** 系统 SHALL 终止或隔离该次旁路操作
- **AND** SHALL 不等待 Hermes Agent turn
- **AND** SHALL 保持既有消息交接和 reply cost 语义
