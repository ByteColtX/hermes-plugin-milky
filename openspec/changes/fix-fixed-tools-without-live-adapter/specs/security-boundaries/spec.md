# Spec Delta

## MODIFIED Requirements

### Requirement: 业务日志和 Tool 调用日志保留原始业务值

运行时日志 MUST NOT 对必要的业务关联 ID、chat key、message ID 或结果分类执行会破坏关联的
掩码、改名或字段删除；这些值只在确实有助于运维关联时记录。下列调用日志规则适用于固定目录中的 Milky Action Tool；语义贴纸工具遵循各自规范及上述日志最小化边界。Action Tool 的日志 SHALL 只
包含 Tool 名称、Action、结果分类、已知 HTTP 状态码、耗时和必要的低敏关联 ID，不得包含
Tool 原始入参或为生成日志而复制的业务对象。Tool 的日志分类 SHALL 只反映是否取得远端响应体
以及本地失败类型，不得反映远端成功、拒绝或响应形状。Tool 结果 SHALL 遵守下文“QQ Tool 远端响应原样交付”，日志生成不得改变交付内容。该边界 MUST 排除 token、Authorization header、原始响应 body、
下载 URL、头像或其他媒体 URL、本地路径、文件内容以及自由文本理由出现在日志中。

#### Scenario: 记录业务关联信息

- **WHEN** 日志需要关联合法的 chat key、message ID、Action、分类或状态码
- **THEN** 日志 SHALL 保留足以定位边界的原始低敏值
- **AND** SHALL 不通过通用掩码或摘要改写这些值

#### Scenario: 记录 Tool 调用

- **WHEN** `get_private_file_download_url` 或其他 Tool 返回包含下载 URL、媒体 URL 或未知扩展字段的响应体
- **THEN** Tool 调用方 SHALL 收到完整原始响应体
- **AND** 日志 SHALL 只记录 Tool 名称、结果分类、已知状态码和耗时
- **AND** 日志 SHALL NOT 记录下载 URL、媒体 URL、完整响应 body、token、Authorization 或本地路径

#### Scenario: 记录带自由文本参数的 Tool 调用

- **WHEN** `reject_friend_request` 携带可选 `reason` 完成调用
- **THEN** Tool 调用方 SHALL 收到远端响应体或无响应固定分类
- **AND** 日志 SHALL NOT 记录完整 `reason` 文本、底层异常正文或 Tool 参数对象

#### Scenario: Tool 没有远端结果

- **WHEN** Tool 参数校验失败、Action 未注册、一次性 client 的运行时配置不可读，或传输未取得远端响应体
- **THEN** Tool SHALL 返回既有固定错误分类
- **AND** SHALL 不伪造远端成功结果
- **AND** 日志 MAY 记录 Tool 名称和固定失败分类，但不得记录未确认的原始结果

#### Scenario: 无 live adapter 的进程记录 Tool 调用

- **WHEN** 工具在没有 live adapter 的进程中通过一次性 client 完成调用或得到固定失败分类
- **THEN** 日志 SHALL 只记录 Tool 名称、结果分类、已知状态码和耗时
- **AND** SHALL NOT 记录 token、Authorization、响应 body、目标 QQ 号、本地路径或一次性 client 的配置值

#### Scenario: 记录包含敏感字段和未知字段的 Tool 响应

- **WHEN** Tool 收到在顶层或嵌套层级包含 `access_token`、`authorization`、`cookie`、`password`、`token`（任意大小写）、数组、显式 `null` 和未知字段的远端响应体
- **THEN** Tool 调用方 SHALL 收到与远端响应体内容一致的结果
- **AND** 日志 SHALL 只记录 Tool 名称、已取得响应的分类、已知状态码和耗时
- **AND** 日志 SHALL NOT 记录响应体、token、Authorization、下载 URL、媒体 URL 或本地路径

#### Scenario: 记录远端拒绝或 HTTP 错误响应

- **WHEN** 远端以协议拒绝或非成功 HTTP 状态返回响应体
- **THEN** Tool 调用方 SHALL 收到该响应体的原始内容
- **AND** 日志 SHALL 使用与成功响应相同的已取得响应分类，并附带已知状态码
- **AND** 日志 SHALL NOT 出现 `rejected`、`http_error` 或 `malformed` 等远端语义分类
