# Spec Delta

## MODIFIED Requirements

### Requirement: Gate 按固定顺序执行

除按 hot-chat-allowlist 进入 core 分发的管理命令路由例外外，所有普通入站消息 MUST 依次经过 SelfMessage、ChatAllowlist 和 MutedGroup 三道门禁；任何门禁拒绝后 SHALL 停止后续门禁、缓冲、Will 和 Hermes 处理。

#### Scenario: 自身消息

- **WHEN** `sender_id` 等于 `self_id`
- **THEN** SelfMessage gate SHALL 以稳定 reason 拒绝
- **AND** 消息 SHALL 不增长 wait buffer 或修改 Will

#### Scenario: 白名单外消息

- **WHEN** 普通消息的当前有效入站白名单为空或完整 chat key 未命中任何有效规则
- **THEN** ChatAllowlist gate SHALL 拒绝消息
- **AND** SHALL 不调用 Agent 或资源接口

管理命令例外 SHALL 豁免来源会话的白名单与入站禁言匹配；canonical、自身消息和去重边界仍然适用，管理命令 SHALL 不查询来源群或目标群状态，回执仍遵守既有发送限制。普通正文和其他命令 MUST NOT 获得此路由豁免。Gate MUST NOT 读取管理员名单或判断 slash 权限；所有命令权限 SHALL 由 core 决定。Gate 本身 SHALL 保持只读；按需群状态准备 SHALL 由通过自身与白名单检查后的普通入站流程负责，查询后重新检查授权与撤销代次。

#### Scenario: 空名单仍能管理

- **WHEN** 有效白名单为空，调用者从合法会话发送规范白名单管理命令且 canonical、自身消息和去重检查通过
- **THEN** 仅该管理命令 SHALL 进入 core 命令通道，由 core 判断权限；插件 SHALL 不先判断发送者是否为管理员
- **AND** 同一发送者的普通正文及其他命令 SHALL 被拒绝

群管资格 MUST 与聊天门禁分开判断；Self 和有效 allowlist 拒绝同样阻断审核；白名单管理命令的路由例外不授予群管审核或处置资格，而 MutedGroup 只控制普通聊天可回复路径。群管 MUST 另外确认显式启用及 Bot 管理身份，不得借此改变 Gate 的纯确定性边界或在 Gate 内调用网络。

#### Scenario: 聊天禁言但群管仍有资格

- **WHEN** 群管已启用且 Bot 管理身份确认，普通聊天因 MutedGroup 拒绝
- **THEN** 普通 wait buffer、Will 和 Hermes SHALL 停止，独立本地审核 SHALL 继续
- **AND** 审核不得把身份未确认、自身消息或白名单外消息当作合资格输入
