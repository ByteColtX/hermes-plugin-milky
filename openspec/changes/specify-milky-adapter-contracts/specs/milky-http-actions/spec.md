## Purpose

定义 Milky HTTP Action 的统一调用、认证、响应校验和错误语义，使登录、状态、资源、
发送与上传等外部交互可在 fake transport 和真实协议 fixture 中稳定验证。

## ADDED Requirements

### Requirement: Action 使用统一 POST 请求

每个 Milky Action MUST 使用派生的 `/api/{action}` 路径、HTTP POST、JSON body 和 Bearer 认证；无参数 Action 也 MUST 发送 `{}`。

#### Scenario: 调用无参数 Action

- **WHEN** 适配器调用不需要参数的登录信息 Action
- **THEN** 请求 SHALL 使用 POST 访问对应的 `/api/get_login_info`
- **AND** JSON body SHALL 为 `{}`
- **AND** 请求 SHALL 包含 `Authorization: Bearer <token>`

#### Scenario: 带 prefix 的 Action

- **WHEN** base URL 含有 `/milky` path prefix
- **THEN** 群列表 Action SHALL 访问 `/milky/api/get_group_list`
- **AND** SHALL NOT 访问 `/api/milky/api/get_group_list` 或 query string 替代路径

### Requirement: HTTP 和协议 envelope 错误必须分类

Action 调用 MUST 区分连接或超时、非 JSON、HTTP 状态错误、协议 `status`/`retcode` 错误、字段缺失和明确不支持的能力；HTTP 200 SHALL NOT 单独代表成功。

#### Scenario: HTTP 200 协议失败

- **WHEN** 服务返回 HTTP 200 但 envelope 的 `status` 不是 `ok` 或 `retcode` 非零
- **THEN** 调用 SHALL 返回 `rejected` 错误
- **AND** SHALL NOT 交付成功数据给状态、发送或入站调用方

#### Scenario: 响应不是 JSON

- **WHEN** 服务返回无法解码为 JSON 的响应
- **THEN** 调用 SHALL 返回 `malformed` 错误
- **AND** 错误 SHALL 不包含认证凭证或完整敏感响应

#### Scenario: 请求超时

- **WHEN** 发送请求后发生超时且远端是否执行未知
- **THEN** 调用 SHALL 返回 `transport_unknown`
- **AND** 默认 SHALL NOT 自动重发可能产生副作用的消息

### Requirement: Action 数据满足最小结构才算成功

调用方 MUST 校验当前 Action 所需的最小 `data` 结构，并允许安全保留未知字段而不将未知字段解释为已支持能力。

#### Scenario: 发送成功返回远端序号

- **WHEN** 发送 Action 返回成功 envelope 且 `data.message_seq` 存在
- **THEN** 发送结果 SHALL 使用该远端序号的稳定字符串形式作为消息 ID
- **AND** SHALL NOT 使用时间、随机数或本地计数器伪造消息 ID

#### Scenario: 发送成功缺少序号

- **WHEN** 服务返回成功 envelope 但缺少 `data.message_seq`
- **THEN** 调用 SHALL 返回 `malformed` 错误
- **AND** SHALL NOT 报告假成功或生成本地消息 ID

### Requirement: 外部参数在请求前校验

Action 参数 MUST 在进入 HTTP 边界前通过类型、范围和目标校验；目标或参数无效时 SHALL 在网络访问前失败。

#### Scenario: 非法群目标

- **WHEN** 出站请求给出空值、负数、非数字或包含额外分隔符的群 ID
- **THEN** 调用 SHALL 返回目标校验失败
- **AND** SHALL NOT 发起 HTTP 请求或回退到默认目标
