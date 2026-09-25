# Spec Delta

## MODIFIED Requirements

### Requirement: 状态变更工具只能由显式调用触发且不得盲目重试

`kick_group_member`、`quit_group`、`delete_friend`、`accept_friend_request` 和 `reject_friend_request`
MUST 只在对应 ToolSpec 被显式调用时执行；唯一新增例外是 kick_group_member 可由显式启用并满足 group-moderation 全部约束的案件流程执行。它们 MUST 分别调用同名 Milky Action，并使用 schema
定义的 body；不得由 `friend_request`、群通知、普通消息正文、关键词、Will 决策或其他事件自动
触发；上述群管案件流程必须先有本地命中、上下文复核及相应自动授权或 Web 批准，正文/关键词命中本身不授予执行权。请求进入 HTTP 边界后，只要取得远端响应体，工具 MUST 原样返回该响应体，不得按 HTTP
或协议状态重建、包装或替换结果；未取得远端响应体时，工具 MUST 返回 `transport_unknown`，
不得自动重发或把未知结果伪装成成功。

#### Scenario: 踢出群成员

- **WHEN** Agent 显式调用 `kick_group_member` 并提供合法群号、成员 QQ 号和可选拒绝加群申请标记，且可信上下文关联已获准的具体案件方案、实时权限检查通过
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

#### Scenario: 踢人直接调用未获业务授权

- **WHEN** kick_group_member 参数合法，但缺少可信案件关联、参数不匹配或群管权限不足
- **THEN** 工具 SHALL 在 Action 前返回 blocked，不因为显式工具调用或宿主通用放行而执行

#### Scenario: 踢人方案等待 Web 审批

- **WHEN** 可信关联的合法踢人方案尚需 Web 批准
- **THEN** 工具 SHALL 立即返回 pending_review 和不透明案件标识，不阻塞等待、不在 QQ 请求批准

### Requirement: 工具必须统一处理生命周期、无响应分类和安全日志

所有新增工具 MUST 复用 Milky Action 的 Bearer 认证、`POST` JSON、path prefix 和显式操作映射。
kick_group_member MUST 额外遵守群管业务执行检查，可在处置 Action 前返回 blocked 或 pending_review；该本地结果不是远端响应分类，不得伪造执行成功。
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
- **THEN** 工具 SHALL 在网络访问前返回 `unsupported`
- **AND** SHALL 不建立新连接、不发起 HTTP 请求
- **AND** 日志 MAY 记录工具名称和固定分类，但不得伪造远端状态码或结果

#### Scenario: 安全记录工具调用

- **WHEN** 新增工具完成一次调用或得到可记录的本地/传输结果
- **THEN** 日志 SHALL 只记录工具名称、低基数结果分类、已知状态码、耗时和必要的低敏关联 ID
- **AND** SHALL 不记录 token、Authorization、完整响应 body、下载 URL、完整敏感理由、本地路径、原始参数或原始结果

#### Scenario: 未连接或未取得响应

- **WHEN** Agent 在工具 client 未绑定或已关闭时调用任一新增工具，或请求进入 HTTP 边界后未取得远端响应体
- **THEN** 工具 SHALL 分别返回 `unsupported` 或 `transport_unknown`
- **AND** SHALL 不建立新连接、不自动重试、不伪造远端状态码或结果
- **AND** 日志 MAY 记录工具名称和固定分类
