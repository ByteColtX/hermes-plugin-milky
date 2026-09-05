# slash-commands Specification

## Purpose

为 Milky 入站消息提供独立、可控且可扩展的 Hermes 斜杠命令通道，使内置命令不被 Will
或 Agent 普通消息处理吞掉，并以首个插件命令 `/milky` 暴露协议端实现信息。

## Requirements

### Requirement: 斜杠命令必须在 Will 之前进入独立通道

对于已经通过协议解析、canonical、TTL dedup、per-chat admission 和 Gate 的 friend 或
group `message_receive`，当消息是可识别的斜杠命令时，系统 MUST 在 wait buffer 和 Will
之前将其交给 Hermes gateway control 通道。命令 SHALL NOT 增长 wait buffer、修改 Will
状态、触发资源补全或创建普通 Agent turn。

#### Scenario: 合法群内置命令

- **WHEN** 合法 group 消息的纯文本正文为 `/status`
- **THEN** 消息 SHALL 经过既有身份、去重和 Gate 后进入 Hermes 命令通道
- **AND** SHALL 不进入 Will、wait buffer 或普通 Agent 正文

#### Scenario: Gate 拒绝命令

- **WHEN** 斜杠命令来自 self、未在 allowlist 中的 chat 或已确认不可发言的群
- **THEN** 命令 SHALL 在 Gate 阶段被拒绝
- **AND** SHALL 不调用 Hermes 命令 handler、Milky Action、Will 或 buffer

#### Scenario: 普通正文保持原有 Will 路径

- **WHEN** 消息正文不是可识别的斜杠命令
- **THEN** 消息 SHALL 继续按照既有 wait/trigger Will 流水线处理
- **AND** SHALL 不因正文包含普通斜杠字符而进入命令通道

### Requirement: Hermes MessageEvent 必须保留命令控制语义

命令交接给 Hermes 时，`MessageEvent` 的正文 MUST 保留以 `/` 开头的命令名和参数，不得
加上普通消息的 sender header、`[New message]` 标记或 channel context。事件 MUST 标记为
Hermes 可解析的 gateway control/command，并继续携带已确认的 Milky source、发送者身份和
message ID；普通消息仍 MUST 保持不允许 gateway control 的安全标记。

#### Scenario: 内置命令参数保持不变

- **WHEN** 用户发送 `/model gpt-5.5` 或其他 Hermes 内置命令及参数
- **THEN** Hermes SHALL 收到可按原有 `get_command`/`get_command_args` 语义解析的命令正文
- **AND** 命令正文 SHALL 不被 canonical 历史格式包裹或改写为 Agent 提示

#### Scenario: 命令消息的身份保留

- **WHEN** friend 或 group 斜杠命令通过 Gate
- **THEN** Hermes event SHALL 保留 `source=milky`、正确的 `dm:`/`group:` chat key、发送者和 Milky message ID
- **AND** 命令控制标记 SHALL 只改变命令分发，不改变身份授权结果

#### Scenario: 仅普通消息关闭命令控制

- **WHEN** 普通非命令消息被映射为 Hermes MessageEvent
- **THEN** event SHALL 继续禁止 gateway control
- **AND** 普通正文 SHALL 不因适配器扩大命令标记而获得命令权限

### Requirement: 内置命令和插件命令必须复用 Hermes 注册与分发边界

适配器 MUST 将 Hermes 内置斜杠命令交给宿主已有的命令 registry/dispatcher，并通过宿主
提供的插件命令注册 API 预留插件侧命令。适配器 MUST NOT 复制 Hermes 内置命令表、busy
处理、follow-up 队列、权限策略或任意 Milky Action catalog。未注册命令 SHALL 由 Hermes
按其既有 unknown-command 行为处理，不得落入 Agent 普通消息。

#### Scenario: 内置命令由 Hermes 处理

- **WHEN** Milky 消息携带 Hermes 已注册的内置命令
- **THEN** 命令 SHALL 使用 Hermes 现有 handler 和响应回传路径
- **AND** Milky plugin SHALL 不实现一套平行的内置命令分发

#### Scenario: 插件侧命令可注册

- **WHEN** Milky plugin 在根注册阶段注册插件命令 `/milky`
- **THEN** Hermes SHALL 将该命令纳入插件命令 registry 和既有 gateway 命令识别范围
- **AND** 插件命令 SHALL 继续受宿主的名称规范化和与内置命令冲突拒绝规则约束

#### Scenario: 未知命令不进入 Agent

