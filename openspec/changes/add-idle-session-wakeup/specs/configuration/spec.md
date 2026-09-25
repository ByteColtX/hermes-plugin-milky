## MODIFIED Requirements

### Requirement: Manifest 只声明实际契约

插件 manifest MUST 声明普通配置 schema 和绑定 MILKY_ACCESS_TOKEN 的 secret。连接地址 SHALL 为必需的
有效配置，但不得要求它只能来自环境变量；凭证 SHALL 继续使用宿主凭证机制。兼容环境来源 SHALL 包括
`MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的 `MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、
`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、`MILKY_MAX_LOCAL_MEDIA_BYTES`、
`MILKY_LONG_TEXT_FORWARD_THRESHOLD`、`MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 和
`MILKY_PROACTIVE_POLICY`，并保留当前固定的 25 个显式 Milky Action ToolSpec：`send_profile_like`、
`send_friend_nudge`、`send_group_nudge`、`recall_group_message`、`get_group_info`、
`get_group_member_list`、`get_group_member_info`、`set_group_member_mute`、`set_group_whole_mute`、
`get_forwarded_messages`、`get_private_file_download_url`、`kick_group_member`、`quit_group`、
`delete_friend`、`get_friend_requests`、`accept_friend_request`、`reject_friend_request`、
`get_group_file_download_url`、`accept_group_request`、`reject_group_request`、
`accept_group_invitation`、`reject_group_invitation`、`get_group_files`、`get_friend_info` 和
`set_group_member_special_title`；manifest MUST NOT 声明任意未纳入显式 ToolSpec 的 Action 工具。
另 SHALL 保留现有 `sticker_send` 与 `sticker_search` 的独立工具声明及各自可用性契约，本变更不新增
通用 Action 或发送入口。

#### Scenario: 查看插件配置提示

- **WHEN** Hermes 展示插件的配置项
- **THEN** 它 SHALL 展示新配置契约、token 密码属性、可选的 Milky home channel 和本地出站资源大小上限
  提示
- **AND** SHALL 展示 `MILKY_MAX_LOCAL_MEDIA_BYTES` 的默认值为 `33554432` 字节（`32 MiB`）
- **AND** SHALL 展示 `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 的默认值为 `0`
- **AND** SHALL 展示 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 的默认值为 `false`
- **AND** SHALL 展示 `MILKY_PROACTIVE_POLICY` 为可选 JSON 配置
- **AND** SHALL NOT 把主动唤醒配置拆成独立 chat 列表、cooldown 或 timezone 环境变量
- **AND** SHALL NOT 把任意未纳入显式 ToolSpec 的 Action catalog 展示为支持项

#### Scenario: 只有 YAML 地址也能被宿主发现

- **WHEN** 当前 profile 已配置有效的插件 base_url 设置和宿主凭证，但没有 MILKY_BASE_URL 环境变量
- **THEN** 插件配置发现与平台启动 SHALL 接受已解析的有效地址
- **AND** SHALL 不因缺少旧地址环境变量而阻止加载

#### Scenario: 宿主展示插件设置

- **WHEN** 宿主读取插件配置声明
- **THEN** 普通字段 SHALL 使用与运行时一致的名称、类型、默认值和选项
- **AND** token SHALL 只作为绑定 MILKY_ACCESS_TOKEN 的 secret 展示，不写入普通设置

### Requirement: 启动时解析正式配置契约

适配器 MUST 按本规范的来源优先级在启动时一次性解析配置。以下 MILKY_* 名称表示对应配置及其兼容环境输入，
相同校验 SHALL 适用于最终选中的原生类型设置；必需连接地址可来自任一合法普通配置来源，凭证来自宿主凭证机制。
`MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的 `MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、
`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、`MILKY_MAX_LOCAL_MEDIA_BYTES`、
`MILKY_LONG_TEXT_FORWARD_THRESHOLD`、`MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 和
`MILKY_PROACTIVE_POLICY` SHALL 共同构成启动配置；`MILKY_MAX_LOCAL_MEDIA_BYTES` SHALL 是表示字节数的十进制整数，
取值范围 SHALL 为 `8 MiB` 至 `32 MiB`（含边界），所有来源均省略该项时 SHALL 使用 `33554432`；
`MILKY_PROACTIVE_POLICY` 未设置时 SHALL 使用关闭主动唤醒的默认策略：`enabled=false`、`idleSeconds=7200`、
`maxAttemptsPerDay=1`、`quietHours=null`。配置 JSON MUST 是对象，只允许 `enabled`、`idleSeconds`、
`maxAttemptsPerDay` 和 `quietHours` 四个字段；其中 `enabled` MUST 为布尔值，`idleSeconds` MUST 为
`60..604800` 的整数，`maxAttemptsPerDay` MUST 为 `1..24` 的整数，`quietHours` MUST 为 `null` 或包含
`start`/`end` 两个 `HH:MM` 字符串的对象，且起止时间不得相同。免扰时间使用 Hermes Core 当前时区，配置不得声明时区。
缺失必需值、类型错误、未知字段、JSON 错误、范围错误或时间格式错误 MUST 使启动失败。

#### Scenario: 缺少必需配置

- **WHEN** 所有合法来源均未提供必需的连接地址或宿主凭证
- **THEN** 启动 SHALL 失败并指出缺少的配置名
- **AND** 错误 SHALL NOT 包含 token 值

#### Scenario: 使用默认出站资源上限

- **WHEN** 所有普通配置来源均未提供本地出站资源上限
- **THEN** 配置 SHALL 保存 `33554432` 字节作为本地出站资源上限
- **AND** 该默认值 SHALL 供图片、语音、视频、文档和 CQ sticker 的本地出站路径使用

#### Scenario: 使用自定义出站资源上限

- **WHEN** 按优先级选中的本地出站资源上限是范围内的整数（环境输入使用十进制文本），例如 `16777216`
- **THEN** 配置 SHALL 保存该数值
- **AND** 出站本地资源 SHALL 按该值判断是否超限

#### Scenario: 非法出站资源上限

- **WHEN** 按优先级选中的本地出站资源上限为空、类型或十进制格式错误、低于 `8 MiB` 或高于 `32 MiB`
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别
- **AND** SHALL 不建立 Milky 网络连接或读取本地资源

#### Scenario: 多入口保持同一启动快照

- **WHEN** 当前实例已经完成配置解析，随后操作者保存新设置
- **THEN** 该实例的普通 adapter、独立 sender 和 home-channel 元数据 SHALL 保持已解析快照
- **AND** 新设置 SHALL 在新的启动或宿主明确重新加载该配置后才适用

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
