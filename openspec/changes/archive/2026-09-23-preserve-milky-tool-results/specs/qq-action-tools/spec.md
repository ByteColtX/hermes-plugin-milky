# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: 查询工具必须返回经过协议校验的完整成功 envelope`
- TO: `### Requirement: 查询工具必须原样交付远端响应体`

- FROM: `### Requirement: 工具必须统一处理生命周期、协议错误和安全日志`
- TO: `### Requirement: 工具必须统一处理生命周期、无响应分类和安全日志`

- FROM: `### Requirement: `get_friend_info` 必须保留经过校验的完整查询结果`
- TO: `### Requirement: `get_friend_info` 必须原样交付远端响应体`

## MODIFIED Requirements

### Requirement: 查询工具必须原样交付远端响应体

`get_forwarded_messages`、`get_private_file_download_url` 和 `get_friend_requests` MUST 分别调用
对应 Milky Action。插件对这些 Tool 的响应路径 MUST 只在网络前校验参数和在传输层确认是否
取得响应体；一旦取得远端响应体，Tool 调用方 SHALL 收到其原始内容，无论 HTTP 状态、协议
状态、JSON 形状、数组、显式 `null` 或未知字段为何。插件 MUST NOT 对响应体执行 envelope
校验、业务字段校验、敏感字段过滤、容器转换、JSON 重建、摘要、状态码附加或错误分类替换，
也不得把结果写入普通入站上下文。

#### Scenario: 查询合并转发消息

- **WHEN** Agent 以合法 `forward_id` 调用 `get_forwarded_messages`，远端返回包含数组和扩展字段的响应体
- **THEN** 请求 SHALL 使用 `POST /api/get_forwarded_messages` 和 `{ "forward_id": "<forward-id>" }`
- **AND** Tool 调用方 SHALL 收到响应体中的完整数组、扩展字段和其他内容
- **AND** 工具 SHALL 不把转发内容自动注入当前 Hermes turn

#### Scenario: 查询私聊文件下载链接

- **WHEN** Agent 提供合法 `user_id`、`file_id`、`file_hash` 以及可选 `is_self_send`，远端返回包含下载链接的响应体
- **THEN** 请求 SHALL 使用 `POST /api/get_private_file_download_url`
- **AND** Tool 调用方 SHALL 收到包含该链接及未知字段的原始响应体
- **AND** 插件 SHALL 不在工具调用中下载、缓存、解码、过滤或改写该 URL

#### Scenario: 查询工具收到协议拒绝或非预期结构

- **WHEN** 查询 Action 返回协议拒绝、非成功 HTTP 状态、非 JSON 文本、JSON 数组、显式 `null` 或缺少历史最小字段的响应体
- **THEN** Tool 调用方 SHALL 收到该响应体的原始内容
- **AND** 工具 SHALL 不返回插件自有 `rejected`、`http_error` 或 `malformed` 替代结果，也不附加状态码

#### Scenario: 查询好友请求

- **WHEN** Agent 调用 `get_friend_requests` 并提供可选的 `limit` 或 `is_filtered`
- **THEN** 请求 SHALL 使用 Milky schema 的字段名和值
- **AND** 只要取得远端响应体，Tool 调用方 SHALL 收到完整原始响应体及未知扩展字段

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
- **AND** 系统 SHALL 不因该调用自动更新入站 Gate、群列表、禁言快照或其他本地状态

#### Scenario: 退出群或删除好友

- **WHEN** Agent 显式调用 `quit_group` 或 `delete_friend`
- **THEN** 工具 SHALL 只向对应的目标 Action 发送合法 ID
- **AND** 取得的远端响应体 SHALL 原样交给 Tool 调用方
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

- **WHEN** 状态变更 Action 的请求已发出，但连接中断、超时或读取失败导致远端是否执行未知
- **THEN** 工具 SHALL 返回 `transport_unknown`
- **AND** SHALL 不把未知结果伪装成成功或远端拒绝

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

#### Scenario: 未连接或未取得响应

- **WHEN** Agent 在工具 client 未绑定或已关闭时调用任一新增工具，或请求进入 HTTP 边界后未取得远端响应体
- **THEN** 工具 SHALL 分别返回 `unsupported` 或 `transport_unknown`
- **AND** SHALL 不建立新连接、不自动重试、不伪造远端状态码或结果
- **AND** 日志 MAY 记录工具名称和固定分类

#### Scenario: 未连接或已关闭

- **WHEN** Agent 在工具 client 未绑定或已关闭时调用任一新增工具
- **THEN** 工具 SHALL 在网络访问前返回 `unsupported`
- **AND** SHALL 不建立新连接、不发起 HTTP 请求
- **AND** 日志 MAY 记录工具名称和固定分类，但不得伪造远端状态码或结果

#### Scenario: 安全记录工具调用

- **WHEN** 新增工具完成一次调用或得到可记录的本地/传输结果
- **THEN** 日志 SHALL 只记录工具名称、低基数结果分类、已知状态码、耗时和必要的低敏关联 ID
- **AND** SHALL 不记录 token、Authorization、完整响应 body、下载 URL、完整敏感理由、本地路径、原始参数或原始结果

### Requirement: `get_friend_info` 必须原样交付远端响应体

`get_friend_info` MUST 向 Tool 调用方返回远端响应体的完整原始内容。插件只允许在网络访问前
校验 `user_id` 和在传输层确认是否取得响应体；不得擅自规定或改写好友资料内部字段，也不得对
响应体执行 envelope/data 校验、敏感字段过滤、容器转换、JSON 重建或本地状态投影。只要取得
响应体，即使其表示协议失败、HTTP 错误、`data` 缺失、为 `null`、为数组或不是 object，工具也
MUST 原样交付；未取得响应体时才返回既有传输分类。查询结果不得自动写入普通入站上下文、
本地好友状态或 Agent 指令。

#### Scenario: 返回好友资料对象和扩展字段

- **WHEN** 目标服务返回包含好友资料和未知扩展字段的响应体
- **THEN** Tool SHALL 收到完整原始响应体
- **AND** `data` 内的好友资料字段及未知扩展字段 SHALL 保持可用
- **AND** 插件 SHALL 不把结果改造成摘要、正文或本地缓存状态

#### Scenario: 查询结果结构未确认或损坏

- **WHEN** `get_friend_info` 返回的响应体缺少 `data`、为 `null`、为数组、为标量或不是合法 envelope
- **THEN** 工具 SHALL 将已取得的响应体原样交给 Tool 调用方
- **AND** SHALL 不伪造好友资料、不补默认字段且不返回插件自有 `malformed`

#### Scenario: HTTP 200 仍表示协议拒绝

- **WHEN** `get_friend_info` 返回 HTTP 200 但 envelope 的 `status` 非 `ok` 或 `retcode` 非零
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** SHALL 不把 HTTP 状态码或协议状态改写成查询成功或固定拒绝结果
