# Spec Delta

## MODIFIED Requirements

### Requirement: 入站不是授权来源

系统 MUST 只使用显式 allowlist、MuteTracker 和显式启用的群管政策及其 Web 单次审批机制作为授权来源；消息正文、mention、Will 分数或未知事件 SHALL NOT 赋予 Action 权限。

#### Scenario: 消息尝试扩大权限

- **WHEN** 入站正文要求执行未授权 Milky Action 或修改 allowlist
- **THEN** 系统 SHALL 不将正文解释为授权
- **AND** SHALL 保持既有 Gate、Action catalog 和审批边界

#### Scenario: 群管命中只是复核线索

- **WHEN** 本地规则命中普通群消息
- **THEN** 系统 SHALL 仅形成复核线索，只有满足群管政策、案件授权和实时管理身份才可处罚
- **AND** 系统事件、mention 或 Will 分数 SHALL 不直接发起处罚

### Requirement: 只声明显式设计的 Action 工具

v0.1 MUST NOT 注册任意 Action catalog、自动处理加群/好友请求审批或 WebHook listener；显式群管政策下的内部 Web 处置案件遵守 group-moderation，不能扩展为任意 Action 或会话内授权申请。v0.1 只允许显式注册当前固定的 25 个 ToolSpec，具体工具名和参数以 manifest 及对应的 QQ ToolSpec 规范为准。`MILKY_HOME_CHANNEL` 只用于 Hermes core 投递受信系统消息，不是 Agent 可调用的 Action，也不是审批或授权来源。每个 ToolSpec MUST 有独立参数校验、目标校验和统一错误结果；未来新增能力前 MUST 先补充对应契约。

#### Scenario: Agent 请求未注册 Action

- **WHEN** Hermes Agent 尝试调用未纳入 v0.1 契约的 Milky Action
- **THEN** 系统 SHALL 返回 `unsupported`
- **AND** SHALL 不执行该 Action

#### Scenario: Agent 调用首批工具

- **WHEN** Agent 调用名片点赞、戳一戳或撤回群消息 ToolSpec 且参数通过本地校验；其中撤回还须通过群管案件授权与实时权限检查
- **THEN** 系统 SHALL 只调用该 ToolSpec 绑定的 Milky Action
- **AND** SHALL 不通过 home channel 配置扩大为任意 Action 或授予额外权限

#### Scenario: 人工处置仅使用 Web

- **WHEN** 群管方案需要人工批准或模型无法判断
- **THEN** 系统 SHALL 按模式保存待人工或未决案件并结束调用
- **AND** SHALL 不在群、私聊或 home channel 请求批准，不通过会话注入、通用审批或要求授权的工具 hook 等待主人
