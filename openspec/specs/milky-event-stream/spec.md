# milky-event-stream Specification

## Purpose

为 Milky 提供独立于 HTTP Action 的 SSE `/event` 事件接收能力，可靠处理帧边界、
断线和取消，并保证慢速业务处理不会阻塞后续事件读取。

## Requirements

### Requirement: 事件流使用正确的 SSE 端点

事件消费者 MUST 通过同一 scheme、host、port 和 path prefix 的 GET `/event` 建立 SSE 连接，并使用 Bearer 认证；事件流 SHALL NOT 追加 `/api` 或重复 `/event`。Milky v1.3 的 SSE 外层事件名通常为 `milky_event`，业务事件类型 SHALL 以 JSON data 内的 `event_type` 为准。

#### Scenario: 建立带 prefix 的 SSE 连接

- **WHEN** base URL 为 `https://host.example/milky/`
- **THEN** 事件消费者 SHALL GET `https://host.example/milky/event`
- **AND** SHALL 包含 Bearer 认证

#### Scenario: Action 响应与事件流分离

- **WHEN** HTTP Action 收到响应
- **THEN** 该响应 SHALL 只完成对应的 Action 调用
- **AND** SHALL NOT 被当作 SSE 事件或用于唤醒 WebSocket echo pending 请求

#### Scenario: milky_event 外层包装

- **WHEN** SSE 帧的外层字段为 `event: milky_event` 且 data JSON 的 `event_type` 为 `message_receive`
- **THEN** 消费者 SHALL 解析 data 内的事件类型并交给对应事件 parser
- **AND** SHALL 不把固定的外层 `milky_event` 当成业务事件类型或依赖 OneBot echo

### Requirement: SSE 帧按标准边界解码

事件流 MUST 识别 `event:` 字段、多个 `data:` 行和空行事件边界，并将同一帧的多行 data 按 SSE 规则拼接后再解码。

#### Scenario: 多行 data 事件

- **WHEN** 一帧包含事件类型、两行 data 和随后空行
- **THEN** 消费者 SHALL 将两行 data 拼接为一个事件 payload
- **AND** SHALL 只分发一次该事件

#### Scenario: malformed 帧

- **WHEN** 一帧无法解析为合法事件或 JSON payload
- **THEN** 消费者 SHALL 记录不含凭证的安全摘要并丢弃该帧
- **AND** SHALL 继续读取后续帧

### Requirement: 事件 handler 不阻塞 receive loop

事件消费者 MUST 将每个合法事件交给独立的可观察处理任务或等价的非阻塞边界；单个 handler
的慢处理或异常 SHALL 不终止后续帧读取。合法帧交付后发生的 handler 失败 MUST 记录固定的
`milky_event_stream_handler_failed` 事件；该失败不得复用表示帧解析或事件类型拒绝的
`milky_event_stream_frame_ignored` 事件。handler 日志 SHALL 只包含安全分类和固定 reason，不得包含
事件 payload、正文、凭证、URL 或路径。

#### Scenario: handler 慢于下一帧

- **WHEN** 当前事件的资源补全或 Hermes turn 尚未完成而下一帧已到达
- **THEN** receive loop SHALL 能继续收帧并按事件顺序交付
- **AND** SHALL 不因等待当前 handler 而停止读取

#### Scenario: handler 抛出异常

- **WHEN** 一个合法事件的 handler 失败
- **THEN** 失败 SHALL 被分类并记录 `milky_event_stream_handler_failed`
- **AND** SHALL NOT 记录 `milky_event_stream_frame_ignored`
- **AND** 后续事件 SHALL 仍可被接收

### Requirement: 断线重连和取消可控

事件流 MUST 在可重试断线后按既有退避策略重连，并支持取消；断开时 SHALL 释放 reader、HTTP response、客户端和定时器资源。每次已建立的 SSE 连接意外终止时，系统 MUST 记录一条以 `[Milky] ` 开头的英文 `milky_event_stream_disconnected` 日志；每次退避重连前 MUST 记录一条以 `[Milky] ` 开头的英文 `milky_event_stream_reconnect_scheduled` 日志，退避结束后 MUST 记录一条以 `[Milky] ` 开头的英文 `milky_event_stream_reconnect_attempt` 日志，重连成功后 MUST 记录一条以 `[Milky] ` 开头的英文 `milky_event_stream_reconnected` 日志。日志消息 SHALL 使用 Hermes-agent 风格的短句和 `info`/`warning` 级别；如宿主保留结构化字段，`event_name`、`reason`、`attempt` 和 `delay_seconds` SHALL 使用固定白名单值。重连日志 MUST 提供 1-based 尝试序号、实际退避等待秒数（适用于 scheduled）和安全原因类别；断连日志至少 MUST 提供安全原因类别。日志中的原因只能使用预定义的 `eof`、`connection_error`、`timeout`、`http_error`、`protocol_error`、`stream_error` 或 `unknown` 分类值，不得包含 token、Authorization、完整 URL、原始异常文本、消息正文、媒体 URL 或本地媒体路径。

`reconnect_attempt` 序号 MUST 从一次连接异常结束或连接建立失败后的第一轮新连接开始按 1 递增；`delay_seconds` MUST 表示对应重连尝试前实际采用的退避等待秒数。主动停止或取消时 MUST 记录一次以 `[Milky] ` 开头的英文取消日志，不得将取消误报为异常断连，不得继续等待退避或发起新的连接请求。

#### Scenario: 可恢复断线

