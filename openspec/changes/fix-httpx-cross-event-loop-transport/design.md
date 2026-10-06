# Design

## Context

See `proposal.md` for the observed failure. 当前 `HttpxTransport` 懒创建并长期复用一个异步 HTTP 客户端；同一插件实例可能被普通 Gateway 出站和异步 Tool 调用共享，而两条路径不保证运行在同一个事件循环。transport 仍须由插件拥有，并在 adapter 停止时关闭；不能修改 Hermes core 或把未知结果改报成功。

## Goals / Non-Goals

**Goals:**

- 为每个使用 transport 的事件循环建立明确的异步 HTTP 资源所有权。
- 保持同一事件循环内的连接复用和并发请求能力。
- 让跨 loop 调用得到隔离的请求路径，避免 HTTPX 连接池跨 loop 触发运行时错误。
- 让停止清理覆盖所有已创建资源，并在 loop 已结束时安全处理。
- 用 fake transport、真实 HTTP loopback 和多 loop 测试证明行为。

**Non-Goals:**

- 不修改 Hermes core、delivery ledger 或恢复文案。
- 不改变 Milky Action 请求/响应字段、`transport_unknown` 的未知结果语义或副作用 Action 的最多一次边界。
- 不处理多段消息的状态聚合、部分成功恢复或 Milky 服务端拒绝原因。
- 不要求把所有请求强制调度回单一全局事件循环；实现可选择 loop-local client 或等价的隔离机制，但对外行为必须符合 delta spec。

## Decisions

### 1. 按事件循环隔离异步 HTTP 客户端

transport 保存“所属事件循环到异步客户端”的受控映射；第一次在某个 loop 发起请求时创建该 loop 的客户端，后续同 loop 请求复用它。每次请求先确认 loop 仍可用且客户端未关闭，禁止把其他 loop 的客户端交给当前请求。

替代方案是把所有调用 `run_coroutine_threadsafe` 调回 adapter 的主 loop。该方案依赖宿主 loop 始终存活，并会把 Tool 调用耦合到 Gateway 调度；loop-local 隔离更符合当前 transport 所有权边界，也能维持不同调用方的独立性。

### 2. 关闭由 transport 统一协调

`close()` 将 transport 标记为关闭，阻止新请求，并安排每个 loop-local 客户端在其所有者 loop 仍可运行时完成关闭。若某个 loop 已结束或无法在当前上下文安全关闭，则不得从当前 loop 强行 await 该客户端；资源只可标记为不可复用并进入既有安全降级路径，正常生命周期必须在 loop 结束前完成清理。所有关闭路径保持幂等。

这避免在错误 loop 上直接 await 客户端关闭，也避免为了清理而重启或阻塞已经结束的事件循环。

### 3. 将 loop 生命周期测试作为 transport 契约

测试至少覆盖：同 loop 复用、不同 loop 隔离、两个 loop 并发请求、一个 loop 失败不污染另一个 loop、loop 结束后关闭，以及关闭后新请求在网络访问前失败。使用本地 loopback HTTP 服务或 HTTPX mock 验证真实异步客户端路径；不发送 QQ 消息。

## Risks / Trade-offs

- [连接池数量随并发事件循环增加] -> loop-local client 只在实际使用的 loop 创建，并在 adapter 停止和可确认的 loop 结束路径回收；记录低基数资源计数以便诊断，不记录 URL、body 或凭证。
- [无法在已结束 loop 中 await close] -> 不跨 loop 调用异步关闭；由所有者 loop 的停止任务在结束前完成正常回收，异常降级只标记资源不可复用并保持主关闭流程继续。
- [HTTPX 客户端构造或关闭异常] -> 继续归类为 `transport_unknown`，不伪造成功，不改变副作用 Action 的不自动重试规则。
- [实现与 SSE transport 的边界不一致] -> 本 change 只覆盖 Action transport；SSE 的独立连接生命周期保持现状，另行评估。

## Migration Plan

1. 在插件侧实现 loop-local Action transport 资源管理。
2. 添加并通过单元、loopback 和跨 loop 回归测试。
3. 在 hermes-dev 以只读/受控健康检查验证不同 loop 的 Action 请求不再出现毫秒级跨 loop `transport_unknown`。
4. 回滚时恢复原 transport 实现；无需迁移数据、修改 Hermes core 或变更 Milky 服务端。

## Open Questions

无。
