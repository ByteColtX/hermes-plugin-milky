# Spec Delta

## ADDED Requirements

### Requirement: 本地失败必须带固定原因码和可重试提示

固定 Action Tool 返回插件本地失败时 MUST 在结果中包含固定 `reason` 原因码和 `retryable`
布尔值。`reason` MUST 取自固定集合（`configuration_unavailable`、`client_closed`、
`action_not_registered`、`input_invalid`、`service_unavailable`、`outcome_unknown`），
MUST NOT 包含自由文本、异常正文、路径或凭证。`retryable` MUST 只在请求确定未进入网络时为
true；取得响应体的远端拒绝 MUST 继续按原样交付契约返回原始字符串，MUST NOT 附加本地字段。

#### Scenario: 配置不可读

- **WHEN** 进程内没有 live client 且运行时 profile 配置无法解析
- **THEN** 工具 SHALL 返回 `classification=unsupported` 与 `reason=configuration_unavailable`
- **AND** `retryable` SHALL 为 false
- **AND** SHALL 不创建 client、不发起 HTTP 请求

#### Scenario: 客户端已关闭

- **WHEN** 已绑定的 live client 在调用时处于关闭状态
- **THEN** 工具 SHALL 返回 `classification=unsupported` 与 `reason=client_closed`
- **AND** `retryable` SHALL 为 true，因为该请求未进入网络
- **AND** SHALL 不发起 HTTP 请求

#### Scenario: 传输结果未知

- **WHEN** Action 已进入 HTTP 边界但未取得响应体
- **THEN** 工具 SHALL 返回 `classification=transport_unknown` 与 `reason=outcome_unknown`
- **AND** `retryable` SHALL 为 false
- **AND** SHALL NOT 自动重试

#### Scenario: 远端业务拒绝

- **WHEN** Milky 返回 HTTP 200 且响应体中的 `status` 非 `ok` 或 `retcode` 非零
- **THEN** 工具 SHALL 原样交付该响应体
- **AND** SHALL NOT 附加 `reason`、`retryable` 或其他本地字段

### Requirement: `send_profile_like` 的 `count` 必须与 schema 一致

`send_profile_like` 的 `count` 在 handler、client 和参数校验层 MUST 统一限制为闭区间
`1..50`，与实际 schema 声明一致。越界值 MUST 在网络访问前返回 `invalid_input`。

#### Scenario: count 越界

- **WHEN** 调用方传入 `count` 为 0、负数或大于 50
- **THEN** 工具 SHALL 在网络访问前返回 `classification=invalid_input`
- **AND** SHALL 不发出 Action 请求

#### Scenario: count 边界值

- **WHEN** 调用方传入 `count` 为 1 或 50
- **THEN** 工具 SHALL 按一次 Action 发出该值
