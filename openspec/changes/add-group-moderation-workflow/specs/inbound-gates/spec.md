# Spec Delta

## MODIFIED Requirements

### Requirement: Gate 按固定顺序执行

普通聊天路径的所有消息 MUST 依次经过 SelfMessage、ChatAllowlist 和 MutedGroup 三道门禁；任何门禁拒绝后 SHALL 停止后续门禁、缓冲、Will 和 Hermes 处理。

#### Scenario: 自身消息

- **WHEN** `sender_id` 等于 `self_id`
- **THEN** SelfMessage gate SHALL 以稳定 reason 拒绝
- **AND** 消息 SHALL 不增长 wait buffer 或修改 Will

#### Scenario: 白名单外消息

- **WHEN** `MILKY_ALLOWED_CHATS` 非空且完整 chat key 未命中
- **THEN** ChatAllowlist gate SHALL 拒绝消息
- **AND** SHALL 不调用 Agent 或资源接口

群管资格 MUST 与聊天门禁分开判断；Self 和有效 allowlist 拒绝同样阻断审核，而 MutedGroup 只控制普通聊天可回复路径。群管 MUST 另外确认显式启用及 Bot 管理身份，不得借此改变 Gate 的纯确定性边界或在 Gate 内调用网络。

#### Scenario: 聊天禁言但群管仍有资格

- **WHEN** 群管已启用且 Bot 管理身份确认，普通聊天因 MutedGroup 拒绝
- **THEN** 普通 wait buffer、Will 和 Hermes SHALL 停止，独立本地审核 SHALL 继续
- **AND** 审核不得把身份未确认、自身消息或白名单外消息当作合资格输入
