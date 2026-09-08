## MODIFIED Requirements

### Requirement: Manifest 只声明实际契约

插件 manifest MUST 声明必需的 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的
`MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、
`MILKY_MAX_LOCAL_MEDIA_BYTES`、`MILKY_LONG_TEXT_FORWARD_THRESHOLD`、
`MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 和 `MILKY_PROACTIVE_POLICY`，并声明当前固定的 25 个显式
ToolSpec：`send_profile_like`、`send_friend_nudge`、`send_group_nudge`、`recall_group_message`、
`get_group_info`、`get_group_member_list`、`get_group_member_info`、`set_group_member_mute`、
`set_group_whole_mute`、`get_forwarded_messages`、`get_private_file_download_url`、
`kick_group_member`、`quit_group`、`delete_friend`、`get_friend_requests`、
`accept_friend_request`、`reject_friend_request`、`get_group_file_download_url`、
`accept_group_request`、`reject_group_request`、`accept_group_invitation`、
`reject_group_invitation`、`get_group_files`、`get_friend_info` 和
`set_group_member_special_title`；manifest MUST NOT 声明任意未纳入显式 ToolSpec 的 Action 工具。

#### Scenario: 查看插件配置提示

- **WHEN** Hermes 展示插件的配置项
- **THEN** 它 SHALL 展示 `MILKY_PROACTIVE_POLICY` 为可选 JSON 配置，并保留 token 密码属性、
  可选的 Milky home channel 和本地出站资源大小上限提示
- **AND** SHALL NOT 把主动唤醒配置拆成独立 chat 列表、cooldown 或 timezone 环境变量
- **AND** SHALL NOT 把任意未纳入显式 ToolSpec 的 Action catalog 展示为支持项

### Requirement: 启动时解析正式配置契约

适配器 MUST 在启动时一次性解析必需的 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的
`MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、
`MILKY_MAX_LOCAL_MEDIA_BYTES`、`MILKY_LONG_TEXT_FORWARD_THRESHOLD`、
`MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 和 `MILKY_PROACTIVE_POLICY`；`MILKY_MAX_LOCAL_MEDIA_BYTES`
SHALL 是表示字节数的十进制整数，取值范围 SHALL 为 `8 MiB` 至 `32 MiB`（含边界），省略时 SHALL
使用 `33554432`；`MILKY_PROACTIVE_POLICY` 未设置时 SHALL 使用关闭主动唤醒的默认策略：
`enabled=false`、`idleSeconds=7200`、`maxAttemptsPerDay=1`、`quietHours=null`。配置 JSON MUST
是对象，只允许 `enabled`、`idleSeconds`、`maxAttemptsPerDay` 和 `quietHours` 四个字段；其中
`enabled` MUST 为布尔值，`idleSeconds` MUST 为 `60..604800` 的整数，`maxAttemptsPerDay` MUST
为 `1..24` 的整数，`quietHours` MUST 为 `null` 或包含 `start`/`end` 两个 `HH:MM` 字符串的对象，
且起止时间不得相同。免扰时间使用 Hermes Core 当前时区，配置不得声明时区。缺失必需值、类型错误、
未知字段、JSON 错误、范围错误或时间格式错误 MUST 使启动失败。

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

- **WHEN** `MILKY_MAX_LOCAL_MEDIA_BYTES` 缺失值以外为空、不是十进制整数、低于
  `8 MiB` 或高于 `32 MiB`
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别
- **AND** SHALL 不建立 Milky 网络连接或读取本地资源

#### Scenario: 使用默认主动策略

- **WHEN** `MILKY_PROACTIVE_POLICY` 未配置
- **THEN** 配置 SHALL 保存 `enabled=false`、`idleSeconds=7200`、`maxAttemptsPerDay=1` 和
  `quietHours=null`
- **AND** 插件 SHALL 不启动主动 watcher

#### Scenario: 使用完整 JSON 策略

- **WHEN** 配置为以下 JSON：

  ```json
  {"enabled":true,"idleSeconds":7200,"maxAttemptsPerDay":1,"quietHours":{"start":"23:00","end":"08:00"}}
  ```

- **THEN** 启动 SHALL 接受并保存四个字段
- **AND** 免扰判断 SHALL 使用 Hermes Core 当前时区

#### Scenario: 免扰关闭

- **WHEN** `quietHours` 显式为 `null` 或省略
- **THEN** 配置 SHALL 表示不启用夜间免扰
- **AND** SHALL 不要求或读取独立 timezone 配置

#### Scenario: 跨午夜免扰

- **WHEN** `quietHours.start` 晚于 `quietHours.end`，例如 `23:00` 到 `08:00`
- **THEN** 配置 SHALL 接受该跨午夜区间
- **AND** watcher SHALL 按 Hermes Core 本地时间判断该区间

#### Scenario: 主动策略配置非法

- **WHEN** JSON 不是对象、含未知字段、字段类型错误、`idleSeconds`/`maxAttemptsPerDay` 超出范围、
  `quietHours` 不是 `null` 或合法时间对象，或起止时间相同
- **THEN** 启动 SHALL 失败并指出安全的 `MILKY_PROACTIVE_POLICY` 配置错误类别
- **AND** SHALL 不建立 Milky 网络连接或启动后台任务

#### Scenario: 主动策略不声明 chat、cooldown 或 timezone

- **WHEN** 部署者只配置 `MILKY_PROACTIVE_POLICY`
- **THEN** chat 范围 SHALL 继续完全由 `MILKY_ALLOWED_CHATS` 决定
- **AND** SHALL 不读取 `chats`、`cooldownSeconds`、`timezone` 或同义扩展字段
