# Proposal

## Why

插件当前会在一个 `HttpxTransport` 实例中复用懒创建的 HTTPX 异步客户端。Hermes 的普通出站和异步 Tool 调用可能运行在不同事件循环，同一个连接池跨 loop 使用会抛出运行时异常，随后被插件隐藏成 `transport_unknown`，造成本来可用的请求失败并触发错误恢复。

## What Changes

- 让 HTTPX 连接池与创建它的事件循环绑定，禁止跨事件循环复用同一个异步客户端。
- 为同一事件循环保持可复用的客户端；其他事件循环使用各自隔离的客户端或等价的 loop-affine 请求路径。
- 在插件生命周期结束时回收由 transport 创建的全部 loop-local 客户端，并保持重复关闭安全。
- 增加跨事件循环请求、并发请求、关闭和 loop 结束后的失败分类测试；跨 loop 不再把可避免的连接池复用异常伪装成正常业务拒绝。
- 保持 Hermes core、Milky Action 协议、消息分段、重试语义和 Tool 原样响应契约不变。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `milky-http-actions`: Action transport 必须遵守事件循环所有权，不能跨 loop 复用异步 HTTP 客户端；生命周期关闭必须覆盖 transport 创建的 loop-local 资源。

## Impact

- 主要影响 `milky/client.py` 中的 HTTPX transport 生命周期和客户端缓存。
- 需要更新 HTTPX transport 的单元测试，覆盖 Gateway 出站与异步 Tool 使用不同事件循环的场景。
- 不修改 Hermes core，不改变公开 Milky Action 字段或发送结果分类；真实 Hermes/Milky 集成仍需单独验证。
