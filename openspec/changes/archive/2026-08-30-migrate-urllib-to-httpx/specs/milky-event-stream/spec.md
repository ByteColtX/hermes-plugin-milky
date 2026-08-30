## MODIFIED Requirements

### Requirement: 断线重连和取消可控

事件流 MUST 在连接建立、持续读取和主动停止之间保持可区分的超时与状态语义；连接建立
超时、EOF 或传输错误发生后 MUST 按退避策略重连，但已建立的 SSE 在正常空闲期间 MUST
保持打开。适配器停止时 MUST 支持取消，并释放 reader、HTTP response、事件流 client
和定时器资源。

#### Scenario: 可恢复断线

- **WHEN** SSE 连接发生 EOF、连接异常或持续读取传输错误
- **THEN** 消费者 SHALL 按配置退避后重新建立 `/event` 连接
- **AND** SHALL 不把本次重连视为断线期间事件已被恢复

#### Scenario: 建立连接超时

- **WHEN** `/event` 连接在连接建立期限内未完成
- **THEN** 消费者 SHALL 将其分类为可重试的传输错误
- **AND** SHALL 按退避策略再次尝试连接

#### Scenario: 主动取消

- **WHEN** 适配器停止并取消事件消费者
- **THEN** receive loop SHALL 结束
- **AND** SHALL 不再生成新 handler 或发起重连请求
- **AND** SHALL 释放当前响应、事件流 client 和退避等待资源

### Requirement: 已建立 SSE 的正常空闲不得触发重连

事件流在连接建立成功后 MUST 允许超过任意单次事件间隔而不因缺少业务事件主动断开；正常
空闲、SSE 注释心跳和空白帧 SHALL NOT 被分类为传输失败或触发重连。只有 EOF、明确的
网络/读取错误或适配器主动停止才可结束当前连接。

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

事件消费者 MUST 仅依赖 Milky 已确认的 SSE 恢复协议；在 Milky v1.3 当前 OpenAPI 未定义
事件 ID、恢复游标、`Last-Event-ID` 或断线补发语义的情况下，消费者 SHALL NOT 猜测、伪造
或声称存在这些能力。事件流重连成功只表示开始接收新连接上可见的事件。

#### Scenario: 当前协议未定义恢复游标

- **WHEN** 根据当前 Milky OpenAPI 无法确认事件 ID 或断线补发协议
- **THEN** 重连 SHALL 继续使用已确认的 `/event` 请求边界
- **AND** 系统 SHALL 将断线期间事件恢复能力保持为 `unknown`，不得向用户报告无损恢复

#### Scenario: 未来协议明确支持恢复

- **WHEN** 后续 Milky 协议明确声明事件 ID、恢复请求头和补发边界
- **THEN** 适配器 SHALL 先通过独立契约和回归测试支持该恢复协议
- **AND** 在此之前 SHALL 不发送未确认的恢复字段或依赖其语义
