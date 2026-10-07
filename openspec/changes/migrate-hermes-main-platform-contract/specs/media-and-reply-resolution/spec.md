# Spec Delta

## ADDED Requirements

### Requirement: 入站本地媒体属于实际接收消息的 profile

Milky 消息映射到 Hermes profile 后，交给 Agent 的本地媒体路径 MUST 可由该 profile 的 Gateway 安全访问。插件 MUST 使用 Hermes helper 或 Gateway 返回的当前 profile materialization，不得猜测路径、跨 profile 复用缓存文件或自行绕过媒体边界。

#### Scenario: 多 profile 路由图片消息

- **WHEN** Milky 图片资源在一个 profile 中 materialize，而事件由另一个 profile 的 Gateway session 处理
- **THEN** MessageEvent SHALL 只引用当前 profile 可访问的 materialization
- **AND** 原 profile 的路径 SHALL 不作为跨 profile 访问的替代路径

#### Scenario: 当前 profile materialization 无法确认

- **WHEN** 下载、缓存或 profile 重定位失败，或 Hermes 未返回当前 profile 可用的本地路径
- **THEN** 媒体 SHALL 不进入 MessageEvent 的本地媒体字段
- **AND** 消息 SHALL 保留安全占位和可分类诊断
- **AND** 插件 SHALL 不构造远端 URL、猜测路径或私自复制缓存文件
