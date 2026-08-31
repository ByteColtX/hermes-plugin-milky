## ADDED Requirements

### Requirement: Home channel 在插件生命周期中可被 Hermes 识别

当 `MILKY_HOME_CHANNEL` 配置有效时，插件 MUST 在不建立网络连接或长期后台任务的注册/配置发现阶段向 Hermes 提供 Milky home channel 元数据，并 MUST 注册 Milky 作为支持 home-channel cron delivery 的平台。该元数据 SHALL 与普通 adapter 的连接就绪状态和入站初始化顺序分离。

#### Scenario: 注册阶段暴露 home channel

- **WHEN** Hermes 发现 Milky plugin 且 `MILKY_HOME_CHANNEL` 已配置
- **THEN** Hermes SHALL 能将 Milky 识别为具有 home channel 的平台
- **AND** plugin 注册阶段 SHALL 不调用 Milky HTTP Action 或启动 SSE

#### Scenario: 配置变更只在下一次启动生效

- **WHEN** 进程启动后环境中的 `MILKY_HOME_CHANNEL` 被改变
- **THEN** 当前运行实例 SHALL 继续使用启动时解析的 home channel
- **AND** SHALL 不在运行中静默切换系统消息目标

#### Scenario: home channel 不跳过普通初始化

- **WHEN** `MILKY_HOME_CHANNEL` 已配置但 Milky 登录或必要状态同步尚未完成
- **THEN** 系统通知的 home target 元数据 MAY 已被 Hermes 发现
- **AND** 普通 `message_receive` SHALL 仍遵守既有初始化就绪门槛
