# Spec Delta

## MODIFIED Requirements

### Requirement: 入站不是授权来源

普通入站 MUST 遵守显式 allowlist 和 MuteTracker 门禁，命令权限 MUST 由 Hermes core 决定。群管处置 MUST 满足显式启用的群管政策及其 Web 单次审批机制；工具遵守对应 ToolSpec 的调用边界。消息正文、mention、Will 分数或未知事件 SHALL NOT 赋予 Action 权限。

#### Scenario: 消息尝试扩大权限

- **WHEN** 入站正文要求执行未授权 Milky Action 或修改 allowlist
- **THEN** 系统 SHALL 不将正文解释为授权
- **AND** SHALL 保持既有 Gate、Action catalog 和审批边界

#### Scenario: 群管命中只是复核线索

- **WHEN** 本地规则命中普通群消息
- **THEN** 系统 SHALL 仅形成复核线索，只有满足群管政策、案件授权和实时管理身份才可处罚
- **AND** 系统事件、mention 或 Will 分数 SHALL 不直接发起处罚

### Requirement: 只声明显式设计的 Action 工具

插件 MUST NOT 注册任意 Action catalog、自动处理加群/好友请求审批或 WebHook listener；显式群管政策下的内部 Web 处置案件遵守 group-moderation，不能扩展为任意 Action 或会话内授权申请；Milky Action 工具 SHALL 限定为 qq-action-tools（主规范 `openspec/specs/qq-action-tools/spec.md`） 的固定 26 项目录，具体参数以对应工具规范为准。sticker_search 与 sticker_send 是独立语义工具，遵守各自契约，不计入 Action 目录。`MILKY_HOME_CHANNEL` 只用于 Hermes core 投递受信系统消息，不是 Agent 可调用的 Action，也不是审批或授权来源。每个 ToolSpec MUST 有明确的参数和目标校验；Action 工具的无响应错误与原始响应交付 SHALL 遵守 security-boundaries（主规范 `openspec/specs/security-boundaries/spec.md`）。新增能力前 MUST 先补充对应契约。

#### Scenario: Agent 请求未注册 Action

- **WHEN** Hermes Agent 尝试调用未纳入固定工具目录的 Milky Action
- **THEN** 系统 SHALL 返回 `unsupported`
- **AND** SHALL 不执行该 Action

#### Scenario: Agent 调用已注册消息工具

- **WHEN** Agent 调用名片点赞、戳一戳或撤回群消息 ToolSpec 且参数通过本地校验；其中撤回还须通过群管案件授权与实时权限检查
- **THEN** 系统 SHALL 只调用该 ToolSpec 绑定的 Milky Action
- **AND** SHALL 不通过 home channel 配置扩大为任意 Action 或授予额外权限

#### Scenario: 人工处置仅使用 Web

- **WHEN** 群管方案需要人工批准或模型无法判断
- **THEN** 系统 SHALL 按模式保存待人工或未决案件并结束调用
- **AND** SHALL 不在群、私聊或 home channel 请求批准，不通过会话注入、通用审批或要求授权的工具 hook 等待主人
