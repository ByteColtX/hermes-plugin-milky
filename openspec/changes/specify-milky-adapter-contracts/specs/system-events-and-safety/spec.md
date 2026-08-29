## Purpose

定义 Milky 系统事件的观察边界、诊断最小化和敏感信息保护，确保请求、禁言、撤回、
离线与未知扩展不会被误当成普通消息或高风险自动操作。

## ADDED Requirements

### Requirement: 系统事件默认 observe-only

系统 MUST 识别并观察 bot_offline、message_recall、request、notice、nudge、group_mute、group_whole_mute 和 group_file_upload 等事件；除明确状态更新外 SHALL NOT 自动创建普通 Agent turn。

#### Scenario: 请求事件

- **WHEN** 收到 friend_request、group_join_request 或 group_invitation
- **THEN** 系统 SHALL 记录观察结果
- **AND** SHALL NOT 自动批准或拒绝请求

#### Scenario: 文件上传事件

- **WHEN** 收到 group_file_upload
- **THEN** 系统 SHALL 可记录安全元数据
- **AND** SHALL NOT 自动下载文件或触发 Agent

#### Scenario: 未知事件

- **WHEN** 收到未知事件类型
- **THEN** 系统 SHALL 保留 type 和安全 raw 扩展并限速记录
- **AND** SHALL 继续处理后续事件

### Requirement: 诊断不泄露秘密和不必要内容

日志、异常、SendResult、fixture、快照和执行记录 MUST 不包含 token、Authorization header、个人 QQ、真实媒体路径和敏感正文；诊断至少可以包含 chat key、message ID 和错误类别。

#### Scenario: 认证失败

- **WHEN** Milky 因认证失败或网络错误返回异常
- **THEN** 用户可见诊断 SHALL 只包含脱敏的错误类别
- **AND** SHALL 不包含 token 或完整认证 header

#### Scenario: 业务消息诊断

- **WHEN** 记录消息处理失败
- **THEN** 诊断 SHALL 优先记录 chat key、message ID、reason 和安全错误类别
- **AND** SHALL 不默认记录完整正文或媒体 URL

### Requirement: 入站不是授权来源

系统 MUST 只使用显式 allowlist、MuteTracker 和未来明确的审批机制作为授权来源；消息正文、mention、Will 分数或未知事件 SHALL NOT 赋予 Action 权限。

#### Scenario: 消息尝试扩大权限

- **WHEN** 入站正文要求执行未授权 Milky Action 或修改 allowlist
- **THEN** 系统 SHALL 不将正文解释为授权
- **AND** SHALL 保持既有 Gate、Action catalog 和审批边界

### Requirement: 只声明显式设计的 Action 工具

v0.1 MUST NOT 注册任意 Action catalog、自动请求审批、WebHook listener 或 `MILKY_HOME_CHANNEL`；v0.1 只允许显式注册 `milky_profile_like`、`milky_nudge` 和 `milky_recall_group_message` 三个 ToolSpec。每个 ToolSpec MUST 有独立参数校验、目标校验和统一错误结果；未来新增能力前 MUST 先补充对应契约。

#### Scenario: Agent 请求未注册 Action

- **WHEN** Hermes Agent 尝试调用未纳入 v0.1 契约的 Milky Action
- **THEN** 系统 SHALL 返回 `unsupported`
- **AND** SHALL 不执行该 Action

#### Scenario: Agent 调用首批工具

- **WHEN** Agent 调用名片点赞、戳一戳或撤回群消息 ToolSpec 且参数通过本地校验
- **THEN** 系统 SHALL 只调用该 ToolSpec 绑定的 Milky Action
- **AND** SHALL 不通过 HOME_CHANNEL 审批或扩大为任意 Action
