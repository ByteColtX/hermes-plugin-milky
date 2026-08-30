## MODIFIED Requirements

### Requirement: 断线重连和取消可控

事件流 MUST 在可重试断线后按既有退避策略重连，并支持取消；断开时 SHALL 释放 reader、HTTP response、客户端和定时器资源。每次已建立的 SSE 连接意外终止时，系统 MUST 记录一条英文 `milky_event_stream_disconnected` 日志；每次退避重连前 MUST 记录一条英文 `milky_event_stream_reconnect_scheduled` 日志，退避结束后 MUST 记录一条英文 `milky_event_stream_reconnect_attempt` 日志，重连成功后 MUST 记录一条英文 `milky_event_stream_reconnected` 日志。重连日志 MUST 提供 1-based 尝试序号、实际退避等待秒数（适用于 scheduled）和安全原因类别；断连日志至少 MUST 提供安全原因类别。日志中的原因只能使用预定义的 `eof`、`connection_error`、`timeout`、`http_error`、`protocol_error`、`stream_error` 或 `unknown` 分类值，不得包含 token、Authorization、完整 URL、原始异常文本、消息正文、媒体 URL 或本地媒体路径。

`reconnect_attempt` 序号 MUST 从一次连接异常结束或连接建立失败后的第一轮新连接开始按 1 递增；`delay_seconds` MUST 表示对应重连尝试前实际采用的退避等待秒数。主动停止或取消时 MUST 记录一次英文取消日志，不得将取消误报为异常断连，不得继续等待退避或发起新的连接请求。

#### Scenario: 可恢复断线

- **WHEN** 已建立的 SSE 连接意外以 EOF、读取连接错误、超时或协议级连接错误结束
- **THEN** 消费者 SHALL 记录 `milky_event_stream_disconnected` 英文日志和安全 `reason`
- **AND** SHALL 按配置退避后重新建立 `/event` 连接
- **AND** SHALL 不假设断线期间丢失事件会被服务端恢复

#### Scenario: 连接建立失败

- **WHEN** 一次待重连的 `/event` 连接因连接错误、超时或 HTTP 错误而未建立成功
- **THEN** 消费者 SHALL 记录该次 `milky_event_stream_reconnect_attempt` 和下一次 `milky_event_stream_reconnect_scheduled` 所需的安全 `reason`
- **AND** SHALL 不为从未建立的连接伪造 `milky_event_stream_disconnected` 日志
- **AND** SHALL 继续按退避策略尝试连接

#### Scenario: 退避等待和实际重连可观测

- **WHEN** 消费者为第 1 次或后续重连安排退避
- **THEN** SHALL 在等待前记录 `milky_event_stream_reconnect_scheduled`，包含 1-based `attempt`、`delay_seconds` 和安全 `reason`
- **AND** 退避结束后 SHALL 记录 `milky_event_stream_reconnect_attempt`，包含相同的 `attempt`
- **AND** SHALL 使用该重连尝试建立同一 `/event` 端点，不得在日志或请求中新增 `/api` 或重复 `/event`

#### Scenario: 重连成功

- **WHEN** 一次断连或连接失败后的重连尝试成功建立 SSE 连接
- **THEN** SHALL 记录 `milky_event_stream_reconnected` 英文日志
- **AND** 日志 SHALL 包含本次恢复对应的 1-based `attempt`
- **AND** SHALL 使用新的事件流继续消费可见事件而不恢复断线期间丢失的事件、wait buffer 或 Will 分数

#### Scenario: 主动取消

- **WHEN** 适配器停止、取消事件消费者，或取消正在进行的退避等待
- **THEN** receive loop SHALL 结束并记录一次 `milky_event_stream_cancelled` 英文日志
- **AND** SHALL 不记录 `milky_event_stream_disconnected` 异常日志
- **AND** SHALL 不再生成新 handler、等待剩余退避或发起重连请求

#### Scenario: 日志原因安全降级

- **WHEN** 连接异常包含底层异常信息、认证失败信息或服务端返回内容
- **THEN** 日志 SHALL 只保留预定义的安全原因类别和数值型退避/尝试字段
- **AND** SHALL 不包含 token、Authorization、完整 URL、原始异常文本、消息正文、媒体 URL 或本地媒体路径
