# Spec Delta

## ADDED Requirements

### Requirement: 固定 QQ 工具可用于 Milky Gateway Agent 会话

目标 Hermes Gateway MUST 在 Milky 会话使用的 Agent toolset 中提供 manifest 声明的固定 QQ Action 与贴纸工具。工具注册 MUST 独立于 Milky adapter 的连接状态，且工具范围 SHALL 限定于现有固定 operationId，不得扩展为任意 Milky Action catalog。

#### Scenario: Gateway 准备 Milky Agent 工具集

- **WHEN** Gateway 为 Milky 会话准备 Agent toolset
- **THEN** manifest 声明的固定 QQ 工具 SHALL 各注册一次
- **AND** 工具注册 SHALL 不发起 Milky HTTP 请求或 SSE 连接

#### Scenario: Milky Agent 调用固定 QQ 工具

- **WHEN** Milky Agent 调用一个已声明的固定 QQ 工具
- **THEN** 插件 SHALL 只调用对应的固定 operationId，并遵守当前 adapter 的授权和错误边界
- **AND** 未声明的 operation SHALL 在网络调用前失败，且不自动重试
