## Purpose

为 Milky 提供独立于 HTTP Action 的 SSE `/event` 事件接收能力，可靠处理帧边界、
断线和取消，并保证慢速业务处理不会阻塞后续事件读取。

## ADDED Requirements

### Requirement: 事件流使用正确的 SSE 端点

事件消费者 MUST 通过同一 scheme、host、port 和 path prefix 的 GET `/event` 建立 SSE 连接，并使用 Bearer 认证；事件流 SHALL NOT 追加 `/api` 或重复 `/event`。

#### Scenario: 建立带 prefix 的 SSE 连接

- **WHEN** base URL 为 `https://host.example/milky/`
- **THEN** 事件消费者 SHALL GET `https://host.example/milky/event`
- **AND** SHALL 包含 Bearer 认证

#### Scenario: Action 响应与事件流分离

- **WHEN** HTTP Action 收到响应
- **THEN** 该响应 SHALL 只完成对应的 Action 调用
- **AND** SHALL NOT 被当作 SSE 事件或用于唤醒 WebSocket echo pending 请求

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

事件消费者 MUST 将每个合法事件交给独立的可观察处理任务或等价的非阻塞边界；单个 handler 的慢处理或异常 SHALL 不终止后续帧读取，也 SHALL NOT 要求插件为慢 handler 建立 Agent 执行队列。

#### Scenario: handler 慢于下一帧

- **WHEN** 当前事件的资源补全或 Hermes turn 尚未完成而下一帧已到达
- **THEN** receive loop SHALL 能继续收帧并独立分发后续事件
- **AND** SHALL 不因等待当前 handler 或 Agent turn 而停止读取；后续 busy 行为 SHALL 由 Hermes 处理

#### Scenario: handler 抛出异常

- **WHEN** 一个事件 handler 失败
- **THEN** 失败 SHALL 被观察并分类
- **AND** 后续事件 SHALL 仍可被接收

### Requirement: 断线重连和取消可控

事件流 MUST 在可重试断线后按退避策略重连，并支持取消；断开时 SHALL 释放 reader、HTTP response、客户端和定时器资源。

#### Scenario: 可恢复断线

- **WHEN** SSE 连接意外断开
- **THEN** 消费者 SHALL 按配置退避后重新建立 `/event` 连接
- **AND** SHALL 不假设断线期间丢失事件会被服务端恢复

#### Scenario: 主动取消

- **WHEN** 适配器停止并取消事件消费者
- **THEN** receive loop SHALL 结束
- **AND** SHALL 不再生成新 handler 或发起重连请求
