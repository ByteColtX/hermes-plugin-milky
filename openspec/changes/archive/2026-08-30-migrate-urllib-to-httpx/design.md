## Context

See `proposal.md` for the motivation. 当前插件的 `MilkyClient` 和 `SseEventStream` 都以
`urllib` 为底层网络实现；SSE 响应通过线程执行阻塞 `readline()`，并把同一个有限 timeout
同时用于连接建立和持续读取。Hermes Agent 当前核心依赖已固定提供 `httpx==0.28.1`，而
`aiohttp` 只在 messaging 等可选 extra 中提供。

现有 SSE 帧解码、事件 parser、handler 隔离、重连退避和生命周期边界已经独立于 transport；
本设计只替换 HTTP transport，并保持这些上层行为。Milky v1.3.0 OpenAPI 当前只描述
`Event` 的 `event_type`、`time`、`self_id` 和 `data`，没有 `/event` path、SSE event ID、
恢复游标、`Last-Event-ID` 或断线补发契约，因此恢复能力必须继续保持 `unknown`。

参考实现为 `notnotype/milky-python-sdk` 当前 `master`（v0.4.2）：其异步 client 使用
`httpx.AsyncClient`，Action 通过 `post(..., json=...)`，SSE 通过
`AsyncClient.stream("GET", ..., timeout=None)` 和异步文本 chunk 读取。该 SDK 的
`events_sse()` 是有价值的 transport 起点，但它没有重连循环，按 `\\n\\n` 简单切帧，未完整
处理 `event:`、注释心跳和标准多行 `data:` 规则，也没有事件恢复游标；本变更只借鉴其
HTTPX 使用方式，不将 SDK 作为依赖或协议事实来源。

## Goals / Non-Goals

**Goals:**

- 使用 Hermes 已有的核心 HTTP 依赖提供原生异步 Action 和 SSE 流式 I/O，不改变插件声明的
  运行时依赖集合。
- 为普通 Action 保留明确的连接、写入、读取/超时、HTTP、JSON 和 Milky envelope 错误分类。
- 为 SSE 使用有限的连接建立超时和无固定短读取期限的长连接，避免正常空闲造成周期性重连。
- 保留 SSE 帧语义、handler 非阻塞、重连退避、主动取消、错误脱敏和独立资源所有权。
- 通过 fake transport、脱敏本地 HTTP/SSE fixture 和宿主环境验证覆盖并发、空闲、心跳、EOF
  和资源释放。

**Non-Goals:**

- 不引入 `aiohttp`、`httpx-sse`、`requests` 或任何新的插件运行时依赖。
- 不把 `httpx` 迁移扩展为新的代理、认证、重试、缓存、SSRF 或媒体下载框架；媒体安全仍由
  Hermes 公共 helper 所有。
- 不实现 Milky 当前未确认的 SSE event ID、`Last-Event-ID`、回放、补发或 exactly-once/
  at-least-once 语义。
- 不替换 `urllib.parse` 等纯 URL 解析工具，不修改 Milky Action、事件字段或消息流水线契约。

## Decisions

### 1. 复用 Hermes 核心 httpx，不新增插件依赖

实现使用延迟导入的 `httpx`，因为当前 Hermes Agent 的核心 `pyproject.toml` 已固定
`httpx[socks]==0.28.1`；插件自身保持空的 runtime `dependencies`，避免把宿主已经提供的
包重复打进插件。延迟导入可以让根入口、纯 parser 测试和 fake transport 在没有 Hermes
宿主的本地环境中继续加载；真正建立网络连接时若宿主缺少 `httpx`，应返回固定的依赖/传输
不可用诊断，而不静默回退到 `urllib`。

备选方案：

- `aiohttp`：官方 Hermes 仅通过 messaging、slack、matrix 等 optional extra 提供，不能作为
  默认宿主契约。
- `httpx-sse`：它不是 Hermes 核心必需依赖，且现有帧解码器已经处理 `event:`、多行 `data:`
  和空行边界，不值得增加一层协议依赖。
