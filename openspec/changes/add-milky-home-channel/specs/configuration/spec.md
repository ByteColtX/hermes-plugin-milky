## REMOVED Requirements

### Requirement: 启动时只接受新配置契约

**Reason**: 原 requirement 包含旧配置名检测和迁移判断；本 change 不负责探测、读取或处理旧配置名。

**Migration**: 部署只使用本 change 声明的正式配置变量；其他环境变量不属于本 change 的配置行为。

## ADDED Requirements

### Requirement: 启动时解析正式配置契约

适配器 MUST 在启动时一次性解析必需的 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的 `MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`；缺失必需值、类型错误、范围错误或 home channel 目标格式错误 MUST 使启动失败。

#### Scenario: 缺少必需配置

- **WHEN** `MILKY_BASE_URL` 或 `MILKY_ACCESS_TOKEN` 缺失
- **THEN** 启动 SHALL 失败并指出缺少的配置名
- **AND** 错误 SHALL NOT 包含 token 值

#### Scenario: 合法 home channel

- **WHEN** `MILKY_HOME_CHANNEL` 为 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>`
- **THEN** 配置 SHALL 保留该完整 chat key 供 Hermes 系统/cron 投递使用
- **AND** 该配置 SHALL 不改变 `MILKY_ALLOWED_CHATS` 的入站 Gate 语义

#### Scenario: 非法 home channel

- **WHEN** `MILKY_HOME_CHANNEL` 不是完整的 `group:` 或 `dm:` chat key，或 ID 为空、为负数、含额外分隔符
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别
- **AND** SHALL 不建立 home channel 或发起网络请求

## MODIFIED Requirements

### Requirement: Manifest 只声明实际契约

插件 manifest MUST 声明必需的 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的 `MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`，声明 `provides_tools` 且仅包含 `milky_profile_like`、`milky_nudge` 和 `milky_recall_group_message`，并 MUST NOT 声明任意未纳入显式 ToolSpec 的 Action 工具。

#### Scenario: 查看插件配置提示

- **WHEN** Hermes 展示插件的配置项
- **THEN** 它 SHALL 展示新配置契约、token 密码属性和可选的 Milky home channel
- **AND** SHALL NOT 把任意未纳入显式 ToolSpec 的 Action catalog 展示为支持项
