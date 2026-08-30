## MODIFIED Requirements

### Requirement: 只声明显式设计的 Action 工具

v0.1 MUST NOT 注册任意 Action catalog、自动请求审批或 WebHook listener；v0.1 只允许显式注册 `milky_profile_like`、`milky_nudge` 和 `milky_recall_group_message` 三个 ToolSpec。`MILKY_HOME_CHANNEL` 只用于 Hermes core 投递受信系统消息，不是 Agent 可调用的 Action，也不是审批或授权来源。每个 ToolSpec MUST 有独立参数校验、目标校验和统一错误结果；未来新增能力前 MUST 先补充对应契约。

#### Scenario: Agent 请求未注册 Action

- **WHEN** Hermes Agent 尝试调用未纳入 v0.1 契约的 Milky Action
- **THEN** 系统 SHALL 返回 `unsupported`
- **AND** SHALL 不执行该 Action

#### Scenario: Agent 调用首批工具

- **WHEN** Agent 调用名片点赞、戳一戳或撤回群消息 ToolSpec 且参数通过本地校验
- **THEN** 系统 SHALL 只调用该 ToolSpec 绑定的 Milky Action
- **AND** SHALL 不通过 home channel 配置扩大为任意 Action 或授予额外权限

## ADDED Requirements

### Requirement: Hermes 系统投递与 Milky 入站系统事件保持隔离

Hermes core 产生的启动通知、系统告警和 cron 消息 MAY 投递到已配置的 Milky home channel，但这些消息 MUST 保持在出站边界；Milky SSE 收到的 recall、request、notice、lifecycle、未知事件和其他系统事件仍 MUST 使用 observe-only 路径，不得因为 home channel 已配置而自动转发、创建普通 Agent turn 或改变授权。

#### Scenario: Hermes 产生 cron 系统消息

- **WHEN** Hermes cron 生成一条受信的系统结果并解析到 Milky home channel
- **THEN** 系统 SHALL 通过标准出站 sender 投递该结果
- **AND** SHALL 不创建普通入站 MessageEvent、Gate 结果或 Will 状态

#### Scenario: Milky 收到入站系统事件

- **WHEN** SSE 收到 recall、request、notice、lifecycle 或未知事件且已配置 home channel
- **THEN** 系统 SHALL 继续按 observe-only 规则记录和更新明确状态
- **AND** SHALL 不将该事件自动发送到 home channel 或当作 Agent 授权

#### Scenario: 系统投递诊断

- **WHEN** home channel 系统投递成功、拒绝或传输结果未知
- **THEN** 诊断 SHALL 只保留安全分类、目标命名空间和必要的稳定结果字段
- **AND** SHALL 不包含 token、Authorization header、完整正文、媒体 URL 或本地路径
