# configuration Specification

## Purpose

集中定义 Milky 适配器的启动配置、默认值和安全摘要，使部署者可以明确配置连接、
聊天范围、Will 策略与 wait 缓冲，而不会因旧配置或凭证泄露产生歧义。

## Requirements

### Requirement: URL 和 Bearer 凭证安全派生

配置 SHALL 去除 `MILKY_BASE_URL` 的末尾斜杠但保留已有 path prefix，并从同一 scheme、host、port 与 prefix 派生 HTTP Action 路径和事件 `/event` 路径；凭证 SHALL 只用于认证并在所有用户可见诊断中脱敏。

#### Scenario: 带 prefix 的 HTTP 基址

- **WHEN** 基址为 `http://localhost:5500/milky/`
- **THEN** Action URL SHALL 形成为 `http://localhost:5500/milky/api/{action}`
- **AND** 事件 URL SHALL 形成为 `http://localhost:5500/milky/event`

#### Scenario: 凭证出现在错误路径

- **WHEN** 连接、解析或远端请求产生错误
- **THEN** 错误、日志、结果和快照 SHALL 不包含 token 或完整 `Authorization` header

### Requirement: Will 和缓冲配置保持嵌套且可验证

`MILKY_WILL_POLICY` MUST 支持完整嵌套的 `engine`、`routing`、`willingness` 和 `priority` 字段；省略时 SHALL 使用架构定义的完整默认 routing；`MILKY_SESSION_BUFFER_SIZE` 默认 SHALL 为 20，值 0 SHALL 禁用历史缓冲。

#### Scenario: 使用完整嵌套策略

- **WHEN** 配置提供 `engine`、八个 routing 动作、willingness 全部字段和 `priority`
- **THEN** 适配器 SHALL 按字段类型和值域保留该策略
- **AND** SHALL 不把嵌套字段合并为旧的扁平策略

#### Scenario: 非法策略被拒绝

- **WHEN** `engine`、动作值、数值或布尔字段不符合策略契约
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别

### Requirement: Manifest 只声明实际契约

插件 manifest MUST 声明必需的 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的 `MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`，声明 `provides_tools` 且仅包含 `milky_profile_like`、`milky_nudge` 和 `milky_recall_group_message`，并 MUST NOT 声明任意未纳入显式 ToolSpec 的 Action 工具。

#### Scenario: 查看插件配置提示

- **WHEN** Hermes 展示插件的配置项
- **THEN** 它 SHALL 展示新配置契约、token 密码属性和可选的 Milky home channel
- **AND** SHALL NOT 把任意未纳入显式 ToolSpec 的 Action catalog 展示为支持项

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
