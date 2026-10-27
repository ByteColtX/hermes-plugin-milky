# Spec Delta

## ADDED Requirements

### Requirement: 指引必须说明工具结果形状与重试语义

Milky system prompt section MUST 说明固定 Action Tool 的两类结果：插件本地失败结果包含
`ok=false`、`classification`、`reason`、`error`、`retryable`；其他结果是从 Milky 原样透传的
响应体，调用方需自行读取 `status`、`retcode`、`message`。指引 MUST 明确：本地失败不得盲目
重试；只有 `client_closed` 可能通过单次重试恢复；`outcome_unknown` 之后不得自动重复有副作用的
Action；配额或权限类远端拒绝重试无效。

#### Scenario: 模型读取本地失败

- **WHEN** 工具返回插件本地失败 JSON
- **THEN** 指引 SHALL 让模型按 `reason` 判断是否可重试
- **AND** SHALL 明确 `client_closed` 之外不得盲目重试

#### Scenario: 模型读取远端原样响应

- **WHEN** 工具返回 Milky 原始响应体
- **THEN** 指引 SHALL 让模型自行检查 `status`、`retcode`、`message`
- **AND** SHALL 说明配额或权限拒绝重试无效
