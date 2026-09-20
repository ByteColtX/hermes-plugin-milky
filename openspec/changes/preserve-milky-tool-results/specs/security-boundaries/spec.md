# Spec Delta

## MODIFIED Requirements

### Requirement: 业务日志和 Tool 调用日志保留原始业务值

运行时日志 MUST NOT 对必要的业务关联 ID、chat key、message ID 或结果分类执行会破坏关联的
掩码、改名或字段删除；这些值只在确实有助于运维关联时记录。已注册 Tool 的日志 SHALL 只
包含 Tool 名称、Action、结果分类、已知 HTTP 状态码、耗时和必要的低敏关联 ID，不得包含
Tool 原始入参或为生成日志而复制的业务对象。只要远端响应体已经取得，Tool 调用方 SHALL
收到该响应体的原始内容，无论其 HTTP 状态、协议状态、JSON 形状、字段名、数组、显式
`null` 或未知字段为何；插件 MUST NOT 因日志、安全判断或结果分类过滤、遍历、冻结、重建、
摘要或改写该响应体。该边界 MUST 排除 token、Authorization header、原始响应 body、下载 URL、
头像或其他媒体 URL、本地路径、文件内容以及自由文本理由出现在日志中。

#### Scenario: 记录业务关联信息

- **WHEN** 日志需要关联合法的 chat key、message ID、Action、分类或状态码
- **THEN** 日志 SHALL 保留足以定位边界的原始低敏值
- **AND** SHALL 不通过通用掩码或摘要改写这些值

#### Scenario: 记录包含敏感字段和未知字段的 Tool 响应

- **WHEN** Tool 收到包含 `token`、`authorization`、数组、显式 `null` 和未知字段的远端响应体
- **THEN** Tool 调用方 SHALL 收到与远端响应体内容一致的结果
- **AND** 日志 SHALL 只记录 Tool 名称、结果分类、已知状态码和耗时
- **AND** 日志 SHALL NOT 记录响应体、token、Authorization、下载 URL、媒体 URL 或本地路径

#### Scenario: 记录 Tool 调用

- **WHEN** `get_private_file_download_url` 或其他 Tool 返回包含下载 URL、媒体 URL 或未知扩展字段的响应体
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** 日志 SHALL 只记录 Tool 名称、结果分类、已知状态码和耗时
- **AND** 日志 SHALL NOT 记录下载 URL、媒体 URL、完整响应 body、token、Authorization 或本地路径

#### Scenario: 记录带自由文本参数的 Tool 调用

- **WHEN** `reject_friend_request` 携带可选 `reason` 完成调用
- **THEN** Tool 调用方 SHALL 按 raw passthrough 契约收到远端响应体或无响应固定分类
- **AND** 日志 SHALL NOT 记录完整 `reason` 文本、底层异常正文或 Tool 参数对象

#### Scenario: 记录远端拒绝或 HTTP 错误响应

- **WHEN** 远端以协议拒绝或非成功 HTTP 状态返回响应体
- **THEN** Tool 调用方 SHALL 收到该响应体的原始内容
- **AND** 插件 SHALL 不把该响应体转换为 `rejected`、`http_error` 或其他固定 Tool 结果
- **AND** 日志 SHALL 只记录低基数的远端响应分类和已知状态码

#### Scenario: Tool 没有远端结果

- **WHEN** Tool 参数校验失败、Action 未注册、client 已关闭或传输未取得远端响应体
- **THEN** Tool SHALL 返回既有固定错误分类
- **AND** SHALL 不伪造远端成功结果
- **AND** 日志 MAY 记录 Tool 名称和固定失败分类，但不得记录未确认的原始结果

### Requirement: QQ Tool 成功结果原样交付

已注册 Tool 只要取得远端响应体，就 MUST 原样返回给当前 Tool 调用方，保留完整响应内容、
未知字段和业务字段值；该规则适用于成功、协议拒绝、HTTP 错误、非对象 JSON、数组、显式
`null`、文本和其他可获得的响应体。插件 MUST NOT 将该结果改造成摘要 DTO、插件状态或固定
错误，也不得为了生成日志而过滤、遍历、冻结、复制、重构或摘要该结果。

#### Scenario: Tool 返回任意可获得的远端响应

- **WHEN** 已注册 Tool 的远端 Action 返回任意 HTTP 状态和响应体
- **THEN** Tool 调用方 SHALL 收到内容不变的远端响应体
- **AND** 结果中的数组、显式 `null`、未知字段和敏感字段 SHALL 保持可用
- **AND** 日志 SHALL NOT 记录入参、结果 body、下载 URL 或媒体字段

#### Scenario: Tool 返回成功协议结果

- **WHEN** 已注册 Tool 的远端 Action 返回成功协议结果
- **THEN** Tool 调用方 SHALL 收到未重构的原始协议结果
- **AND** 日志 MAY 记录该调用的 Tool 名称、固定结果分类、状态码和耗时
- **AND** 日志 SHALL NOT 记录入参、结果 body、下载 URL 或媒体字段

#### Scenario: 远端响应体不是预期 envelope

- **WHEN** 远端响应体是 malformed JSON、JSON 数组、JSON 标量或未知 envelope
- **THEN** Tool SHALL 仍将已取得的响应体原样交给 Tool 调用方
- **AND** SHALL 不将其归类为插件自有 `malformed` 结果或补造 envelope

#### Scenario: Tool 没有远端结果

- **WHEN** 参数校验失败、Action 未注册或传输没有取得远端响应体
- **THEN** Tool SHALL 返回既有固定错误分类
- **AND** SHALL 不伪造远端成功结果
- **AND** 日志是否存在 SHALL 不改变该结果
