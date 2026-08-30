## MODIFIED Requirements

### Requirement: HTTP 和协议 envelope 错误必须分类

Action 调用 MUST 区分连接建立、请求写入、响应读取或超时、非 JSON、HTTP 状态错误、协议 `status`/`retcode` 错误、字段缺失和明确不支持的能力；HTTP 200 SHALL NOT 单独代表成功。已经进入 HTTP 请求边界但尚未收到可确认响应的 Action MUST 返回 `transport_unknown`，不得暗示远端未执行；持续事件流的读取空闲不得被误用为有副作用 Action 的成功或失败结果。

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

#### Scenario: 请求已到达但响应路径中断

- **WHEN** 一个可能产生副作用的 POST Action 已进入远端处理，客户端在收到完整成功响应前遇到连接中断、写入错误、读取错误或其他传输异常
- **THEN** 调用 SHALL 返回 `transport_unknown`，不得返回成功或生成本地消息 ID
- **AND** 调用链 SHALL NOT 将该结果解释为“远端未执行”或自动再次提交同一 Action

#### Scenario: SSE 持续读取保持独立

- **WHEN** SSE 连接在等待事件期间保持打开但暂时没有业务数据
- **THEN** SSE transport SHALL 继续等待或按其事件流契约处理
- **AND** SHALL NOT 将该空闲状态包装成 HTTP Action 的 envelope、成功或失败
