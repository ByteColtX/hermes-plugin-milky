## 1. 契约与测试基础

- [x] 1.1 为 HTTPX Action transport 增加脱敏 fake/local fixture，覆盖 POST JSON、Bearer、HTTP 200 rejected、非 JSON、连接/写入/读取超时、并发调用和重复关闭；以定向 `uv run pytest tests/test_milky_client.py` 验证既有 envelope、参数校验、稳定 `message_seq` 和不盲目重试契约不回归
- [x] 1.2 为 HTTPX SSE transport 增加脱敏 fixture，覆盖超过 10 秒无业务事件仍保持同一连接、注释 heartbeat、空白帧、分块行读取、EOF、读取异常、主动取消和慢 handler；以定向 `uv run pytest tests/test_milky_event_stream.py tests/test_milky_local_integration.py` 验证事件帧只分发一次且 receive loop 不被阻塞
- [x] 1.3 增加协议恢复边界回归，证明当前 Milky v1.3 OpenAPI 未确认 event ID、`Last-Event-ID` 和断线补发时，重连不发送未确认恢复字段且诊断保持安全 `unknown`；以脱敏 fixture、OpenSpec strict validation 和 `rg` 检查验证不伪造恢复语义
- [x] 1.4 对照 `notnotype/milky-python-sdk` 的异步 Action/SSE client 公开用法建立兼容性检查，确认只复用 HTTPX stream 组织而不引入 SDK、Pydantic、dotenv 或其不完整的 SSE/错误语义；以依赖差异检查和本地脱敏 fixture 验证

## 2. HTTP Action transport 迁移

- [x] 2.1 在保留 `HttpTransport` 注入 seam 的前提下实现延迟导入的 HTTPX 异步 Action transport，使用 Hermes 核心已提供的 `httpx==0.28.1`，区分连接、写入、读取和连接池阶段 timeout，并将网络异常映射为 `transport_unknown`；以第 1.1 节测试和宿主依赖环境的最小请求验证完成
- [x] 2.2 将 `MilkyClient` 的 Action 请求接入 HTTPX transport，确保每个调用独立处理 response、继续使用 POST/Bearer/JSON 和既有 envelope 分类，并在成功解析后释放/归还 response；以 `uv run pytest tests/test_milky_client.py tests/test_outbound.py tests/test_mute_tracker.py` 验证所有 Action 调用方
- [x] 2.3 实现 Action client 的幂等关闭和停止后前置拒绝，验证关闭不会影响 SSE client，也不会产生新的网络请求；以并发关闭/停止 fake 测试和 `uv run pytest tests/test_adapter_lifecycle.py` 验证

## 3. SSE transport 迁移

- [x] 3.1 实现延迟导入的 HTTPX SSE response/transport，使用原生异步 stream 和可取消的行读取，保留 `SseResponse`/`SseTransport` seam、UTF-8 校验和现有 `decode_sse_frame`；以第 1.2 节 fixture 和本地真实 HTTP/SSE server 验证分块边界、response close 和 client close
- [x] 3.2 调整 SSE timeout 传递，使连接建立使用有限 timeout、已建立连接的读取不使用固定 10 秒短 timeout，并保留注释 heartbeat、EOF/网络异常重连、退避和 handler 隔离；以空闲超过 10 秒单连接测试、EOF 重连测试和 `uv run pytest tests/test_milky_event_stream.py` 验证
- [x] 3.3 保持 SSE 重连不发送或依赖未确认的 event ID、恢复游标和 `Last-Event-ID`，不改变 `milky_event`、多行 `data`、unknown/malformed 分类或普通消息 pipeline；以第 1.3 节测试、`rg -n "Last-Event-ID|last_event|event.id" milky tests` 和相关全量测试验证

## 4. 生命周期与集成验证

- [x] 4.1 将两个 HTTPX transport 的启动、取消、response 释放和 client 关闭接入 adapter 生命周期，确保重连只恢复现有事件流、不重复初始化状态或创建多个 receive loop；以 `uv run pytest tests/test_adapter_lifecycle.py tests/test_milky_local_integration.py` 验证
- [x] 4.2 在 Hermes Agent 官方依赖环境验证目录 plugin 可延迟导入 HTTPX，确认插件 `pyproject.toml` 和 `uv.lock` 没有新增运行时依赖，且插件独立测试不因顶层缺少 HTTPX 而无法加载；以宿主环境导入检查、`uv lock --check` 和 `uv run pytest` 验证
- [x] 4.3 检查 `milky/client.py` 与 `milky/event_stream.py` 不再包含 urllib HTTP 网络 I/O；允许保留 `urllib.parse` 的纯 URL 解析用途，并以 `rg -n "urllib.request|urlopen|asyncio.to_thread" milky/client.py milky/event_stream.py` 和代码审查验证

## 5. 质量门禁与真实观察

- [x] 5.1 运行并记录 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`、`uv lock --check`、`uv build`、`git diff --check` 和 `npx --yes @fission-ai/openspec@1.11.0 validate --changes --strict`；失败项必须绑定最小复现和回归测试，不得把未执行的检查标为通过
- [x] 5.2 使用运行时注入的 `MILKY_BASE_URL` 与 `MILKY_ACCESS_TOKEN` 执行默认只读 Milky smoke，观察 `/event` 空闲期间连接是否不再固定每 10 秒断开；输出和 tasks 证据只记录连接次数、事件数量、错误类别和时间，不记录 token、Authorization、真实 ID、正文、URL 或路径
- [x] 5.3 按“协议字段/路径、并发/顺序、权限/安全、真实环境差异、测试基础设施”分类记录 smoke 反馈；若真实服务仍断开，区分 EOF、服务端关闭、代理空闲策略和网络错误，并确认无法据此证明事件补发或无损恢复

## 证据台账

- 2026-08-30，协议字段/路径：HTTPX Action 使用 POST JSON 和 Bearer；SSE 使用已确认的 `/event` 请求边界，重连请求没有添加未经 Milky v1.3 OpenAPI 定义的恢复字段。
- 2026-08-30，并发/顺序：`uv run --with httpx==0.28.1 pytest tests/test_milky_client.py tests/test_milky_event_stream.py tests/test_milky_local_integration.py` 结果为 75 passed；覆盖并发 Action、分块 SSE、EOF 重连、handler 隔离和资源关闭。
- 2026-08-30，测试基础设施：无 HTTPX 的独立 uv 环境执行 `uv run pytest` 结果为 273 passed、12 skipped；HTTPX 专项仅因宿主依赖未安装而跳过，插件模块导入时未加载 HTTPX。`uv run ruff check .`、`uv run ruff format --check .`、`uv lock --check`、`uv build`、`git diff --check` 和 OpenSpec strict validation 均通过。
- 2026-08-30，权限/安全：默认只读 smoke 只输出固定分类和计数；未执行任何写入 Action，未把凭证、Authorization、真实 ID、正文、URL 或路径写入日志或台账。
- 2026-08-30，真实环境差异：只读 smoke 结果为 `connection_attempt_count=1`、`received_event_count=0`、`status=timeout`、诊断分类为 `transport_unknown`。随后 11 秒读取探针确认 SSE 连接可建立且同一连接保持空闲，未触发客户端固定 10 秒读取超时；当前证据仍不足以区分服务未来断开时的 EOF、服务端主动关闭、代理策略或网络错误，也不足以证明事件补发或无损恢复。
