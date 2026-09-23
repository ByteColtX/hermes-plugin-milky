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

### Requirement: 查询工具必须原样交付远端响应体

`get_forwarded_messages`、`get_private_file_download_url` 和 `get_friend_requests` MUST 分别调用
对应 Milky Action。插件对这些 Tool 的响应路径 MUST 只在网络前校验参数和在传输层确认是否
取得响应体；一旦取得远端响应体，Tool 调用方 SHALL 收到其原始内容，无论 HTTP 状态、协议
状态、JSON 形状、数组、显式 `null` 或未知字段为何。插件 MUST NOT 对响应体执行 envelope
校验、业务字段校验、敏感字段过滤、容器转换、JSON 重建、摘要、状态码附加或错误分类替换，
也不得把结果写入普通入站上下文。

#### Scenario: 查询合并转发消息

- **WHEN** Agent 以合法 `forward_id` 调用 `get_forwarded_messages`
- **THEN** 请求 SHALL 使用 `POST /api/get_forwarded_messages` 和 `{ "forward_id": "<forward-id>" }`
- **AND** Tool 调用方 SHALL 收到响应体中的完整数组、扩展字段和其他内容
- **AND** 工具 SHALL 不把转发内容自动注入当前 Hermes turn

#### Scenario: 查询私聊文件下载链接

- **WHEN** Agent 提供合法 `user_id`、`file_id`、`file_hash` 以及可选 `is_self_send`
- **THEN** 请求 SHALL 使用 `POST /api/get_private_file_download_url`
- **AND** Tool 调用方 SHALL 收到包含该链接及未知字段的原始响应体
- **AND** 插件 SHALL 不在工具调用中下载、缓存、解码或改写该 URL

#### Scenario: 查询好友请求

- **WHEN** Agent 调用 `get_friend_requests` 并提供可选的 `limit` 或 `is_filtered`
- **THEN** 请求 SHALL 使用 Milky schema 的字段名和值
- **AND** 只要取得远端响应体，Tool 调用方 SHALL 收到完整原始响应体及未知扩展字段

#### Scenario: 查询工具收到协议拒绝或非预期结构

- **WHEN** 查询 Action 返回协议拒绝、非成功 HTTP 状态、非 JSON 文本、JSON 数组、显式 `null` 或缺少历史最小字段的响应体
- **THEN** Tool 调用方 SHALL 收到该响应体的原始内容
- **AND** 工具 SHALL 不返回插件自有 `rejected`、`http_error` 或 `malformed` 替代结果，也不附加状态码

### Requirement: 状态变更工具只能由显式调用触发且不得盲目重试

`kick_group_member`、`quit_group`、`delete_friend`、`accept_friend_request` 和 `reject_friend_request`
MUST 只在对应 ToolSpec 被显式调用时执行。它们 MUST 分别调用同名 Milky Action，并使用 schema
定义的 body；不得由 `friend_request`、群通知、普通消息正文、关键词、Will 决策或其他事件自动
触发。请求进入 HTTP 边界后，只要取得远端响应体，工具 MUST 原样返回该响应体，不得按 HTTP
或协议状态重建、包装或替换结果；未取得远端响应体时，工具 MUST 返回 `transport_unknown`，
不得自动重发或把未知结果伪装成成功。

#### Scenario: 踢出群成员

- **WHEN** Agent 显式调用 `kick_group_member` 并提供合法群号、成员 QQ 号和可选拒绝加群申请标记
- **THEN** 工具 SHALL 调用 `/api/kick_group_member`
- **AND** 只要取得远端响应体，Tool 调用方 SHALL 收到该响应体的原始内容
- **AND** 系统 SHALL 不因该调用自动更新入站 Gate、群列表或其他本地状态

#### Scenario: 退出群或删除好友

- **WHEN** Agent 显式调用 `quit_group` 或 `delete_friend`
- **THEN** 工具 SHALL 只向对应的目标 Action 发送合法 ID
- **AND** SHALL 不回退到其他群、私聊或默认目标
- **AND** SHALL 不因普通文本或 observe-only 事件执行同一操作

