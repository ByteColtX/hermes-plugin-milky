## MODIFIED Requirements

### Requirement: Home channel 投递失败必须诚实且安全

home channel 投递 MUST 在目标和内容校验后才访问网络；远端拒绝、响应结构错误或执行结果未知 SHALL 原样保留既有安全分类，不得伪造成功或盲目重试可能产生副作用的请求。插件 SHALL 使用标准 logger 记录成功、失败或未知结果的 `event=milky.outbound` 诊断，至少包含目标类型、结果分类、已知 HTTP 状态码和 `duration_ms`；日志、错误和结果 MUST 不包含 token、Authorization header、完整媒体 URL、本地路径、消息正文、文件内容或未脱敏真实身份。

#### Scenario: home channel 发送成功

- **WHEN** Milky send Action 成功返回 `data.message_seq`
- **THEN** Hermes SHALL 获得该远端序号的稳定字符串消息 ID
- **AND** SHALL 记录 home channel 出站成功、目标类型和耗时，但不得记录系统消息正文或响应 body
- **AND** SHALL 不使用本地时间、随机值或固定假 ID

#### Scenario: home channel 远端拒绝

- **WHEN** Milky 返回 HTTP 200 但 envelope 表示失败
- **THEN** 投递 SHALL 返回 `rejected`
- **AND** SHALL 记录 `event=milky.outbound`、`rejected`、状态码和耗时
- **AND** SHALL 不把系统消息标记为成功或自动改投其他 chat

#### Scenario: home channel 传输结果未知

- **WHEN** standalone 或 live 投递发生超时、连接错误或其他无法确认执行结果的传输错误
- **THEN** 投递 SHALL 返回 `transport_unknown`
- **AND** SHALL 记录 `transport_unknown`、传输阶段、耗时和必要的目标类型
- **AND** 默认 SHALL 不自动重复发送同一系统消息
- **AND** SHALL 不记录底层异常正文、凭证、URL 或消息内容
