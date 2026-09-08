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

`MILKY_WILL_POLICY` MUST 支持完整嵌套的 `engine`、`routing`、`willingness` 和 `priority`
字段；routing MUST 支持 `direct`、`mention`、`mentionAll`、`quote`、`poke` 和
`allMessage` 六个 `wait`/`trigger` 动作字段，以及 `keywords` 字符串数组。willingness
MUST 支持数值、增益、force 和时间字段，以及 `interestKeywords`、`forceKeywords` 两个
字符串数组；`interestKeywords` 命中后只用于 `keywordMultiplier` 增益，`forceKeywords`
命中后用于跳过概率抽样并触发。routing MUST NOT 接受 `group`、`image` 或 `mentionHere`
字段。省略 Will policy 时 SHALL 使用架构定义的完整默认 routing，其中 `allMessage` SHALL
为 `wait` 且 `keywords` SHALL 为空数组；willingness 的 `interestKeywords` 和
`forceKeywords` SHALL 为空数组；`MILKY_SESSION_BUFFER_SIZE` 默认 SHALL 为 20，值 0
SHALL 禁用历史缓冲。

#### Scenario: 使用完整嵌套策略

- **WHEN** 配置提供 `engine`、六个 routing 动作、routing `keywords`、willingness 全部
  字段（包括 `interestKeywords` 和 `forceKeywords`）以及 `priority`
- **THEN** 适配器 SHALL 按字段类型和值域保留该策略
- **AND** SHALL 不把嵌套字段合并为旧的扁平策略

#### Scenario: 关键词数组校验

- **WHEN** `routing.keywords` 是字符串数组，且每一项都是非空字符串
- **THEN** 配置 SHALL 接受该数组
- **AND** routing SHALL 将正文命中任意一项解释为确定性 `trigger`

#### Scenario: willingness 关键词数组校验

- **WHEN** `willingness.interestKeywords` 或 `willingness.forceKeywords` 是字符串数组，且
  每一项都是非空字符串
- **THEN** 配置 SHALL 接受对应数组
- **AND** SHALL 保留两个数组的独立语义，不将其合并为单一关键词集合

#### Scenario: 旧 willingness 关键词字段被拒绝

- **WHEN** 配置包含 `willingness.keywords`
- **THEN** 启动 SHALL 失败并指出不支持的 willingness 字段
- **AND** SHALL 不将该字段静默转换为 `interestKeywords`、`forceKeywords` 或其他规则

#### Scenario: 旧 routing 字段被拒绝

- **WHEN** 配置包含 `routing.group`、`routing.image` 或 `routing.mentionHere`
- **THEN** 启动 SHALL 失败并指出不支持的 routing 字段类别
- **AND** SHALL 不将旧字段静默转换为 `allMessage`、关键词或其他规则

#### Scenario: 空关键词数组保持等待默认

- **WHEN** 配置省略或显式提供空的 `routing.keywords`、`willingness.interestKeywords` 和
  `willingness.forceKeywords`
- **THEN** routing SHALL 不产生关键词命中
- **AND** willingness SHALL 不使用关键词增益倍率且 SHALL 不因关键词直接触发

#### Scenario: 非法策略被拒绝

- **WHEN** `engine`、动作值、数值或布尔字段不符合策略契约
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别

### Requirement: Manifest 只声明实际契约

插件 manifest MUST 声明必需的 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的
`MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、
`MILKY_MAX_LOCAL_MEDIA_BYTES`，并声明当前固定的 25 个显式 ToolSpec：
`send_profile_like`、`send_friend_nudge`、`send_group_nudge`、`recall_group_message`、
`get_group_info`、`get_group_member_list`、`get_group_member_info`、`set_group_member_mute`、
`set_group_whole_mute`、`get_forwarded_messages`、`get_private_file_download_url`、
`kick_group_member`、`quit_group`、`delete_friend`、`get_friend_requests`、
`accept_friend_request`、`reject_friend_request`、`get_group_file_download_url`、
`accept_group_request`、`reject_group_request`、`accept_group_invitation`、
`reject_group_invitation`、`get_group_files`、`get_friend_info` 和
`set_group_member_special_title`；manifest MUST NOT 声明任意未纳入显式 ToolSpec 的
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

- **WHEN** `MILKY_MAX_LOCAL_MEDIA_BYTES` 缺失值以外为空、不是十进制整数、低于
`8 MiB` 或高于 `32 MiB`
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别
- **AND** SHALL 不建立 Milky 网络连接或读取本地资源

### Requirement: 超长文本合并转发阈值配置可验证

启动配置 MUST 解析可选的 `MILKY_LONG_TEXT_FORWARD_THRESHOLD`。未配置时值 MUST 为 `0`；值 MUST 是十进制整数且范围为 `0` 至 `4096`（含边界）。值为 `0` 时 MUST 禁用超长文本合并转发；正值 MUST 表示当一次出站文本的可见规范化长度超过该阈值时选择合并转发。配置 MUST 在启动时一次性解析并保存在运行时配置中，且 MUST 出现在配置文档和不含凭证的配置摘要中。

#### Scenario: 未配置时保持普通分块

- **WHEN** `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 未配置
- **THEN** 配置值 SHALL 为 `0`
- **AND** 超长文本 SHALL 继续使用普通文本分块出站