- 保留 `urllib`：可维持零依赖，但无法自然表达可取消的原生异步长连接，并保留当前读超时
  误判问题。

SDK 直接依赖 `httpx`、`pydantic` 和 `python-dotenv`，但插件只需要借鉴其 `AsyncClient`
和 stream 组织方式；DTO、配置和错误模型继续由本仓库拥有，避免引入 SDK 的额外依赖和
不同的协议容错语义。

### 2. Action 与 SSE 各自拥有一个长生命周期 AsyncClient

`MilkyClient` 的 HTTP transport 拥有一个可复用的 `httpx.AsyncClient`，负责普通 POST
Action；`SseEventStream` 的 SSE transport 拥有另一个 `httpx.AsyncClient`，负责一个当前
`/event` 流及其重连。两者不共享关闭边界，避免停止 SSE 时意外关闭正在执行的 Action，或
关闭 Action 时截断事件流。每个 owner 在 `close()` 中只关闭自己的 response 和 client，
重复关闭保持幂等。

备选方案是全局共享 client。它可以减少连接池对象，但会让 adapter、Action 和 SSE 的资源
所有权互相耦合，且一个边界的关闭可能影响另一个边界；当前架构将 `milky/client` 与
`event_stream` 作为独立传输边界，因此不选用全局共享。

### 3. 普通 Action 使用有限的阶段 timeout，保持不盲目重试

普通 Action 使用 `httpx` 的阶段 timeout 配置：连接、写入、读取和连接池等待使用现有
请求 timeout 的有限值。`TimeoutException`、网络错误和协议连接错误统一映射为现有
`transport_unknown`；HTTP 非 2xx、非 JSON、envelope 拒绝和最小 data 缺失继续分别映射为
既有分类。普通 Action 不自动重试，以保留发送超时后远端执行状态未知的安全边界。

每次请求使用 JSON body 和已有认证 header；响应在解析完成后立即释放/归还连接池。并发
Action 不共享可变响应状态，每个调用只处理自己的 response。

### 4. SSE 仅限制连接建立，不限制正常空闲读取

SSE 使用 `AsyncClient.stream("GET", ...)` 建立响应流。连接建立阶段保留有限 connect
timeout；读取阶段不设置固定的 10 秒短 timeout（等价于 `read=None`），使无业务事件的正常
空闲不触发断线。底层读取适配为现有 `SseResponse.readline()` seam，继续把行交给已有
SSE frame collector。

SSE 注释心跳和空白边界继续由现有 parser 忽略；它们不会产生业务 handler。EOF、明确的
网络/协议读取异常和主动取消仍结束当前 response，进入既有重连或停止路径。取消时先关闭
response，再关闭 client；重连不会创建第二个长期 receive loop。

备选方案是把 SSE read timeout 调大到固定值。这只能推迟断连，仍会把合法的长空闲误判为
失败；不选用。也不新增 Milky 未确认的健康检查 Action 或自定义 keepalive 请求，因为这
会猜测协议能力。

这里采用 SDK 已验证的 `timeout=None` 长连接方向，但将其收窄为 SSE read timeout 不限时、
connect timeout 有限；普通 Action 不继承 `timeout=None`，仍使用有限的阶段 timeout。

### 5. 不在本次迁移中加入恢复游标

HTTPX transport 不解析或发送未由 Milky 文档确认的 `Last-Event-ID`。现有 `id:` 等未知
SSE 字段仍不进入业务 payload；连接重建只重新 GET 已确认的 `/event`。如果未来 Milky
明确提供事件 ID、请求头和补发窗口，必须另建契约和 fixture 后再加入恢复层，不能把更换
HTTP 客户端当成无损保证。

### 6. 保持 transport 注入和无敏感输出测试边界

