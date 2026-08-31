# system-events-and-safety Specification

## Purpose

定义 Milky 系统事件的观察边界、诊断最小化和敏感信息保护，确保请求、禁言、撤回、
离线与未知扩展不会被误当成普通消息或高风险自动操作。

## Requirements

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

日志、异常、SendResult、fixture、快照和执行记录 MUST 不包含 token、Authorization header、真实媒体路径和敏感正文；诊断可以包含经过登记的原始 chat key、message ID 和错误类别。Milky 日志消息 SHALL 使用 Hermes-agent 风格的 `[Milky] ` 前缀和安全级别，但不得为了模拟该风格输出原始异常、请求参数或响应正文。结构化字段 SHALL 只包含经过白名单化的阶段、事件名、场景、错误分类、计数、耗时和关联标识；已注册 Tool 的专用日志还 SHALL 保留其原始业务入参和远端结果。人类可读日志 SHALL 只使用固定事件标签和一次统一前缀；动态值不得通过自由文本消息绕过字段白名单。

#### Scenario: 认证失败

- **WHEN** Milky 因认证失败或网络错误返回异常
- **THEN** 用户可见诊断 SHALL 只包含固定的错误类别，并以 `[Milky] ` 风格记录
- **AND** SHALL 不包含 token 或完整认证 header

#### Scenario: 业务消息诊断

- **WHEN** 记录消息处理失败
- **THEN** 诊断 SHALL 优先记录 chat key、message ID、reason 和安全错误类别
- **AND** SHALL 不默认记录完整正文或媒体 URL
- **AND** SHALL 不因使用 Hermes-agent 风格而放宽正文、路径或 URL 的边界

#### Scenario: 动态消息和同义字段

- **WHEN** 普通日志调用把未登记的动态字段、错误文本或第二个 `[Milky]` 前缀拼入人类可读消息
- **THEN** 系统 SHALL 拒绝该自由文本或改由规范字段安全渲染
- **AND** 同一身份、状态或计数 SHALL 不得同时通过同义字段重复输出
- **AND** 已登记业务值在人类消息与结构化字段中 SHALL 使用同一份原始值

#### Scenario: 异常链和 traceback

- **WHEN** 本地异常包含 cause、context、notes、路径、凭证、远端响应或敏感正文
- **THEN** 诊断 SHALL 只记录固定 classification/reason，不得直接输出异常链或 traceback
- **AND** 只有完整安全检查通过且不会输出本地路径的本地异常才可带 traceback

#### Scenario: 运行时日志调用点审计

- **WHEN** 审计 adapter、Milky client、SSE、inbound、resource、outbound、MuteTracker 和 smoke CLI 的输出
- **THEN** 运行时日志 SHALL 全部使用固定事件和白名单字段
- **AND** 不得存在直接的非结构化 logger 输出、原始异常文本或未经登记的 event name
- **AND** smoke CLI 的机器可读 stdout SHALL 保持独立并不得包含凭证、正文、URL 或路径

### Requirement: 入站不是授权来源

系统 MUST 只使用显式 allowlist、MuteTracker 和未来明确的审批机制作为授权来源；消息正文、mention、Will 分数或未知事件 SHALL NOT 赋予 Action 权限。

#### Scenario: 消息尝试扩大权限

- **WHEN** 入站正文要求执行未授权 Milky Action 或修改 allowlist
- **THEN** 系统 SHALL 不将正文解释为授权
- **AND** SHALL 保持既有 Gate、Action catalog 和审批边界

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
