## MODIFIED Requirements

### Requirement: 诊断不泄露秘密和不必要内容

日志、异常、SendResult、fixture、快照和执行记录 MUST 不包含 token、Authorization header、个人 QQ、真实媒体路径和敏感正文；诊断至少可以包含脱敏的 chat key、message ID 和错误类别。Milky 日志消息 SHALL 使用 Hermes-agent 风格的 `[Milky] ` 前缀和安全级别，但不得为了模拟该风格输出原始异常、请求参数或响应正文。结构化字段 SHALL 只包含经过白名单化的阶段、事件名、场景、错误分类、计数、耗时和脱敏关联标识。人类可读日志 SHALL 只使用固定事件标签和一次统一前缀；动态值不得通过自由文本消息绕过字段白名单或脱敏器。

#### Scenario: 认证失败

- **WHEN** Milky 因认证失败或网络错误返回异常
- **THEN** 用户可见诊断 SHALL 只包含脱敏的错误类别，并以 `[Milky] ` 风格记录
- **AND** SHALL 不包含 token 或完整认证 header

#### Scenario: 业务消息诊断

- **WHEN** 记录消息处理失败
- **THEN** 诊断 SHALL 优先记录脱敏 chat key、message ID、reason 和安全错误类别
- **AND** SHALL 不默认记录完整正文或媒体 URL
- **AND** SHALL 不因使用 Hermes-agent 风格而放宽正文、路径或 QQ/群号脱敏边界

#### Scenario: 动态消息和同义字段

- **WHEN** 日志调用把未脱敏数字 ID、动态 `key=value`、nickname、状态或第二个 `[Milky]` 前缀拼入人类可读消息
- **THEN** 系统 SHALL 拒绝该自由文本或改由规范字段安全渲染
- **AND** 同一身份、状态或计数 SHALL 不得同时通过同义字段重复输出
- **AND** 人类消息与结构化字段 SHALL 使用同一份脱敏结果

#### Scenario: 异常链和 traceback

- **WHEN** 本地异常包含 cause、context、notes、路径、凭证、远端响应或敏感正文
- **THEN** 诊断 SHALL 只记录固定 classification/reason，不得直接输出异常链或 traceback
- **AND** 只有完整安全检查通过且不会输出本地路径的本地异常才可带 traceback

#### Scenario: 运行时日志调用点审计

- **WHEN** 审计 adapter、Milky client、SSE、inbound、resource、outbound、MuteTracker 和 smoke CLI 的输出
- **THEN** 运行时日志 SHALL 全部使用固定事件和白名单字段
- **AND** 不得存在直接的非结构化 logger 输出、原始异常文本或未经登记的 event name
- **AND** smoke CLI 的机器可读 stdout SHALL 保持独立并不得包含凭证、正文、URL 或路径
