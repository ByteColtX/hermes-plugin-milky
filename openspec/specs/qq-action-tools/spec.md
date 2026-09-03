# qq-action-tools Specification

## Purpose
为 Hermes Agent 提供一组固定、可审计且与 Milky v1.3.0 operationId 对齐的 QQ 查询和管理工具，覆盖转发、私聊文件、群成员及好友关系操作，并在工具边界保留明确的参数、错误和安全语义。

## Requirements

### Requirement: 工具发现必须使用固定的 Milky operationId 映射

插件 MUST 在现有显式 Milky 工具之外注册以下 8 个异步 ToolSpec，工具名称 MUST 与对应的 Milky operationId 完全一致：`get_forwarded_messages`、`get_private_file_download_url`、`kick_group_member`、`quit_group`、`delete_friend`、`get_friend_requests`、`accept_friend_request` 和 `reject_friend_request`。每个工具 MUST 使用 `milky` 工具集并只调用名称对应的 `/api/{operationId}` Action。插件 MUST NOT 因本 change 暴露任意 Action catalog 或未列出的 Action。

#### Scenario: Hermes 发现新增工具

- **WHEN** Hermes 加载插件并读取显式工具注册
- **THEN** 工具列表 SHALL 包含这 8 个名称
- **AND** 每个名称 SHALL 只对应同名 Milky operationId
- **AND** 既有工具 SHALL 继续保留且不得被同名覆盖

#### Scenario: 注册阶段保持无网络

- **WHEN** Hermes 在插件注册阶段发现这些 ToolSpec
- **THEN** 插件 SHALL 只登记 schema、handler 和可用性检查
- **AND** SHALL NOT 发起任何 Milky HTTP 请求或 SSE 连接

### Requirement: 工具参数必须匹配 Milky v1.3.0 schema 并在网络前校验

新增工具 MUST 只接受 schema 声明的参数，不得静默忽略额外字段。参数契约 MUST 为：

| ToolSpec | 必填参数 | 可选参数 |
|---|---|---|
| `get_forwarded_messages` | `forward_id: string` | 无 |
| `get_private_file_download_url` | `user_id: integer`、`file_id: string`、`file_hash: string` | `is_self_send: boolean \| null` |
| `kick_group_member` | `group_id: integer`、`user_id: integer` | `reject_add_request: boolean \| null` |
| `quit_group` | `group_id: integer` | 无 |
| `delete_friend` | `user_id: integer` | 无 |
| `get_friend_requests` | 无 | `limit: integer \| null`、`is_filtered: boolean \| null` |
| `accept_friend_request` | `initiator_uid: string` | `is_filtered: boolean \| null` |
| `reject_friend_request` | `initiator_uid: string` | `is_filtered: boolean \| null`、`reason: string \| null` |

所有 QQ ID MUST 是不含布尔值的整数，范围为 `10001` 至 `4294967295`；`limit` MUST 是不含布尔值的整数，范围为 `0` 至 `9007199254740991`；`forward_id`、`file_id`、`file_hash` 和 `initiator_uid` MUST 是非空字符串。可选字段可以省略或按 Milky schema 显式传递 `null`；省略字段时工具 MUST NOT 自行伪造默认字段。所有非法类型、范围、空字符串或额外字段 MUST 在网络访问前返回 `invalid_input`。

#### Scenario: 群管理参数通过校验

- **WHEN** Agent 调用 `kick_group_member`，提供合法的 `group_id`、`user_id` 和可选 `reject_add_request`
- **THEN** 工具 SHALL 只发送 schema 声明的字段
- **AND** Action body SHALL 使用相同的 Milky 字段名和值

#### Scenario: 好友 UID 使用字符串边界

- **WHEN** Agent 调用 `accept_friend_request` 或 `reject_friend_request`
- **THEN** 工具 SHALL 要求非空字符串 `initiator_uid`
- **AND** SHALL NOT 将昵称、数字 QQ 号或正文推断为 `initiator_uid`

#### Scenario: 非法参数不触网

- **WHEN** 任一新增工具收到缺失必填字段、错误类型、越界数值、空 ID 或未声明字段
- **THEN** 工具 SHALL 返回 `invalid_input`
- **AND** SHALL NOT 调用 Milky client、发送 HTTP 请求或记录远端结果

### Requirement: 查询工具必须返回经过协议校验的完整成功 envelope

`get_forwarded_messages`、`get_private_file_download_url` 和 `get_friend_requests` MUST 分别调用对应 Milky Action，并在成功时向 Tool 调用方返回完整的 Milky envelope。工具 MUST 保留 `data.messages`、`data.download_url` 或 `data.requests` 及未知 envelope/data 字段，不得改造成摘要 DTO、拼接为 Agent 指令或自动写入普通入站上下文。成功结果的最小 data 结构缺失、容器类型错误或字段类型错误 MUST 分类为 `malformed`。

#### Scenario: 查询合并转发消息

- **WHEN** Agent 以合法 `forward_id` 调用 `get_forwarded_messages`
- **THEN** 请求 SHALL 使用 `POST /api/get_forwarded_messages` 和 `{ "forward_id": "<forward-id>" }`
- **AND** 成功结果 SHALL 保留完整 `data.messages` 数组及协议扩展字段
- **AND** 工具 SHALL 不把转发内容自动注入当前 Hermes turn