- **WHEN** 已建立的 SSE 连接意外以 EOF、读取连接错误、持续读取传输错误或协议级连接错误结束
- **THEN** 消费者 SHALL 记录带 `[Milky] ` 前缀的 `milky_event_stream_disconnected` 英文日志和安全 `reason`
- **AND** SHALL 按配置退避后重新建立 `/event` 连接
- **AND** SHALL 不假设断线期间丢失事件会被服务端恢复

#### Scenario: 连接建立失败

- **WHEN** 一次待重连的 `/event` 连接因连接错误、超时或 HTTP 错误而未建立成功
- **THEN** 消费者 SHALL 记录该次 `milky_event_stream_reconnect_attempt` 和下一次 `milky_event_stream_reconnect_scheduled` 所需的安全 `reason`
- **AND** SHALL 不为从未建立的连接伪造 `milky_event_stream_disconnected` 日志
- **AND** SHALL 继续按退避策略尝试连接

#### Scenario: 建立连接超时

- **WHEN** `/event` 连接在连接建立期限内未完成
- **THEN** 消费者 SHALL 将其分类为可重试的传输错误
- **AND** SHALL 按退避策略再次尝试连接

#### Scenario: 退避等待和实际重连可观测

- **WHEN** 消费者为第 1 次或后续重连安排退避
- **THEN** SHALL 在等待前记录带 `[Milky] ` 前缀的 `milky_event_stream_reconnect_scheduled`，包含 1-based `attempt`、`delay_seconds` 和安全 `reason`
- **AND** 退避结束后 SHALL 记录带 `[Milky] ` 前缀的 `milky_event_stream_reconnect_attempt`，包含相同的 `attempt`
- **AND** SHALL 使用该重连尝试建立同一 `/event` 端点，不得在日志或请求中新增 `/api` 或重复 `/event`

#### Scenario: 重连成功

- **WHEN** 一次断连或连接失败后的重连尝试成功建立 SSE 连接
- **THEN** SHALL 记录带 `[Milky] ` 前缀的 `milky_event_stream_reconnected` 英文日志
- **AND** 日志 SHALL 包含本次恢复对应的 1-based `attempt`
- **AND** SHALL 使用新的事件流继续消费可见事件而不恢复断线期间丢失的事件、wait buffer 或 Will 分数

#### Scenario: 主动取消

- **WHEN** 适配器停止、取消事件消费者，或取消正在进行的退避等待
- **THEN** receive loop SHALL 结束并记录一次带 `[Milky] ` 前缀的 `milky_event_stream_cancelled` 英文日志
- **AND** SHALL 不记录 `milky_event_stream_disconnected` 异常日志
- **AND** SHALL 不再生成新 handler、等待剩余退避或发起重连请求

#### Scenario: 日志原因安全降级

- **WHEN** 连接异常包含底层异常信息、认证失败信息或服务端返回内容
- **THEN** 日志 SHALL 只保留预定义的安全原因类别和数值型退避/尝试字段
- **AND** SHALL 不包含 token、Authorization、完整 URL、原始异常文本、消息正文、媒体 URL 或本地媒体路径

### Requirement: 已建立 SSE 的正常空闲不得触发重连

事件流在连接建立成功后 MUST 允许超过任意单次事件间隔而不因缺少业务事件主动断开；正常空闲、SSE 注释心跳和空白帧 SHALL NOT 被分类为传输失败或触发重连。只有 EOF、明确的网络/读取错误或适配器主动停止才可结束当前连接。

#### Scenario: 十秒以上没有业务事件

- **WHEN** 已建立的 SSE 在超过十秒内没有收到业务事件，且连接没有 EOF 或传输错误
- **THEN** 消费者 SHALL 保持当前连接
- **AND** SHALL NOT 因固定的短读取期限关闭连接或建立新连接

#### Scenario: 注释心跳

- **WHEN** SSE 收到以冒号开头的注释心跳并以空行结束
- **THEN** 消费者 SHALL 将其视为连接活动
- **AND** SHALL 不创建业务事件、malformed 诊断或 handler task

#### Scenario: 空闲期间收到业务事件

- **WHEN** 空闲期之后收到合法的 `milky_event` 帧
- **THEN** 消费者 SHALL 在同一连接上解析并分发该事件一次
- **AND** SHALL 不因此前的空闲时间重复连接或丢弃该帧

### Requirement: 断线恢复能力不做未确认承诺

事件消费者 MUST 仅依赖 Milky 已确认的 SSE 恢复协议；在 Milky v1.3 当前 OpenAPI 未定义事件 ID、恢复游标、`Last-Event-ID` 或断线补发语义的情况下，消费者 SHALL NOT 猜测、伪造或声称存在这些能力。事件流重连成功只表示开始接收新连接上可见的事件。

#### Scenario: 当前协议未定义恢复游标

- **WHEN** 根据当前 Milky OpenAPI 无法确认事件 ID 或断线补发协议
- **THEN** 重连 SHALL 继续使用已确认的 `/event` 请求边界
- **AND** 系统 SHALL 将断线期间事件恢复能力保持为 `unknown`，不得向用户报告无损恢复

#### Scenario: 未来协议明确支持恢复

- **WHEN** 后续 Milky 协议明确声明事件 ID、恢复请求头和补发边界
- **THEN** 适配器 SHALL 先通过独立契约和回归测试支持该恢复协议
- **AND** 在此之前 SHALL 不发送未确认的恢复字段或依赖其语义
