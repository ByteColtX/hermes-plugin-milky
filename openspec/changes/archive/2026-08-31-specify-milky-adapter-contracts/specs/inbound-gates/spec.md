## Purpose

为进入 Agent 前的消息提供确定性的授权与可发送性门禁，确保自身消息、聊天白名单
和动态群禁言在 Will、缓冲和 Hermes turn 之前完成判断且不产生策略副作用。

## ADDED Requirements

### Requirement: Gate 按固定顺序执行

所有普通消息 MUST 依次经过 SelfMessage、ChatAllowlist 和 MutedGroup 三道门禁；任何门禁拒绝后 SHALL 停止后续门禁、缓冲、Will 和 Hermes 处理。

#### Scenario: 自身消息

- **WHEN** `sender_id` 等于 `self_id`
- **THEN** SelfMessage gate SHALL 以稳定 reason 拒绝
- **AND** 消息 SHALL 不增长 wait buffer 或修改 Will

#### Scenario: 白名单外消息

- **WHEN** `MILKY_ALLOWED_CHATS` 非空且完整 chat key 未命中
- **THEN** ChatAllowlist gate SHALL 拒绝消息
- **AND** SHALL 不调用 Agent 或资源接口

### Requirement: 白名单按完整 chat key 匹配

当 `MILKY_ALLOWED_CHATS` 为空时 Gate SHALL 放行可识别的 friend/group 消息；非空时 MUST 只匹配完整的 `group:<id>` 或 `dm:<id>` key。temp 在 Gate 之前已被忽略，不创建命名空间。

#### Scenario: 空白名单

- **WHEN** 未配置聊天白名单
- **THEN** 合法 group 和 dm 消息 SHALL 通过白名单门禁

#### Scenario: 同号不同命名空间

- **WHEN** 白名单只包含 `group:<id>` 而消息来自 `dm:<id>`
- **THEN** 消息 SHALL 被拒绝
- **AND** SHALL NOT 因数值部分相同而放行

### Requirement: 禁言门禁读取显式状态

群消息 MUST 根据 MuteTracker 的 member mute 和 whole mute 快照判断；member mute 或已确认的
whole mute 为 `muted` 时 SHALL 拒绝发送路径。初始化未完成时状态 MUST 默认按 muted 处理；
Milky 无法通过初始 Action 确认的 whole mute SHALL 记录为 `unknown`，不得因 unknown 阻塞群消息。

#### Scenario: 群处于确认禁言

- **WHEN** 群快照显示 member mute 或 whole mute 为 muted
- **THEN** MutedGroup gate SHALL 拒绝消息
- **AND** SHALL 不触发会导致回复的 Hermes turn

#### Scenario: 群状态未维护

- **WHEN** 群状态从未成功维护，或刷新查询失败
- **THEN** Gate SHALL 按 muted 拒绝消息
- **AND** SHALL 保留此前二态状态，不得因失败改成 unmuted

### Requirement: Gate 保持纯确定性边界

Gate MUST NOT 执行网络查询、随机数、概率、关键词评分、回复发送或 Will 分数修改；Gate 结果 SHALL 至少包含 allow/reject 和稳定 reason。

#### Scenario: 相同输入重复判断

- **WHEN** 相同 canonical record 和状态快照被判断两次
- **THEN** 两次结果 SHALL 相同
- **AND** Gate SHALL 不产生网络或消息发送副作用