#### Scenario: 接受或拒绝好友请求

- **WHEN** Agent 显式调用 `accept_friend_request` 或 `reject_friend_request`
- **THEN** 工具 SHALL 使用 `initiator_uid` 和可选过滤标记；拒绝工具还 SHALL 传递可选 `reason`
- **AND** 取得的远端响应体 SHALL 原样交给 Tool 调用方
- **AND** 系统 SHALL 不自动批准或拒绝任何收到的好友请求事件

#### Scenario: 状态变更请求未取得响应体

- **WHEN** 状态变更 Action 已进入 HTTP 请求边界但客户端未取得远端响应体
- **THEN** 工具 SHALL 返回 `transport_unknown`
- **AND** SHALL 只保留一次调用记录
- **AND** SHALL NOT 自动重试或返回成功结果

#### Scenario: 状态变更请求结果未知

- **WHEN** 状态变更 Action 已进入 HTTP 请求边界但客户端未取得可确认的完整响应
- **THEN** 工具 SHALL 返回 `transport_unknown`
- **AND** SHALL 只保留一次调用记录
- **AND** SHALL NOT 自动重试或返回成功结果

### Requirement: 工具必须统一处理生命周期、无响应分类和安全日志

所有新增工具 MUST 复用 Milky Action 的 Bearer 认证、`POST` JSON、path prefix 和显式操作映射。
工具 MUST 在网络前区分 `invalid_input` 与未绑定或已关闭的 `unsupported`，并在进入 HTTP 边界后
未取得远端响应体时返回 `transport_unknown`；只要取得响应体，插件 MUST 将其作为不透明结果原样
交付，不得根据 HTTP 状态、Milky envelope、`data` 结构或 JSON 可解析性返回 `rejected`、
`http_error`、`malformed` 或成功摘要。工具完成调用或得到本地/传输分类时，插件 SHALL 使用标准
logger 记录一个低基数的 `event=milky.tool` 结果事件，至少包含工具名称、已取得响应或固定失败
分类、已知 HTTP 状态码和 `duration_ms`；该日志不是 Tool 响应体的副本，其分类也不反映远端
成功与否。

日志和异常 MUST 不包含 token、Authorization header、原始响应 body、私聊文件下载 URL、媒体
URL、本地媒体路径、Tool 原始参数、自由文本理由或 traceback；响应体中的业务字段只交付给
Tool 调用方，不得被写入普通消息上下文或日志。

#### Scenario: HTTP 200 但协议拒绝

- **WHEN** 新增 Action 返回 HTTP 200 且 envelope 的 `status` 非 `ok` 或 `retcode` 非零
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** SHALL 不返回插件自有 `rejected` 分类或伪造空对象结果
- **AND** 日志 SHALL 只记录 Tool 名称、已取得响应分类、状态码和耗时

#### Scenario: 非成功 HTTP 状态

- **WHEN** 新增 Action 返回 4xx 或 5xx 状态及任意响应体
- **THEN** Tool 调用方 SHALL 收到该响应体的原始内容，结果中不附加状态码
- **AND** SHALL 不返回插件自有 `http_error` 分类
- **AND** 日志 SHALL 记录该状态码

#### Scenario: 响应缺少历史最小结构

- **WHEN** 查询响应缺少历史要求的字段、管理响应的 `data` 非空、响应体不是 JSON object 或不是 JSON
- **THEN** Tool 调用方 SHALL 收到该响应体的原始内容
- **AND** SHALL 不返回 `malformed` 替代结果或报告假成功
- **AND** SHALL 不记录响应 body 或缺失字段的原始内容

#### Scenario: 成功 data 结构缺失

- **WHEN** 查询工具成功 envelope 缺少历史要求的字段，或管理工具的 `data` 不是空对象
- **THEN** Tool 调用方 SHALL 收到已取得的原始响应体
- **AND** SHALL 不报告假成功或返回 `malformed` 替代结果

#### Scenario: 未连接或已关闭

