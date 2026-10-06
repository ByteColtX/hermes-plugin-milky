# Spec Delta

## MODIFIED Requirements

### Requirement: Action 网络调用不阻塞事件循环且生命周期有界

Action 调用 MUST 在异步边界内执行，不得因一个慢速 Action 阻塞 SSE receive loop 或其他独立 Action；同一 Action client 的并发请求 SHALL 保持各自的响应和错误归属。异步 HTTP 资源 MUST 只在其所属事件循环中使用；不同事件循环之间 SHALL 使用隔离的资源上下文，禁止共享会绑定 loop 的连接池。client 停止后 SHALL 拒绝新请求，并在重复关闭时安全释放全部已创建的异步 HTTP 资源。

#### Scenario: 慢速 Action 与 SSE 并行

- **WHEN** 一个 Action 响应延迟，同时 SSE 收到新的事件帧
- **THEN** SSE receive loop SHALL 继续读取并分发事件
- **AND** 慢速 Action SHALL 不改变该事件的帧边界、顺序交接或处理结果

#### Scenario: 并发 Action 独立归属

- **WHEN** 多个 Action 并发请求且其中一个请求失败或超时
- **THEN** 每个调用 SHALL 只返回自身的响应或安全错误分类
- **AND** 一个调用 SHALL 不关闭、覆盖或伪造另一个调用的结果

#### Scenario: 不同事件循环隔离 HTTP 资源

- **WHEN** 普通出站和异步 Tool 在不同事件循环中使用同一个插件客户端边界发起 Action
- **THEN** 每个事件循环 SHALL 使用仅属于自身的异步 HTTP 资源上下文
- **AND** 请求 SHALL 不因跨循环共享连接池而抛出运行时错误或被归类为该错误导致的 `transport_unknown`

#### Scenario: 事件循环结束前的资源回收

- **WHEN** 一个曾使用过 transport 的事件循环仍可运行并进入插件停止清理
- **THEN** 该事件循环创建的异步 HTTP 资源 SHALL 在其所有者事件循环中完成关闭
- **AND** 清理过程 SHALL 不重复关闭、泄漏未完成响应或改变其他事件循环的请求结果

#### Scenario: 所有者事件循环已结束

- **WHEN** transport 发现某个资源的所有者事件循环已经结束，且当前调用无法在该事件循环中执行清理
- **THEN** transport SHALL 不在当前事件循环强行调用该资源的异步关闭方法
- **AND** SHALL 将该资源标记为不可复用并保持既有安全错误/关闭语义；实现与真实 loopback 验证 SHALL 证明正常生命周期路径不会依赖这一降级来完成资源回收

#### Scenario: client 关闭

- **WHEN** adapter 停止并关闭 Action client
- **THEN** 后续新 Action SHALL 在网络访问前返回关闭/传输不可用错误
- **AND** 重复关闭 SHALL 不产生新请求或资源释放异常
