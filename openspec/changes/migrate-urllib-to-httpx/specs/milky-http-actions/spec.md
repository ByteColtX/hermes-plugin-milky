## MODIFIED Requirements

### Requirement: HTTP 和协议 envelope 错误必须分类

Action 调用 MUST 区分连接建立、请求写入、响应读取或超时、非 JSON、HTTP 状态错误、协议
`status`/`retcode` 错误、字段缺失和明确不支持的能力；HTTP 200 SHALL NOT 单独代表成功。
持续事件流的读取空闲不得被误用为有副作用 Action 的成功或失败结果。

#### Scenario: HTTP 200 协议失败

- **WHEN** 服务返回 HTTP 200 但 envelope 的 `status` 不是 `ok` 或 `retcode` 非零
- **THEN** 调用 SHALL 返回 `rejected` 错误
- **AND** SHALL NOT 交付成功数据给状态、发送或入站调用方

#### Scenario: 响应不是 JSON

- **WHEN** 服务返回无法解码为 JSON 的响应
- **THEN** 调用 SHALL 返回 `malformed` 错误
- **AND** 错误 SHALL 不包含认证凭证或完整敏感响应

#### Scenario: 请求超时

- **WHEN** Action 的连接、写入或响应读取阶段发生超时且远端是否执行未知
- **THEN** 调用 SHALL 返回 `transport_unknown`
- **AND** 默认 SHALL NOT 自动重发可能产生副作用的消息

#### Scenario: SSE 持续读取保持独立

- **WHEN** SSE 连接在等待事件期间保持打开但暂时没有业务数据
- **THEN** SSE transport SHALL 继续等待或按其事件流契约处理
- **AND** SHALL NOT 将该空闲状态包装成 HTTP Action 的 envelope、成功或失败

### Requirement: 外部参数在请求前校验

Action 参数 MUST 在进入 HTTP 边界前通过类型、范围和目标校验；目标或参数无效时 SHALL 在网络访问前失败。

#### Scenario: 非法群目标

- **WHEN** 出站请求给出空值、负数、非数字或包含额外分隔符的群 ID
- **THEN** 调用 SHALL 返回目标校验失败
- **AND** SHALL NOT 发起 HTTP 请求或回退到默认目标

### Requirement: Action 网络调用不阻塞事件循环且生命周期有界

Action 调用 MUST 在异步边界内执行，不得因一个慢速 Action 阻塞 SSE receive loop 或其他独立
Action；同一 Action client 的并发请求 SHALL 保持各自的响应和错误归属。client 停止后 SHALL
拒绝新请求，并在重复关闭时安全释放其连接池和响应资源。

#### Scenario: 慢速 Action 与 SSE 并行

- **WHEN** 一个 Action 响应延迟，同时 SSE 收到新的事件帧
- **THEN** SSE receive loop SHALL 继续读取并分发事件
- **AND** 慢速 Action SHALL 不改变该事件的帧边界、顺序交接或处理结果

#### Scenario: 并发 Action 独立归属

- **WHEN** 多个 Action 并发请求且其中一个请求失败或超时
- **THEN** 每个调用 SHALL 只返回自身的响应或安全错误分类
- **AND** 一个调用 SHALL 不关闭、覆盖或伪造另一个调用的结果

#### Scenario: client 关闭

- **WHEN** adapter 停止并关闭 Action client
- **THEN** 后续新 Action SHALL 在网络访问前返回关闭/传输不可用错误
- **AND** 重复关闭 SHALL 不产生新请求或资源释放异常
