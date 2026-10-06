# Tasks

## 1. Transport 所有权与资源管理

- [ ] 1.1 在 Action HTTP transport 中建立按事件循环隔离的异步客户端资源上下文，保持同 loop 复用并拒绝跨 loop 共享；验证同 loop 请求复用、不同 loop 请求使用不同客户端且不出现跨 loop `RuntimeError`。
- [ ] 1.2 实现 loop-local 客户端的关闭、映射移除和已结束 loop 的安全放弃逻辑，保持 transport/client 重复关闭幂等；验证关闭后新请求在网络访问前失败，且其他 loop 的资源仍可独立关闭。
- [ ] 1.3 保持现有 HTTP、协议、取消和 `transport_unknown` 边界不变；验证慢请求、并发请求、HTTP 错误和传输未知结果仍按原分类返回。

## 2. 回归测试与运行验证

- [ ] 2.1 增加基于 fake 或本地 loopback HTTP 的跨事件循环回归测试，覆盖普通出站与异步 Tool 使用不同 loop、并发隔离、loop 结束和重复关闭；验证 `uv run pytest -q` 的相关测试通过。
- [ ] 2.2 增加资源生命周期和日志边界断言，确认不记录 token、Authorization、原始响应、请求正文、URL 或异常正文；验证 `uv run ruff check .`、`uv run ruff format --check .` 和 `git diff --check`。
- [ ] 2.3 在 hermes-dev 执行只读或受控健康检查，确认不同事件循环的 Action 调用不再出现由共享 HTTPX 连接池导致的毫秒级 `transport_unknown`；记录真实 Hermes/Milky 验证或外部阻塞，不将 fake/loopback 结果写成真实集成通过。

## Workflow follow-up

- 完成实现和验证后，运行 `openspec validate --changes --strict`。
- 通过审阅后再归档该 change。
