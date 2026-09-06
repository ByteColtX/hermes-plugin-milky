## MODIFIED Requirements

### Requirement: SSE 帧按标准边界解码

事件流 MUST 识别 `event:` 字段、多个 `data:` 行和空行事件边界，并将同一帧的多行 data 按 SSE 规则拼接后再解码。坏帧或未知事件 SHALL 只产生固定的 `event=milky.sse` 调试诊断，不得把原始帧、payload、异常正文或凭证交给普通日志调用。

#### Scenario: 多行 data 事件

- **WHEN** 一帧包含事件类型、两行 data 和随后空行
- **THEN** 消费者 SHALL 将两行 data 拼接为一个事件 payload
- **AND** SHALL 只分发一次该事件

#### Scenario: malformed 帧

- **WHEN** 一帧无法解析为合法事件或 JSON payload
- **THEN** 消费者 SHALL 丢弃该帧并记录 `event=milky.sse`、固定 malformed 分类
- **AND** SHALL 继续读取后续帧
- **AND** SHALL 不把原始帧、payload、异常正文或凭证交给普通日志调用

### Requirement: 事件 handler 不阻塞 receive loop

事件消费者 MUST 将每个合法事件交给独立的可观察处理任务或等价的非阻塞边界；单个 handler
的慢处理或异常 SHALL 不终止后续帧读取。合法帧交付后发生的 handler 失败 MUST 记录
`event=milky.sse`、handler 失败分类和必要的事件关联信息；该失败不得复用表示帧解析或
事件类型拒绝的诊断。handler 日志 SHALL 只包含安全分类、异常类型名（如有）和固定 reason，
不得包含事件 payload、正文、凭证、URL 或路径。

#### Scenario: handler 慢于下一帧

- **WHEN** 当前事件的资源补全或 Hermes turn 尚未完成而下一帧已到达
- **THEN** receive loop SHALL 能继续收帧并按事件顺序交付
- **AND** SHALL 不因等待当前 handler 而停止读取

#### Scenario: handler 抛出异常

- **WHEN** 一个合法事件的 handler 失败
- **THEN** 失败 SHALL 被分类并记录 `event=milky.sse`、handler 失败和必要耗时/关联字段
- **AND** SHALL NOT 记录 frame ignored 或异常正文
- **AND** 后续事件 SHALL 仍可被接收

### Requirement: 断线重连和取消可控

事件流 MUST 在可重试断线后按既有退避策略重连，并支持取消；断开时 SHALL 释放 reader、HTTP
response、客户端和定时器资源。每次建立连接的异常终止、退避安排、重连尝试、重连成功和主动
取消 SHALL 使用 `event=milky.sse` 的固定子事件或等价可检索标签。日志 SHALL 提供安全原因、
1-based 尝试序号、实际退避秒数（适用于 scheduled）、已知 HTTP 状态码和 `duration_ms`（适用时），
不得包含 token、Authorization、完整 URL、原始异常文本、消息正文、媒体 URL 或本地路径。

主动停止或取消时 MUST 结束 receive loop，不得将取消误报为异常断连，不得继续等待退避或
发起新的连接请求。

#### Scenario: 可恢复断线

- **WHEN** 已建立的 SSE 连接意外以 EOF、读取连接错误、持续读取传输错误或协议级连接错误结束
- **THEN** 消费者 SHALL 记录 `event=milky.sse`、disconnected 子事件和安全 `reason`
- **AND** SHALL 按配置退避后重新建立 `/event` 连接
- **AND** SHALL 不假设断线期间丢失事件会被服务端恢复

#### Scenario: 连接建立失败

- **WHEN** 一次待重连的 `/event` 连接因连接错误、超时或 HTTP 错误而未建立成功
- **THEN** 消费者 SHALL 记录 reconnect attempt 和下一次 scheduled 所需的安全 `reason`、attempt 和状态码（如有）
- **AND** SHALL 不为从未建立的连接伪造已建立连接的 disconnected 终态
- **AND** SHALL 继续按退避策略尝试连接

#### Scenario: 建立连接超时

- **WHEN** `/event` 连接在连接建立期限内未完成
- **THEN** 消费者 SHALL 将其分类为可重试的传输错误
- **AND** SHALL 记录安全的 timeout 原因、attempt、耗时和下一次退避安排
- **AND** SHALL 按退避策略再次尝试连接

#### Scenario: 退避等待和实际重连可观测

- **WHEN** 消费者为第 1 次或后续重连安排退避
- **THEN** SHALL 在等待前记录 scheduled，包含 1-based `attempt`、`delay_seconds` 和安全 `reason`
- **AND** 退避结束后 SHALL 记录 reconnect attempt，并使用该尝试建立同一 `/event` 端点

#### Scenario: 重连成功

- **WHEN** 一次断连或连接失败后的重连尝试成功建立 SSE 连接
- **THEN** SHALL 记录 reconnected 子事件、对应的 1-based `attempt` 和连接耗时（如有）
- **AND** SHALL 使用新的事件流继续消费可见事件而不恢复断线期间丢失的事件、wait buffer 或 Will 分数

#### Scenario: 主动取消

- **WHEN** 适配器停止、取消事件消费者，或取消正在进行的退避等待
- **THEN** receive loop SHALL 结束并记录一次 cancelled 子事件
- **AND** SHALL 不记录 disconnected 异常终态
- **AND** SHALL 不再生成新 handler、等待剩余退避或发起重连请求

#### Scenario: 日志原因安全降级

- **WHEN** 连接异常包含底层异常信息、认证失败信息或服务端返回内容
- **THEN** 日志 SHALL 只保留预定义的安全原因、异常类型名和数值型退避/尝试/状态字段
- **AND** SHALL 不包含 token、Authorization、完整 URL、原始异常文本、消息正文、媒体 URL 或本地媒体路径
