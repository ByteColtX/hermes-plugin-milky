## MODIFIED Requirements

### Requirement: Manifest 只声明实际契约

插件 manifest MUST 声明必需的 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的
`MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、
`MILKY_MAX_LOCAL_MEDIA_BYTES`，声明 `provides_tools` 且仅包含 `milky_profile_like`、
`milky_nudge` 和 `milky_recall_group_message`，并 MUST NOT 声明任意未纳入显式 ToolSpec 的
Action 工具。

#### Scenario: 查看插件配置提示

- **WHEN** Hermes 展示插件的配置项
- **THEN** 它 SHALL 展示新配置契约、token 密码属性、可选的 Milky home channel 和本地出站
  资源大小上限
- **AND** SHALL 展示 `MILKY_MAX_LOCAL_MEDIA_BYTES` 的默认值为 `33554432` 字节（`32 MiB`）
- **AND** SHALL NOT 把任意未纳入显式 ToolSpec 的 Action catalog 展示为支持项

### Requirement: 启动时解析正式配置契约

适配器 MUST 在启动时一次性解析必需的 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的
`MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、
`MILKY_MAX_LOCAL_MEDIA_BYTES`；`MILKY_MAX_LOCAL_MEDIA_BYTES` SHALL 是表示字节数的十进制整数，
取值范围 SHALL 为 `8 MiB` 至 `32 MiB`（含边界），省略时 SHALL 使用 `33554432`；缺失必需值、
类型错误、范围错误或 home channel 目标格式错误 MUST 使启动失败。

#### Scenario: 缺少必需配置

- **WHEN** `MILKY_BASE_URL` 或 `MILKY_ACCESS_TOKEN` 缺失
- **THEN** 启动 SHALL 失败并指出缺少的配置名
- **AND** 错误 SHALL NOT 包含 token 值

#### Scenario: 使用默认出站资源上限

- **WHEN** 未提供 `MILKY_MAX_LOCAL_MEDIA_BYTES`
- **THEN** 配置 SHALL 保存 `33554432` 字节作为本地出站资源上限
- **AND** 该默认值 SHALL 供图片、语音、视频、文档和 CQ sticker 的本地出站路径使用

#### Scenario: 使用自定义出站资源上限

- **WHEN** `MILKY_MAX_LOCAL_MEDIA_BYTES` 是范围内的十进制字节数，例如 `16777216`
- **THEN** 配置 SHALL 保存该数值
- **AND** 出站本地资源 SHALL 按该值判断是否超限

#### Scenario: 非法出站资源上限

- **WHEN** `MILKY_MAX_LOCAL_MEDIA_BYTES` 缺失值以外为空、不是十进制整数、低于 `8 MiB` 或高于
  `32 MiB`
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别
- **AND** SHALL 不建立 Milky 网络连接或读取本地资源

#### Scenario: 合法 home channel

- **WHEN** `MILKY_HOME_CHANNEL` 为 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>`
- **THEN** 配置 SHALL 保留该完整 chat key 供 Hermes 系统/cron 投递使用
- **AND** 该配置 SHALL 不改变 `MILKY_ALLOWED_CHATS` 的入站 Gate 语义

#### Scenario: 非法 home channel

- **WHEN** `MILKY_HOME_CHANNEL` 不是完整的 `group:` 或 `dm:` chat key，或 ID 为空、为负数、含额外分隔符
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别
- **AND** SHALL 不建立 home channel 或发起网络请求