#### Scenario: 查询私聊文件下载链接

- **WHEN** Agent 提供合法 `user_id`、`file_id`、`file_hash` 以及可选 `is_self_send`
- **THEN** 请求 SHALL 使用 `POST /api/get_private_file_download_url`
- **AND** 成功结果 SHALL 保留 `data.download_url` 和未知字段
- **AND** 插件 SHALL 不在工具调用中下载、缓存、解码或改写该 URL

#### Scenario: 查询好友请求

- **WHEN** Agent 调用 `get_friend_requests` 并提供可选的 `limit` 或 `is_filtered`
- **THEN** 请求 SHALL 使用 Milky schema 的字段名和值
- **AND** 成功结果 SHALL 保留完整 `data.requests` 数组、好友请求字段和未知扩展字段

### Requirement: 状态变更工具只能由显式调用触发且不得盲目重试

`kick_group_member`、`quit_group`、`delete_friend`、`accept_friend_request` 和 `reject_friend_request` MUST 只在对应 ToolSpec 被显式调用时执行。它们 MUST 分别调用同名 Milky Action，并使用 schema 定义的 body；不得由 `friend_request`、群通知、普通消息正文、关键词、Will 决策或其他事件自动触发。请求已进入 HTTP 边界后若响应结果未知，工具 MUST 返回 `transport_unknown`，不得自动重发或把未知结果伪装成成功。

#### Scenario: 踢出群成员

- **WHEN** Agent 显式调用 `kick_group_member` 并提供合法群号、成员 QQ 号和可选拒绝加群申请标记
- **THEN** 工具 SHALL 调用 `/api/kick_group_member`
- **AND** 成功结果 SHALL 要求并返回 Milky 成功 envelope 的空对象 data
- **AND** 系统 SHALL 不因该调用自动更新入站 Gate、群列表或其他本地状态

#### Scenario: 退出群或删除好友

- **WHEN** Agent 显式调用 `quit_group` 或 `delete_friend`
- **THEN** 工具 SHALL 只向对应的目标 Action 发送合法 ID
- **AND** SHALL 不回退到其他群、私聊或默认目标
- **AND** SHALL 不因普通文本或 observe-only 事件执行同一操作

#### Scenario: 接受或拒绝好友请求

- **WHEN** Agent 显式调用 `accept_friend_request` 或 `reject_friend_request`
- **THEN** 工具 SHALL 使用 `initiator_uid` 和可选过滤标记；拒绝工具还 SHALL 传递可选 `reason`
- **AND** 系统 SHALL 不自动批准或拒绝任何收到的好友请求事件

#### Scenario: 状态变更请求结果未知

- **WHEN** 状态变更 Action 已进入 HTTP 请求边界但客户端未取得可确认的完整响应
- **THEN** 工具 SHALL 返回 `transport_unknown`
- **AND** SHALL 只保留一次调用记录
- **AND** SHALL NOT 自动重试或返回成功结果

### Requirement: 工具必须统一处理生命周期、协议错误和安全日志

所有新增工具 MUST 复用 Milky Action 的 Bearer 认证、`POST` JSON、path prefix、envelope 和错误分类边界。工具 MUST 区分 `invalid_input`、`rejected`、`http_error`、`malformed`、`transport_unknown` 和 `unsupported`；HTTP 200 且 Milky envelope 失败不得视为成功。未绑定或已关闭的工具 client MUST 在网络访问前返回 `unsupported` 或既有传输不可用分类。日志和异常 MUST 不包含 token、Authorization header、原始响应 body、私聊文件下载 URL 或本地媒体路径；成功 envelope 中的业务字段只交付给 Tool 调用方，不得被写入普通消息上下文。

#### Scenario: HTTP 200 但协议拒绝

- **WHEN** 新增 Action 返回 HTTP 200 且 envelope 的 `status` 非 `ok` 或 `retcode` 非零
- **THEN** 工具 SHALL 返回 `rejected`
- **AND** SHALL NOT 返回成功 envelope 或伪造空对象结果

#### Scenario: 成功 data 结构缺失

- **WHEN** 查询工具成功 envelope 缺少其要求的 `messages`、`download_url` 或 `requests`，或管理工具的 data 不是确认的空对象
- **THEN** 工具 SHALL 返回 `malformed`
- **AND** SHALL 不报告假成功

#### Scenario: 未连接或已关闭

- **WHEN** Agent 在工具 client 未绑定或已关闭时调用任一新增工具
- **THEN** 工具 SHALL 在网络访问前返回 `unsupported` 或既有传输不可用分类
- **AND** SHALL 不建立新连接、不发起 HTTP 请求

#### Scenario: 安全记录工具调用

- **WHEN** 新增工具完成一次调用或得到可分类失败
- **THEN** 日志 SHALL 只记录工具名称、参数的安全业务字段和错误分类等必要诊断
- **AND** SHALL 不记录 token、Authorization、完整响应 body、下载 URL、完整敏感理由或本地路径
