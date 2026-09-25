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

插件 manifest MUST 声明普通配置 schema 和绑定 MILKY_ACCESS_TOKEN 的 secret。连接地址 SHALL 为必需的有效配置，但不得要求它只能来自环境变量；凭证 SHALL 继续使用宿主凭证机制。兼容环境来源 SHALL 包括 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的
`MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、
`MILKY_MAX_LOCAL_MEDIA_BYTES`、`MILKY_LONG_TEXT_FORWARD_THRESHOLD` 和
`MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS`，并保留当前固定的 25 个显式 Milky Action ToolSpec：
`send_profile_like`、`send_friend_nudge`、`send_group_nudge`、`recall_group_message`、
`get_group_info`、`get_group_member_list`、`get_group_member_info`、`set_group_member_mute`、
`set_group_whole_mute`、`get_forwarded_messages`、`get_private_file_download_url`、
`kick_group_member`、`quit_group`、`delete_friend`、`get_friend_requests`、
`accept_friend_request`、`reject_friend_request`、`get_group_file_download_url`、
`accept_group_request`、`reject_group_request`、`accept_group_invitation`、
`reject_group_invitation`、`get_group_files`、`get_friend_info` 和
`set_group_member_special_title`；manifest MUST NOT 声明任意未纳入显式 ToolSpec 的
Action 工具。另 SHALL 保留现有 sticker_send 与 sticker_search 的独立工具声明及各自可用性契约，本变更不新增通用 Action 或发送入口。

#### Scenario: 查看插件配置提示

- **WHEN** Hermes 展示插件的配置项
- **THEN** 它 SHALL 展示新配置契约、token 密码属性、可选的 Milky home channel 和本地出站
  资源大小上限
- **AND** SHALL 展示 `MILKY_MAX_LOCAL_MEDIA_BYTES` 的默认值为 `33554432` 字节（`32 MiB`）
- **AND** SHALL 展示 `MILKY_LONG_TEXT_FORWARD_THRESHOLD` 的默认值为 `0`
- **AND** SHALL 展示 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 的默认值为 `false`
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

适配器 MUST 按本规范的来源优先级在启动时解析配置。经过 Hermes core 允许的白名单管理指令 SHALL 按 hot-chat-allowlist 契约持久化并在线更新入站白名单；其他配置仍为启动快照。以下 MILKY_* 名称表示对应配置及其兼容环境输入，相同校验 SHALL 适用于最终选中的原生类型设置；必需连接地址可来自任一合法普通配置来源，凭证来自宿主凭证机制。 `MILKY_BASE_URL`、`MILKY_ACCESS_TOKEN` 和可选的
`MILKY_ALLOWED_CHATS`、`MILKY_WILL_POLICY`、`MILKY_SESSION_BUFFER_SIZE`、`MILKY_HOME_CHANNEL`、
`MILKY_MAX_LOCAL_MEDIA_BYTES`、`MILKY_LONG_TEXT_FORWARD_THRESHOLD` 和
`MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` SHALL 共同构成启动配置；`MILKY_MAX_LOCAL_MEDIA_BYTES` SHALL 是表示字节数的十进制整数，
取值范围 SHALL 为 `8 MiB` 至 `32 MiB`（含边界），所有来源均省略该项时 SHALL 使用 `33554432`；缺失必需值、
类型错误、范围错误或 home channel 目标格式错误 MUST 使启动失败。

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

- **WHEN** 按优先级选中的本地出站资源上限为空、类型或十进制格式错误、低于
`8 MiB` 或高于 `32 MiB`
- **THEN** 启动 SHALL 失败并指出安全的配置错误类别
- **AND** SHALL 不建立 Milky 网络连接或读取本地资源

#### Scenario: 多入口保持同一启动快照

- **WHEN** 当前实例已经完成配置解析，随后操作者保存新设置
- **THEN** 除已经通过白名单管理指令核验并发布的入站白名单外，该实例的普通 adapter、独立 sender 和 home-channel 元数据 SHALL 保持已解析快照
- **AND** 其他新设置及单独通过 Web 保存的白名单 SHALL 在新的启动或宿主明确重新加载该配置后才适用

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
空值、未配置或原生空列表 SHALL 表示阻止全部普通 friend/group 入站。全部放行 MUST 显式配置 `group:*` 与 `dm:*`。此语义 SHALL 同时适用于启动、重连恢复和管理指令更新，不新增模式字段。

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

本场景沿用既有标识以便规范迁移；原有放行结果由本 BREAKING 变更替换为阻止。

- **WHEN** `MILKY_ALLOWED_CHATS` 未配置或为空字符串
- **THEN** 配置 SHALL 产生空白名单
- **AND** 合法 friend/group 普通消息 SHALL 被白名单门禁拒绝；白名单管理命令按独立路由契约进入 core，由 core 判断命令权限

#### Scenario: 高优先级空列表不回退

- **WHEN** settings 显式保存空列表，低优先级环境仍有非空白名单
- **THEN** 有效白名单 SHALL 为空并阻止全部普通入站
- **AND** SHALL 不恢复环境授权或自动写入通配符

### Requirement: 普通配置遵循宿主插件来源回退顺序

普通配置 MUST 按当前 profile 的 plugins.entries.hermes-plugin-milky.settings、同一插件旧 config 子树、对应 MILKY_* 环境来源、内置默认值依次解析。宿主管理层覆盖、环境/凭证解析和 profile 隔离 SHALL 沿用 core；不得直接读取其他 profile 的进程环境作为补值。core 的插件设置读取只负责 settings 与旧 config 的回退，插件 SHALL 补充明确的旧环境兼容并执行统一校验，不假定 core 自动桥接。不存在的键才可回退，已配置但非法的值 MUST 报错；false、0、空列表或字段允许的空值不得被视为缺失。必需地址没有默认值。

本规范其他条款中的 MILKY_* 字段行为 SHALL 同样适用于按此顺序选中的对应设置；“省略/未配置时使用默认值”仅指所有合法来源均缺少该项，旧环境示例以没有更高优先级值为前提。

普通设置键与兼容来源 SHALL 对应如下：base_url、allowed_chats、will_policy、session_buffer_size、home_channel、max_local_media_bytes、long_text_forward_threshold、group_member_event_notifications 分别对应同名大写 MILKY_ 前缀变量。YAML 中白名单为字符串列表、Will 为对象、数值项为整数、成员通知为布尔值，地址和 home channel 为字符串；空 home channel 表示禁用。旧环境输入保留原文本格式。

Will SHALL 以 will_policy 整个设置键选择来源，选中对象省略的嵌套字段使用现有 Will 默认值，不与低优先级来源的另一个策略混合。人工编辑的未知字段、非法 null 和类型错误 SHALL 被拒绝。

#### Scenario: 设置覆盖旧环境

- **WHEN** settings 与同一 profile 的旧环境同时提供不同的合法值
- **THEN** 最终值 SHALL 来自 settings
- **AND** 没有设置的其他配置项 SHALL 继续独立回退

#### Scenario: 旧 config 兼容和纯环境部署

- **WHEN** 某键不存在于 settings
- **THEN** 系统 SHALL 先读取旧 config 的同名键，再读取该 profile 的对应环境值，最后才使用默认值
- **AND** 纯旧环境部署 SHALL 保持原有配置含义，无需先写入 YAML

#### Scenario: 禁用值与非法高优先级值

- **WHEN** settings 显式提供合法的 false、0、空白名单或空 home channel
- **THEN** 系统 SHALL 使用该值，不恢复低优先级的开启值
- **AND** 若 settings 值非法 SHALL 拒绝该候选配置，即使环境值合法也不得回退

#### Scenario: 嵌套策略不跨来源混合

- **WHEN** settings 提供部分 will_policy 对象且环境中保存另一套策略
- **THEN** 系统 SHALL 仅以 settings 对象和既有策略默认值构成最终策略
- **AND** SHALL 不继承环境策略中未在 settings 指定的增益或触发规则

#### Scenario: 不跨 profile 补值

- **WHEN** 目标 profile 缺少某个配置，而另一个 profile 或无关进程环境中有同名值
- **THEN** 系统 SHALL 按 core 当前作用域规则解析并保持缺失或采用本 profile 的默认值
- **AND** SHALL 不把其他 profile 的连接、白名单或凭证当作回退

### Requirement: Web 保存复用宿主设置与凭证持久化

Web MUST 将普通配置写入当前 profile 的插件 settings，并通过 core 凭证机制维护 MILKY_ACCESS_TOKEN；不得将 token 写入 settings、旧 config、任务记录或结果。读取 SHALL 只返回凭证存在状态。普通字段提交 SHALL 先对完整候选执行统一校验，未知键或任一非法字段使本次普通设置提交在写入前失败。普通设置和凭证 SHALL 使用独立保存动作，不承诺跨两种存储的原子提交；提交前 SHALL 检查所依据的配置版本；保存后 MUST 读取核验，拒绝写入、部分完成或核验失败不得报告全部保存成功。宿主只提供逐键写入而没有跨入口条件事务时 SHALL 明示该限制，不承诺检测检查与写入之间的所有外部竞争；核验发现变化时返回 conflict 或未确认状态并要求刷新。Web 不自动删除旧环境来源。初次配置时 SHALL 允许独立保存合法普通设置或凭证，同时保持启动完整性为未满足。

#### Scenario: 保存普通设置并显示来源

- **WHEN** 操作者提交合法的普通配置修改
- **THEN** 系统 SHALL 使用宿主插件设置持久化并核验，返回各变更字段的保存状态和当前有效来源
- **AND** SHALL 标明尚未确认运行实例应用，而不是仅凭保存成功宣称在线生效

#### Scenario: 托管设置和并发旧表单

- **WHEN** 字段由宿主管理而不可写，或提交前检查发现表单所依据的配置版本已变化
- **THEN** 系统 SHALL 拒绝对应保存并提供 blocked 或 conflict 等明确状态
- **AND** SHALL 不覆盖未提交的字段，不尝试绕过 core 的写入限制

#### Scenario: 凭证替换和清除

- **WHEN** 操作者明确提交新 token 或执行清除凭证动作
- **THEN** 系统 SHALL 通过宿主凭证机制执行并核验，不回显新旧 token
- **AND** 未填写新 token SHALL 保持原凭证；清除后 SHALL 如实显示缺少凭证和待重启状态

#### Scenario: 保存中途失败

- **WHEN** 多个普通设置持久化过程中只有部分字段成功
- **THEN** 系统 SHALL 返回已确认保存、失败及未确认的字段状态并要求刷新有效配置
- **AND** SHALL 不报告全部成功，也不通过盲目回滚覆盖并发更新

#### Scenario: 首次配置的分步保存

- **WHEN** 尚无 token 的用户先保存合法的普通设置
- **THEN** 系统 SHALL 接受普通设置并显示凭证缺失
- **AND** SHALL 继续拒绝 QQ 平台启动，直至完整配置合法
