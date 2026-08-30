## Why

当前 Milky HTTP Action 和 SSE `/event` transport 都使用阻塞式 `urllib`，再通过线程包装异步接口；SSE 的单一 10 秒 socket timeout 会把正常的空闲期误判为传输失败，造成周期性断开和重连，并留下可能漏收事件的窗口。Hermes Agent 核心已固定提供 `httpx==0.28.1`，现在应复用宿主已有依赖，统一迁移到原生异步 HTTP transport，改善长连接生命周期而不增加插件依赖。

## What Changes

- 将 `milky/client.py` 的 HTTP Action transport 从 `urllib.request` 迁移到宿主提供的 `httpx.AsyncClient`，保留现有 POST、Bearer、JSON、envelope 校验、错误分类、参数校验和关闭语义。
- 将 `milky/event_stream.py` 的 SSE transport 迁移到 `httpx.AsyncClient.stream()`，使用原生异步流式读取，分离连接建立超时与持续读取超时；空闲 SSE 不再因固定 10 秒读取超时主动断开。
- 参考 [milky-python-sdk](https://github.com/notnotype/milky-python-sdk) 的异步 client 组织、`post(..., json=...)` 和 SSE stream 用法，但不直接依赖该 SDK，也不照搬其缺少标准 SSE 帧处理、重连和安全错误分类的实现。
- 保留现有 SSE 帧解析、`milky_event` 外层处理、多行 `data`、handler 隔离、重连退避、取消和资源释放行为。
- 不在插件 `pyproject.toml` 增加运行时依赖；`httpx` 仅作为当前 Hermes Agent 宿主的既有核心依赖使用，并通过延迟导入和 fake transport 保持插件测试边界可运行。
- 保留 `urllib.parse` 等纯 URL 解析用途；本次“全面切换”仅针对 HTTP/SSE 网络 I/O，不替换无网络副作用的标准库 URL 工具。
- 明确 Milky v1.3 当前 OpenAPI 未定义 SSE `id`、`Last-Event-ID` 或断线补发语义；本变更不猜测或伪造恢复能力，断线期间的事件可见性仍记录为未确认。
- 增加空闲长连接、SSE 心跳、EOF、网络异常、取消、重连间隔、HTTP Action 并发和共享 client 关闭的脱敏 fixture 与回归测试。

## Capabilities

### New Capabilities

无。本变更改进现有 Milky transport 能力，不引入新的协议能力。

### Modified Capabilities

- `milky-event-stream`: 调整 SSE 持续读取超时、异步流式读取、空闲/心跳处理和连接资源生命周期要求；保持未确认的事件恢复语义。
- `milky-http-actions`: 调整 HTTP Action 的异步 transport、共享 client 生命周期和并发请求要求；保持既有协议 envelope、认证、错误分类和不盲目重试契约。

## Impact

- 受影响代码：`milky/client.py`、`milky/event_stream.py` 及其 transport 测试、协议 fixture、本地 HTTP/SSE 集成测试和必要的生命周期装配。
- 受影响依赖：不修改插件运行时依赖；复用 Hermes Agent 核心的 `httpx==0.28.1`，不引入 `aiohttp`、`httpx-sse` 或其他新包。
- 参考实现依赖：`milky-python-sdk` 自身声明 `httpx`、`pydantic` 和 `python-dotenv`，本变更只借鉴其公开 client 结构，不引入 SDK 或其额外依赖。
- 运行时收益：避免空闲 SSE 在 10 秒处被客户端主动切断，降低重连频率，并使取消和连接关闭不再依赖阻塞线程读取的完成。
- 运行时边界：httpx 迁移本身不提供事件补发或 exactly-once/at-least-once 保证；Milky 未确认的 SSE 恢复能力必须继续标记为 `unknown`，不能把重连视为无损恢复。
