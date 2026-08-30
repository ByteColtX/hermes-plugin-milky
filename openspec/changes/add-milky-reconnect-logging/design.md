## Context

See `proposal.md` for the motivation. 当前 `milky/event_stream.py` 已拥有 SSE `/event` 的连接、帧读取、handler 隔离、退避、取消和有界 `StreamDiagnostic`，但 `_record()` 只保留进程内诊断，不向宿主日志输出连接状态转移。现有测试覆盖了连接失败后的退避、EOF 后重连、关闭期间打断退避和资源释放，但没有验证运维日志的顺序、字段或脱敏边界。

本设计只扩展事件流的可观察诊断。现有 SSE URL、Bearer 认证、帧解析、handler 非阻塞、退避数值和“重连不恢复丢失事件/会话策略状态”的契约继续由既有 `milky-event-stream` spec 负责。

## Goals / Non-Goals

**Goals:**

- 在连接生命周期的确定性转移点输出英文、稳定且可检索的日志事件。
- 让断连原因、退避等待、实际重连尝试和恢复结果可以按一次重连周期关联。
- 保证取消优先于断连处理，取消退避等待不会产生误导性异常日志或新的连接请求。
- 复用现有 fake transport、可注入 sleep 和资源计数，建立不会依赖真实 Milky 的回归证据。

**Non-Goals:**

- 不改变退避初始值、上限、倍增公式、重试资格或连接请求内容。
- 不为初始成功连接、普通 SSE frame、handler 失败或消息流水线增加新的日志协议。
- 不记录原始异常、响应正文、完整 endpoint、消息正文、媒体 URL、本地路径或任何认证材料。
- 不引入新的日志依赖、配置项、持久化重连计数器、指标系统或远程 telemetry。

## Decisions

### 使用标准日志事件标签并保留现有安全诊断

事件流模块使用宿主已有的 Python logging 边界输出固定英文事件标签；日志消息本身使用以下稳定标签：

- `milky_event_stream_disconnected`
- `milky_event_stream_reconnect_scheduled`
- `milky_event_stream_reconnect_attempt`
- `milky_event_stream_reconnected`
- `milky_event_stream_cancelled`

生命周期日志使用结构化字段或等价的可检索字段：`reason` 只允许 `eof`、`connection_error`、`timeout`、`http_error`、`protocol_error`、`stream_error`、`unknown`；重连日志使用 1-based `attempt`；scheduled 日志另外使用实际的 `delay_seconds`。日志可保留现有 `StreamDiagnostic` 作为测试和诊断快照，但不把诊断 deque 当作宿主日志的替代品。

选择固定标签和白名单字段，而不是直接记录异常字符串或 URL，是因为底层 HTTP/SSE 异常可能包含认证头、完整 endpoint 或服务端响应。选择宿主标准 logging，而不是新增 telemetry 依赖，是因为本 change 只需要让已有应用日志显示状态，不应改变部署依赖。日志级别由事件严重性区分：意外断连和安排退避使用 warning，实际尝试、恢复和主动取消使用 info；宿主仍可按 logger 配置过滤这些记录。

### 在 receive loop 的状态转移点记录日志

由拥有连接生命周期的 receive loop 统一发出日志，避免 `close()`、response finalizer 和 transport close 各自重复报告同一次状态：

1. 已建立连接的 `_consume_connection()` 因 EOF、读取错误或协议级错误结束时，先形成一次安全断连结果并输出 `disconnected`，再执行现有 response close。
2. `_transport.connect()` 未返回已建立 response 的失败不输出 `disconnected`；它只把安全原因带入下一次重连周期。退避开始前输出 `reconnect_scheduled`，退避结束且未取消时输出 `reconnect_attempt`，然后才调用同一 `/event` 连接路径。
3. 连接成功后，如果本轮是重连，输出 `reconnected`，随后沿用现有逻辑重置退避；初始连接成功不输出恢复日志。
4. `close()` 只设置 stopping/stop event、关闭当前 response 并取消 handler；最终 receive loop 根据取消优先级输出一次 `cancelled`。取消发生在连接建立或退避等待中时，也不得输出意外断连或后续 attempt。

重连周期的 attempt 从 1 开始，连续连接失败时递增；成功恢复后清零，下一次新的断连周期重新从 1 开始。这与现有成功后重置 backoff 的行为保持一致，也避免把多个独立断连周期误关联为一个无限增长的计数序列。

### 通过安全原因归一化隔离异常细节

在日志边界增加单向的原因归一化：优先根据已知的 `EventStreamError` 分类、超时类型、HTTP 状态失败和 EOF 结果映射到白名单 reason；无法识别的异常统一为 `unknown` 或 `stream_error`。日志 helper 不接受原始异常文本作为输出参数，现有 `_record()` 继续只接收固定安全诊断。这样既保留了操作所需的故障类别，也不要求对每个 transport 的异常类型作不稳定的字符串匹配。

帧级 malformed/unknown 事件仍按原有 observe-and-continue 诊断处理，不因为普通坏帧而伪造断连日志；只有连接级读取无法继续时才进入断连重连转移。这样可区分“单帧被丢弃”和“事件流实际中断”。

### 以脱敏 fake fixture 验证日志顺序和取消竞态

单元测试使用现有 fake transport 与可注入 sleep，不访问真实 Milky。测试通过宿主日志捕获检查事件标签、顺序和字段，并同时检查 `StreamDiagnostic`、连接次数、delay 列表和 response/transport close 次数。至少覆盖：

- EOF 后依次出现 disconnected → scheduled(attempt=1) → attempt(1) → reconnected(1)。
- 首次连接失败和连续连接失败的安全 reason、attempt 递增、退避值与 max backoff 对齐。
- 异常文本、token、Authorization、完整 URL 和消息/媒体内容不进入日志。
- 退避期间取消只输出一次 cancelled，不输出 disconnected/attempt，不建立新连接。
- 连接建立期间取消和重复 close 仍释放资源且不重复发出生命周期日志。

不新增真实环境 smoke 的写入动作；若未来运行已有只读本地 HTTPX SSE 集成测试，可仅追加日志捕获断言，不能把真实响应内容写入 fixture 或日志。

## Risks / Trade-offs

- [日志级别受宿主配置过滤] → 断连和退避安排使用 warning，恢复和取消使用 info；不新增插件私有日志配置，保持宿主统一管理。
- [取消与 EOF/异常同时到达导致重复或误报] → 由 receive loop 作为唯一状态转移拥有者，并在日志前检查 stopping/取消优先级；`close()` 不直接打印同一生命周期事件。
- [transport 异常类型随依赖版本变化] → 日志只使用白名单 reason，未知情况降级为 `unknown`，不依赖异常文本或响应正文。
- [网络抖动产生高频日志] → 每次连接转移最多一组固定生命周期记录，不输出每行 SSE 或原始错误；重连 attempt 使用有界退避策略。
- [测试仅覆盖 fake transport] → 保留现有 HTTPX 本地 SSE 集成测试作为路径和资源回归；日志字段本身用确定性 fake 测试验证，避免真实环境不稳定。

## Migration Plan

这是向现有日志输出添加事件的向后兼容变更。实现并通过单元、集成（如适用）、ruff、format、build、diff 和 OpenSpec strict validation 后随适配器版本发布；无需迁移配置或数据。回滚时恢复旧版事件流模块即可，既有 `/event` 协议和内存状态语义不需要转换。

## Open Questions

无。日志事件标签、字段、reason 白名单、取消优先级和 attempt 生命周期已由本 change spec 固定，后续实现不应再改变其可观察含义。