继续使用现有 `HttpTransport`/`SseTransport` protocol 作为业务与网络的 seam。单元测试使用
fake transport 验证 Action 和 SSE 业务边界；HTTPX-specific 测试使用脱敏的本地 HTTP/SSE
服务验证真实异步读取、分块、空闲、EOF、取消和 client 关闭。所有诊断只保留固定分类和
安全 reason，不记录 token、Authorization、URL、消息正文、媒体路径或远端 ID。

SDK 的 chunk 示例不替换本仓库已有的标准 SSE frame decoder：仍必须先识别 `event:`、多行
`data:`、注释和空行边界，再调用 Milky parser。这样既复用 SDK 的异步读取思路，又不丢失
当前项目已经覆盖的外层 `milky_event`、malformed/unknown 和 handler 隔离契约。

## Risks / Trade-offs

- **宿主缺少 httpx** → 延迟导入并在真实网络边界报告固定的传输依赖不可用；不添加插件依赖，
  因为正式 directory plugin 运行于 Hermes 核心环境。
- **无 read timeout 的 SSE 可能在半开连接上长期等待** → 依赖已确认的 SSE heartbeat/EOF
  或 TCP 错误；不虚构健康检查 Action。若 Milky 后续公开健康检查或恢复契约，再单独设计
  liveness/replay 行为。
- **httpx 版本升级改变流式细节** → 以 Hermes 当前固定的 0.28.1 API 为目标，保留
  transport seam，并用真实本地 SSE fixture 验证行边界和 response 释放。
- **HTTPX 与 urllib 的代理/TLS 默认行为存在差异** → 在宿主环境做 HTTP、HTTPS、Bearer、
  prefix 和失败分类回归；不扩大本次变更为代理策略迁移，差异保持为可分类传输错误。
- **重连窗口仍可能漏事件** → 继续明确 Milky 当前恢复语义为 `unknown`，不发送未确认的
  恢复头；后续若要无损恢复必须依赖 Milky 明确的事件 ID/补发能力。
- **直接照搬 SDK 的 SSE parser 会丢失标准帧语义** → 只采用其 HTTPX stream 结构，保留本仓库
  的 frame decoder、外层事件解析和安全诊断测试。
- **双 AsyncClient 增加少量连接池资源** → 每个 adapter 只保持一个 Action client 和一个
  SSE client，并在 adapter disconnect 中幂等关闭；不创建全局 client 或无界连接池。

## Migration Plan

1. 先补充空闲超过 10 秒仍保持连接、注释 heartbeat、SSE EOF/取消、Action 并发和 client
   关闭的脱敏 fixture 与契约测试。
2. 实现 HTTPX Action transport，替换 `MilkyClient` 的 urllib 网络 I/O，保留现有 parser、
   envelope、错误分类和不重试行为。
3. 实现 HTTPX SSE transport，替换 `SseEventStream` 的 urllib 网络 I/O，保留 frame decoder、
   handler task、重连退避和生命周期接口。
4. 在 Hermes 官方依赖环境和本地 fake/local fixture 中验证 import、Action、SSE、adapter
   disconnect 与重复关闭；确认插件 `pyproject.toml`、`uv.lock` 没有新增运行时依赖。
5. 运行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv build`、
   `git diff --check` 和 OpenSpec strict validation；再用运行时凭证执行只读 Milky smoke，
   只记录连接次数、事件数量和安全分类。
6. 部署后观察 Milky 侧 `/event` 连接日志：正常空闲不应再固定每 10 秒断开；若仍断开，按
   EOF、服务端主动关闭、代理空闲策略或网络错误分类，而不是自动假设为客户端 timeout。

回滚时只恢复两个 transport 的实现，保留既有 protocol seam、parser 和测试；不回滚或改变
Milky 事件恢复语义，也不引入 urllib/httpx 混合的隐式 fallback。

## Open Questions

- Milky 服务端是否在未公开的实现文档或具体部署版本中提供 SSE event ID、`Last-Event-ID`
  或断线补发，当前 OpenAPI 无法回答；本变更按 `unknown` 处理，不阻塞 HTTPX 迁移，但若要
  追求无损接收，必须由后续协议证据先回答。
