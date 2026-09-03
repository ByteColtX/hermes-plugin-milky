## MODIFIED Requirements

### Requirement: 业务日志和 Tool 调用日志保留原始业务值

运行时日志 MUST NOT 对普通业务 ID、chat key、message ID、昵称或非敏感 Tool 调用业务字段执行掩码、摘要、改名或字段删除。已注册 Tool 的调用日志 SHALL 包含 Tool 名称、可安全记录的调用入参和远端结果的安全投影；该投影 MUST 排除 token、Authorization header、原始响应 body、下载 URL、头像或其他媒体 URL、本地路径、文件内容以及自由文本理由。认证 header 和 HTTP transport 上下文不属于 Tool 入参或结果。Tool 调用方收到成功结果时，仍 SHALL 取得现有 Tool raw envelope 契约规定的完整协议结果；日志安全投影不得改变交付结果。

#### Scenario: 记录业务关联信息

- **WHEN** 日志记录合法的业务关联字段或非敏感工具参数
- **THEN** 日志 SHALL 保留该字段的原始值
- **AND** SHALL 不通过通用掩码、摘要或改名改写该值

#### Scenario: 记录 Tool 调用

- **WHEN** `get_private_file_download_url` 或其他 Tool 返回包含下载 URL、媒体 URL 或未知扩展字段的成功 envelope
- **THEN** Tool 调用方 SHALL 收到完整原始成功 envelope
- **AND** 日志 SHALL 记录 Tool 名称和必要的安全业务关联信息
- **AND** 日志 SHALL NOT 记录下载 URL、媒体 URL、完整响应 body、token、Authorization 或本地路径

#### Scenario: 记录带自由文本参数的 Tool 调用

- **WHEN** `reject_friend_request` 携带可选 `reason` 完成调用
- **THEN** Tool 调用方 SHALL 按既有 raw envelope 契约收到远端结果或固定错误分类
- **AND** 日志 SHALL NOT 记录完整 `reason` 文本或底层异常正文

#### Scenario: Tool 没有远端结果

- **WHEN** Tool 参数校验失败、Action 未注册或远端没有可确认响应
- **THEN** Tool SHALL 返回既有固定错误分类
- **AND** SHALL 不伪造远端成功结果