- **WHEN** 用户发送既不是 Hermes 内置命令、插件命令或 skill 命令的 `/unknown`
- **THEN** Hermes SHALL 返回其既有 unknown-command 提示
- **AND** SHALL 不把 `/unknown` 作为普通用户正文交给 Agent

#### Scenario: Agent 忙碌时不复制宿主队列

- **WHEN** Agent 正在运行且收到插件侧斜杠命令
- **THEN** 命令 SHALL 继续携带 gateway control 语义并交给 Hermes 的既有 busy 处理
- **AND** Milky plugin SHALL 不创建第二个命令队列或承诺超出宿主能力的即时执行顺序

### Requirement: `/milky` 必须格式化返回 get_impl_info 的实现信息

插件 MUST 注册首个 `/milky` 命令。无参数调用时，系统 MUST 使用已连接且由 Milky adapter
生命周期拥有的 client 调用 `get_impl_info`，请求 MUST 为对应 `/api/get_impl_info` 的
HTTP POST、Bearer 认证和 JSON `{}` body。成功时，命令回复正文 MUST 使用固定的可读文本格式展示
`data.impl_name`、`data.impl_version`、`data.milky_version`、`data.qq_protocol_type` 和
`data.qq_protocol_version`；不得展示完整 JSON envelope 或未知扩展字段。协议失败、malformed
或传输未知时不适用成功摘要交付。

#### Scenario: 成功获取协议端信息

- **WHEN** 已连接 adapter 收到无参数 `/milky`
- **THEN** 系统 SHALL POST `/api/get_impl_info` 并发送 `{}`
- **AND** 成功回复 SHALL 返回包含上述 5 个已知字段的格式化中文摘要

#### Scenario: get_impl_info 数据形状

- **WHEN** Action 返回成功 envelope 且 `data` 包含实现名、实现版本、Milky 版本、QQ 协议类型和 QQ 协议版本
- **THEN** 命令 SHALL 将已知字段重新组织成格式化中文摘要
- **AND** SHALL 不把未知顶层或 `data` 扩展字段带入回复

#### Scenario: `/milky` 带参数

- **WHEN** 用户发送 `/milky extra`
- **THEN** 命令 SHALL 返回安全的参数错误或 usage 提示
- **AND** SHALL 不调用 `get_impl_info` 或其他 Milky Action

#### Scenario: Action 被拒绝或结果未知

- **WHEN** `get_impl_info` 返回 rejected、malformed、HTTP 错误、连接/超时或 transport_unknown
- **THEN** 用户 SHALL 收到只包含安全错误分类的失败提示
- **AND** 提示 SHALL 不包含 Authorization、token、完整响应正文或底层异常文本

### Requirement: 命令注册和 client 生命周期必须安全降级

斜杠命令注册阶段 MUST 只登记 handler 和静态元数据，不建立 Milky HTTP/SSE 连接。命令
handler MUST 使用 adapter connect 时绑定的同一 client；未连接、已停止或无法确定唯一活动
client 时 MUST 在网络访问前返回 `unsupported`，不得临时创建旁路 client。命令诊断、fixture
和结果 MUST 遵守既有秘密脱敏边界。

#### Scenario: 注册阶段无网络

- **WHEN** Hermes 加载 Milky plugin 并调用其根 `register(ctx)`
- **THEN** `/milky` SHALL 出现在插件命令 registry
- **AND** 注册过程 SHALL 不发送 HTTP/SSE 请求、不读取协议响应、不启动长期后台任务

#### Scenario: adapter 未连接

- **WHEN** 用户在 Milky adapter 完成 connect 前或 disconnect 后调用 `/milky`
- **THEN** 命令 SHALL 返回 `unsupported` 或等价的未连接提示
- **AND** SHALL 不建立新 client、不访问网络且不伪造 JSON 成功

#### Scenario: 多活动 client 无法唯一归属

- **WHEN** 宿主同时存在多个活动 Milky client 且插件命令 handler 没有 source/profile 参数可用于选择
- **THEN** `/milky` SHALL 安全返回 `unsupported`
- **AND** SHALL 不随机选择 client 或把信息泄露到错误 profile

#### Scenario: 命令诊断脱敏

- **WHEN** 命令注册、请求或响应解析失败
- **THEN** 日志和用户可见结果 SHALL 只保留命令名、错误分类和必要的安全 reason
- **AND** SHALL 不包含 token、Authorization header、真实 QQ/群 ID、媒体路径、完整响应或完整异常