- **WHEN** Agent 在工具 client 未绑定或已关闭时调用任一新增工具
- **THEN** 工具 SHALL 在网络访问前返回 `unsupported` 或既有传输不可用分类
- **AND** SHALL 不建立新连接、不发起 HTTP 请求
- **AND** 日志 MAY 记录工具名称和固定分类，但不得伪造远端状态码或结果

#### Scenario: 安全记录工具调用

- **WHEN** 新增工具完成一次调用或得到可分类失败
- **THEN** 日志 SHALL 只记录工具名称、固定结果分类、已知状态码、耗时和必要的低敏关联 ID
- **AND** SHALL 不记录 token、Authorization、完整响应 body、下载 URL、完整敏感理由、本地路径、原始参数或原始结果
### Requirement: `get_friend_info` 必须使用固定 operationId 和明确参数

插件 MUST 注册名为 `get_friend_info` 的异步 ToolSpec，使用 `milky` 工具集，并且只调用
`POST /api/get_friend_info`。工具 MUST 只接受必填的 `user_id: integer`；该值 MUST 是不含
布尔值、范围为 `10001` 至 `4294967295` 的 QQ 号。工具 MUST 拒绝缺失字段、错误类型、越界
值和额外字段，并在网络访问前返回 `invalid_input`；不得从好友名称、入站正文或当前会话推断
`user_id`。

#### Scenario: Hermes 发现好友信息工具

- **WHEN** Hermes 加载插件并读取显式 ToolSpec
- **THEN** 工具列表 SHALL 包含 `get_friend_info`
- **AND** 该工具 SHALL 使用 `milky` 工具集并绑定 `get_friend_info` operationId
- **AND** 注册阶段 SHALL 不发起 Milky HTTP 请求、SSE 连接或长期任务

#### Scenario: 好友信息请求使用精确 body

- **WHEN** Agent 以合法 `user_id` 调用 `get_friend_info`
- **THEN** 系统 SHALL 向保留 path prefix 的 `<base>/api/get_friend_info` 发送一次 `POST` JSON 请求
- **AND** 请求 body SHALL 只包含 `{ "user_id": <user_id> }`
- **AND** SHALL 不添加未由目标 operation 契约确认的可选字段或默认值

#### Scenario: 非法好友信息参数不触网

- **WHEN** Agent 缺少 `user_id`、传入布尔值、错误类型、范围外 QQ 号或未声明字段
- **THEN** 工具 SHALL 返回 `invalid_input`
- **AND** SHALL 不调用 Milky client、不发送 HTTP 请求且不记录远端结果

### Requirement: `get_friend_info` 必须原样交付远端响应体

`get_friend_info` 只要取得远端响应体，Tool 调用方 SHALL 收到其原始内容，无论 HTTP 状态、
协议状态、JSON 形状、空对象、数组、显式 `null` 或未知字段为何。由于当前公开 Milky v1.3
schema 未声明该 operation，插件不得擅自规定或改写好友资料内部字段；插件 MUST NOT 对响应体
执行 envelope 校验、业务字段校验、敏感字段过滤、容器转换、JSON 重建、摘要、状态码附加或
错误分类替换。查询结果不得自动写入普通入站上下文、本地好友状态或 Agent 指令。

#### Scenario: 返回好友资料对象和扩展字段

- **WHEN** 目标服务返回好友资料对象和扩展字段的响应体
- **THEN** Tool SHALL 收到完整原始响应体
- **AND** `data` 内的好友资料字段及未知扩展字段 SHALL 保持可用
- **AND** 插件 SHALL 不把结果改造成摘要、正文或本地缓存状态

#### Scenario: 查询结果结构未确认或损坏

- **WHEN** 响应体的 `data` 缺失、为 `null`、为数组或其他非 object，或响应体不是 JSON
- **THEN** 工具 SHALL 将已取得的响应体原样交给 Tool 调用方
- **AND** SHALL 不伪造好友资料、不补默认字段且不返回 `malformed` 替代结果

#### Scenario: HTTP 200 仍表示协议拒绝

- **WHEN** `get_friend_info` 返回协议拒绝、非成功 HTTP 状态或其他可取得的响应体
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** SHALL 不把 HTTP 状态码或协议状态改造成插件自有错误分类
