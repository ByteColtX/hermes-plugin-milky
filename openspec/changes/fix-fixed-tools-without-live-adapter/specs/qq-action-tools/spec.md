# Spec Delta

## MODIFIED Requirements

### Requirement: 工具必须统一处理生命周期、无响应分类和安全日志

本工具组中的所有工具 MUST 复用 Milky Action 的 Bearer 认证、`POST` JSON、path prefix 和显式操作映射。
工具 MUST 优先复用当前进程已绑定的 live client；当进程内没有 live adapter 绑定的 client（例如
Hermes cron 的独立进程）时，工具 MUST 按调用时 profile 配置创建一次性的 Milky client 和 sender，
执行本次 Action 后在 `finally` 中关闭这些资源，且 MUST NOT 缓存、复用或重试该连接。工具 MUST 在
网络前区分 `invalid_input` 与配置不可读的 `unsupported`，并在进入 HTTP 边界后未取得远端响应体时
返回 `transport_unknown`；只要取得响应体，插件 MUST 将其作为不透明结果原样交付，不得根据 HTTP
状态、Milky envelope、`data` 结构或 JSON 可解析性返回 `rejected`、`http_error`、`malformed` 或成功
摘要。工具完成调用或得到本地/传输分类时，插件 SHALL 使用标准 logger 记录一个低基数的
`event=milky.tool` 结果事件，至少包含工具名称、已取得响应或固定失败分类、已知 HTTP 状态码和
`duration_ms`；该日志不是 Tool 响应体的副本，其分类也不反映远端成功与否。

日志和异常 MUST 不包含 token、Authorization header、原始响应 body、私聊文件下载 URL、媒体
URL、本地媒体路径、Tool 原始参数、自由文本理由或 traceback；响应体中的业务字段只交付给
Tool 调用方，不得被写入普通消息上下文或日志。

#### Scenario: HTTP 200 但协议拒绝

- **WHEN** 对应 Action 返回 HTTP 200 且 envelope 的 `status` 非 `ok` 或 `retcode` 非零
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** SHALL 不返回插件自有 `rejected` 分类或伪造空对象结果
- **AND** 日志 SHALL 只记录 Tool 名称、已取得响应分类、状态码和耗时

#### Scenario: 非成功 HTTP 状态

- **WHEN** 对应 Action 返回 4xx 或 5xx 状态及任意响应体
- **THEN** Tool 调用方 SHALL 收到该响应体的原始内容，结果中不附加状态码
- **AND** SHALL 不返回插件自有 `http_error` 分类
- **AND** 日志 SHALL 记录该状态码

#### Scenario: 响应缺少历史最小结构

- **WHEN** 查询响应缺少历史要求的字段、管理响应的 `data` 不是空对象、响应体不是 JSON object 或不是 JSON
- **THEN** Tool 调用方 SHALL 收到该响应体的原始内容
- **AND** SHALL 不返回 `malformed` 替代结果或报告假成功
- **AND** SHALL 不记录响应 body 或缺失字段的原始内容

#### Scenario: 进程内没有 live adapter

- **WHEN** Agent 在网关进程外（例如 Hermes cron 的独立 worker）调用本工具组中任一工具
- **THEN** 工具 SHALL 按调用时 profile 配置创建一次性 client 与 sender，并且只发起一次 HTTP 请求
- **AND** SHALL 在成功、协议拒绝、传输失败或取消后关闭该次 client 与 sender
- **AND** SHALL NOT 复用该连接、发起额外重试或把连接保存在进程级状态中

#### Scenario: 一次性 client 的配置不可读

- **WHEN** 进程内没有 live client，且运行时 profile 配置无法解析
- **THEN** 工具 SHALL 在网络访问前返回 `unsupported`
- **AND** SHALL 不创建 client、不发起 HTTP 请求
- **AND** 日志 MAY 记录工具名称和固定分类，但不得伪造远端状态码或结果

#### Scenario: 安全记录工具调用

- **WHEN** 本工具组完成一次调用或得到可记录的本地/传输结果
- **THEN** 日志 SHALL 只记录工具名称、低基数结果分类、已知状态码、耗时和必要的低敏关联 ID
- **AND** SHALL 不记录 token、Authorization、完整响应 body、下载 URL、完整敏感理由、本地路径、原始参数或原始结果
