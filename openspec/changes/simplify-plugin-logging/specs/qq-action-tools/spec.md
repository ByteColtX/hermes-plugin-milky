## MODIFIED Requirements

### Requirement: 工具必须统一处理生命周期、协议错误和安全日志

所有新增工具 MUST 复用 Milky Action 的 Bearer 认证、`POST` JSON、path prefix、envelope 和错误分类边界。工具 MUST 区分 `invalid_input`、`rejected`、`http_error`、`malformed`、`transport_unknown` 和 `unsupported`；HTTP 200 且 Milky envelope 失败不得视为成功。未绑定或已关闭的工具 client MUST 在网络访问前返回 `unsupported` 或既有传输不可用分类。工具完成调用或得到可分类失败时，插件 SHALL 使用标准 logger 记录一个低基数的 `event=milky.tool` 结果事件，至少包含工具名称、结果分类、已知 HTTP 状态码和 `duration_ms`；该日志不是 Tool raw envelope 的副本。

日志和异常 MUST 不包含 token、Authorization header、原始响应 body、私聊文件下载 URL、媒体 URL、本地媒体路径、Tool 原始参数、自由文本理由或 traceback；成功 envelope 中的业务字段只交付给 Tool 调用方，不得被写入普通消息上下文或日志。

#### Scenario: HTTP 200 但协议拒绝

- **WHEN** 新增 Action 返回 HTTP 200 且 envelope 的 `status` 非 `ok` 或 `retcode` 非零
- **THEN** 工具 SHALL 返回 `rejected`
- **AND** SHALL 记录 `event=milky.tool`、工具名称、`rejected`、状态码和耗时
- **AND** SHALL NOT 返回成功 envelope 或伪造空对象结果

#### Scenario: 成功 data 结构缺失

- **WHEN** 查询工具成功 envelope 缺少其要求的 `messages`、`download_url` 或 `requests`，或管理工具的 data 不是确认的空对象
- **THEN** 工具 SHALL 返回 `malformed`
- **AND** SHALL 记录 `malformed` 分类，但不得记录响应 body 或缺失字段的原始内容
- **AND** SHALL 不报告假成功

#### Scenario: 未连接或已关闭

- **WHEN** Agent 在工具 client 未绑定或已关闭时调用任一新增工具
- **THEN** 工具 SHALL 在网络访问前返回 `unsupported` 或既有传输不可用分类
- **AND** SHALL 不建立新连接、不发起 HTTP 请求
- **AND** 日志 MAY 记录工具名称和固定分类，但不得伪造远端状态码或结果

#### Scenario: 安全记录工具调用

- **WHEN** 新增工具完成一次调用或得到可分类失败
- **THEN** 日志 SHALL 只记录工具名称、固定结果分类、已知状态码、耗时和必要的低敏关联 ID
- **AND** SHALL 不记录 token、Authorization、完整响应 body、下载 URL、完整敏感理由、本地路径、原始参数或原始结果
