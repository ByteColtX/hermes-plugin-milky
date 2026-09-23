# Spec Delta

## MODIFIED Requirements

### Requirement: HTTP 和协议 envelope 错误必须分类

非 Tool Action 调用 MUST 区分连接建立、请求写入、响应读取或超时、非 JSON、HTTP 状态错误、协议
`status`/`retcode` 错误、字段缺失和明确不支持的能力；HTTP 200 SHALL NOT 单独代表成功。已经进入
HTTP 请求边界但尚未收到可确认响应的非 Tool Action MUST 返回 `transport_unknown`，不得暗示远端未
执行；持续事件流的读取空闲不得被误用为有副作用 Action 的成功或失败结果。已注册 Tool 遵循独立
的原样交付契约：只要取得响应体，HTTP 或协议状态不再转换为插件错误分类。

#### Scenario: HTTP 200 协议失败

- **WHEN** 登录、状态同步、消息发送或上传等非 Tool Action 服务返回 HTTP 200 但 envelope 的 `status`
  不是 `ok` 或 `retcode` 非零
- **THEN** 调用 SHALL 返回 `rejected` 错误
- **AND** SHALL NOT 交付成功数据给状态、发送或入站调用方

#### Scenario: 响应不是 JSON

- **WHEN** 非 Tool Action 服务返回无法解码为 JSON 的响应
- **THEN** 调用 SHALL 返回 `malformed` 错误
- **AND** 错误 SHALL 不包含认证凭证或完整敏感响应

#### Scenario: Tool 收到协议或 HTTP 错误

- **WHEN** 已注册 Tool 收到 HTTP 4xx/5xx、协议拒绝、非 JSON 文本或其他可取得响应体
- **THEN** Tool SHALL 将该响应体原样交付给调用方
- **AND** SHALL 不返回 `rejected`、`http_error` 或 `malformed` 插件结果

#### Scenario: 请求超时

- **WHEN** Action 的连接、写入或响应读取阶段发生超时且远端是否执行未知
- **THEN** 调用 SHALL 返回 `transport_unknown`
- **AND** 默认 SHALL NOT 自动重发可能产生副作用的消息

#### Scenario: SSE 持续读取保持独立

- **WHEN** SSE 连接在等待事件期间保持打开但暂时没有业务数据
- **THEN** SSE transport SHALL 继续等待或按其事件流契约处理
- **AND** SHALL NOT 将该空闲状态包装成 HTTP Action 的 envelope、成功或失败

#### Scenario: 请求已到达但响应路径中断

- **WHEN** 一个可能产生副作用的 POST Action 已进入远端处理，客户端在收到完整成功响应前遇到连接中断、
  写入错误、读取错误或其他传输异常
- **THEN** 调用 SHALL 返回 `transport_unknown`，不得返回成功或生成本地消息 ID
- **AND** 调用链 SHALL NOT 将该结果解释为“远端未执行”或自动再次提交同一 Action

### Requirement: Action 数据满足最小结构才算成功

非 Tool Action 调用方 MUST 校验当前 Action 所需的最小 `data` 结构，并允许安全保留未知字段而不将
未知字段解释为已支持能力。Milky v1.3 的成功 data 是按 Action 定义的对象：登录信息使用
`data.uin`/`data.nickname`，群列表使用 `data.groups`，成员查询使用 `data.member`，而不是把这些
data 对象当作数组或直接 ID。已注册 Tool 不执行本结构校验；取得响应体即交付其原始字符串。

#### Scenario: 发送成功返回远端序号

- **WHEN** 消息发送 Action 返回成功 envelope 且 `data.message_seq` 存在
- **THEN** 发送结果 SHALL 使用该远端序号的稳定字符串形式作为消息 ID
- **AND** SHALL NOT 使用时间、随机数或本地计数器伪造消息 ID

#### Scenario: 发送成功缺少序号

- **WHEN** 消息发送服务返回成功 envelope 但缺少 `data.message_seq`
- **THEN** 调用 SHALL 返回 `malformed` 错误
- **AND** SHALL NOT 报告假成功或生成本地消息 ID

#### Scenario: 状态同步 data 层级

- **WHEN** `get_login_info`、`get_group_list` 或 `get_group_member_info` 等非 Tool 状态同步 Action 返回成功 envelope
- **THEN** 调用方 SHALL 分别从 `data.uin`、`data.groups` 和 `data.member` 读取最小结果
- **AND** SHALL 将缺失、错误容器类型或错误字段层级分类为 `malformed`

#### Scenario: Tool 保留未知 data 结构

- **WHEN** 已注册 Tool 返回缺少历史最小字段、非对象 data、数组、标量或显式 `null`
- **THEN** Tool SHALL 将已取得的响应体原样交付
- **AND** SHALL 不返回 `malformed` 或补造成功结果