#### Scenario: 零值显式禁用

- **WHEN** `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 配置为 `0`
- **THEN** 启动 SHALL 成功
- **AND** 任意长度的文本 SHALL 不选择合并转发路径

#### Scenario: 正值启用阈值

- **WHEN** `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 配置为 `300`
- **THEN** 启动 SHALL 保存数值 `300`
- **AND** 只有一次出站文本的可见规范化长度大于 `300` 时才允许选择合并转发

#### Scenario: 范围边界值

- **WHEN** 配置值分别为 `1` 或 `4096`
- **THEN** 启动 SHALL 接受对应配置
- **AND** `1` SHALL 表示大于 1 个字符时可选择合并转发，`4096` SHALL 表示大于 4096 个字符时可选择合并转发

#### Scenario: 非法阈值拒绝启动

- **WHEN** 配置为空、不是十进制整数、为负数或大于 `4096`
- **THEN** 启动 SHALL 返回配置错误
- **AND** SHALL 不建立 Milky 网络连接、不读取本地媒体且不创建出站目标

#### Scenario: 合法 home channel

- **WHEN** `MILKY_HOME_CHANNEL` 为 `group:<十进制群号>` 或 `dm:<十进制 QQ 号>`
- **THEN** 配置 SHALL 保留该完整 chat key 供 Hermes 系统/cron 投递使用
- **AND** 该配置 SHALL 不改变 `MILKY_ALLOWED_CHATS` 的入站 Gate 语义

#### Scenario: 非法 home channel

- **WHEN** `MILKY_HOME_CHANNEL` 不是完整的 `group:` 或 `dm:` chat key，或 ID 为空、为负数、含额外分隔符
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别
- **AND** SHALL 不建立 home channel 或发起网络请求

### Requirement: MILKY_ALLOWED_CHATS 支持命名空间通配符

适配器启动时 SHALL 接受 `MILKY_ALLOWED_CHATS` 中的完整 `group:<十进制群号>`、
`dm:<十进制 QQ 号>`、`group:*` 和 `dm:*` 条目；条目两端的空白 SHALL 被裁剪，重复条目
SHALL 归一化。`group:*` SHALL 表示所有合法 group chat，`dm:*` SHALL 表示所有合法 friend
chat；通配符 SHALL 只在完整条目中出现。除上述格式外的通配符、未知场景、空 ID、负数、
额外分隔符和空条目 MUST 使启动失败并指出安全的 `MILKY_ALLOWED_CHATS` 配置错误类别。
空值或未配置时 SHALL 保持空白名单语义，不因该配置拒绝合法 friend/group 消息。

#### Scenario: 混合具体条目和通配符

- **WHEN** `MILKY_ALLOWED_CHATS` 配置为 `group:123, dm:* , dm:*`
- **THEN** 启动 SHALL 成功
- **AND** 解析后的白名单 SHALL 保留 `group:123` 和 `dm:*` 两种授权规则
- **AND** 重复的 `dm:*` SHALL 不产生额外规则

#### Scenario: 通配符按命名空间生效

- **WHEN** `MILKY_ALLOWED_CHATS` 配置为 `dm:*`
- **THEN** 任意合法 `dm:<十进制 QQ 号>` 消息 SHALL 被白名单规则允许
- **AND** 任意合法 `group:<十进制群号>` 消息 SHALL 不因该 `dm:*` 条目被允许

#### Scenario: 非法通配符被拒绝

- **WHEN** `MILKY_ALLOWED_CHATS` 包含 `dm:**`、`group:12*`、`*:123` 或 `private:*` 等非完整通配符条目
- **THEN** 启动 SHALL 失败并指出 `MILKY_ALLOWED_CHATS` 的安全配置错误类别
- **AND** SHALL 不将非法条目静默转换为具体 chat key、`dm:*` 或 `group:*`

#### Scenario: 空白名单保持原有语义

- **WHEN** `MILKY_ALLOWED_CHATS` 未配置或为空字符串
- **THEN** 配置 SHALL 产生空白名单
- **AND** 合法 friend/group 消息 SHALL 不因 ChatAllowlist 被拒绝
