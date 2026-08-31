## MODIFIED Requirements

### Requirement: 诊断不泄露秘密和不必要内容

日志和诊断 SHALL 保留事件契约允许的业务值，不对业务 ID、chat key、message ID、昵称或已注册 Tool 的调用入参和远端结果做掩码。已注册 Tool 的专用调用日志 SHALL 记录 Tool 名称、调用入参和远端结果；认证 header 和 HTTP transport 上下文不属于 Tool 日志字段。普通日志仍使用已有固定事件和错误分类，不通过任意对象日志扩大范围。

#### Scenario: 认证失败

- **WHEN** Milky 因认证失败或网络错误返回异常
- **THEN** 用户可见诊断 SHALL 只包含既有错误分类
- **AND** SHALL 不把认证 header 作为日志字段或错误文本

#### Scenario: 业务消息诊断

- **WHEN** 记录消息处理失败
- **THEN** 诊断 SHALL 按事件契约记录原始业务关联字段
- **AND** SHALL 不通过通用掩码改写业务 ID、chat key、message ID 或昵称

#### Scenario: 动态消息和同义字段

- **WHEN** 普通日志调用把未登记的动态对象或 `key=value` 拼入人类可读消息
- **THEN** 系统 SHALL 拒绝该自由字段或改由已有日志字段输出
- **AND** 已注册 Tool 的专用日志 SHALL 例外记录其调用入参和远端结果

#### Scenario: 异常链和 traceback

- **WHEN** 本地异常包含 cause、context、notes、路径、远端响应或敏感正文
- **THEN** 诊断 SHALL 只记录既有固定 classification/reason
- **AND** SHALL 不直接输出异常链、traceback 或原始异常文本

#### Scenario: 运行时日志调用点审计

- **WHEN** 审计 adapter、Milky client、SSE、inbound、resource、outbound、MuteTracker 和 smoke CLI 的输出
- **THEN** 普通运行时日志 SHALL 使用已有固定事件和字段
- **AND** 已注册 Tool 日志 SHALL 额外包含调用入参和远端结果，不做摘要、改名、掩码或未知业务字段删除
