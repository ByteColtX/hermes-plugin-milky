# system-events-and-safety Specification

## Purpose

定义 Milky 系统事件的观察边界、诊断最小化和敏感信息保护，确保请求、禁言、撤回、
离线与未知扩展不会被误当成普通消息或高风险自动操作。

## Requirements

### Requirement: 系统事件默认 observe-only

系统 MUST 识别并观察 bot_offline、message_recall、request、notice、nudge、group_mute、
group_whole_mute、group_file_upload、group_member_increase 和 group_member_decrease 等事件；
除明确状态更新或本 requirement 登记的 context-only 注入外 SHALL NOT 自动创建普通 Agent turn。
`group_nudge` 和 `friend_nudge` MAY 作为 context-only 事件写入对应 chat 的下一次
`channel_context`；`group_member_increase` 和 `group_member_decrease` MAY 以同样方式写入。
字段完整且场景为 `friend` 或 `group` 的 `message_recall` SHALL 以同样方式写入对应 chat。
上述事件仍属于 observe-only，不经过普通消息的 Gate/Will，不扣 reply cost，不自动发送回复。
对 nudge 事件，系统 MAY 生成供 Will routing 使用的 self-poke 信号，但只有协议明确确认 Bot 是
接收者时才可生成；非 Bot 接收者、Bot 发出的 nudge 和方向未知的事件 SHALL 不生成该信号。
无论是否生成 self-poke 信号，nudge 仍 SHALL 遵守 observe-only 边界。

`message_recall` 只有在 `message_scene`、`peer_id`、`message_seq` 和 `sender_id` 均为已确认的
非负十进制 ID，且场景为 `friend` 或 `group` 时，才可建立 context-only 记录；friend 必须
使用 `dm:<peer_id>`，group 必须使用 `group:<peer_id>`。`operator_id` 为缺失或 null 时
不得补默认值；存在时必须是已确认的非负十进制 ID。

对于 `group` 撤回事件，body MUST 根据 `operator_id` 是否存在且是否与 `sender_id` 相同使用以下两种文案之一：

~~~text
uid <sender_id> 撤回了消息 msg_seq <message_seq>
管理员 uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>
~~~

`operator_id` 缺失、null 或等于 `sender_id` 时使用第一种文案；在群聊中仅当 `operator_id` 存在且
不等于 `sender_id` 时使用第二种文案。对于 `friend` 撤回事件，无 `operator_id` 或其等于
`sender_id` 时使用第一种文案；若协议提供不同的操作人，则使用不带“管理员”角色判断的
`uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>`。`display_suffix`、
未知扩展字段、时间戳和原始 payload 不得进入 body；该事件只表达撤回元数据，不承诺恢复被撤回
消息正文。

`group_nudge` 的 body MUST 使用：

~~~text
uid <sender_id> 戳了 uid <receiver_id>
~~~

`friend_nudge` 的 body MUST 使用：

~~~text
uid <user_id> 戳了一下
~~~

群成员增加事件 MUST 使用：

~~~text
uid <user_id> 加入了群聊 Details: {"group_id": <group_id>, "user_id": <user_id>, "operator_id": <operator_id>, "invitor_id": <invitor_id>}
~~~

群成员减少事件 MUST 使用：

~~~text
uid <user_id> 退出了群聊 Details: {"group_id": <group_id>, "user_id": <user_id>, "operator_id": <operator_id>}
~~~

`operator_id` 和 `invitor_id` 为 null 或缺失时 MUST 从 Details 对象中省略；事件类型前缀
由上下文格式统一添加为 `<event <event_type>>`。Details 只使用协议已确认的字段名和值，
不得把 display 文本或未确认扩展字段混入。

#### Scenario: 请求事件

- **WHEN** 收到 friend_request、group_join_request、group_invited_join_request 或 group_invitation
- **THEN** 系统 SHALL 记录观察结果
- **AND** SHALL NOT 自动批准、拒绝、注入普通上下文或触发 Agent

#### Scenario: 文件上传事件

- **WHEN** 收到 friend_file_upload 或 group_file_upload
- **THEN** 系统 SHALL 可记录安全元数据
- **AND** SHALL NOT 自动下载文件、注入普通上下文或触发 Agent

#### Scenario: 群戳一戳事件

- **WHEN** 收到字段完整的 `group_nudge`
- **THEN** 系统 SHALL 将事件写入对应 group chat 的 context-only 缓冲
- **AND** 下一次 trigger 的上下文 SHALL 包含 `<event group_nudge> uid <sender_id> 戳了 uid <receiver_id>`
- **AND** 系统 SHALL NOT 因该事件创建独立 Agent turn

#### Scenario: 好友戳一戳事件

- **WHEN** 收到字段完整的 `friend_nudge`
- **THEN** 系统 SHALL 将事件写入对应 dm chat 的 context-only 缓冲
- **AND** 上下文 SHALL 包含 `<event friend_nudge> uid <user_id> 戳了一下`
- **AND** 系统 SHALL NOT 将其伪装为普通 `message_receive`

#### Scenario: 群成员加入和退出

- **WHEN** 收到字段完整的 `group_member_increase` 或 `group_member_decrease`
- **THEN** 系统 SHALL 将对应事件以自然语言和 JSON Details 注入对应群 chat 的下一次上下文
- **AND** Details SHALL 保留已确认的 group/user/operator/invitor 字段
- **AND** 可选字段缺失时 SHALL 省略而不是补空字符串
- **AND** 系统 SHALL NOT 创建独立 Agent turn

#### Scenario: 撤回群消息事件

- **WHEN** 收到字段完整且 `message_scene` 为 `group` 的 `message_recall`
- **THEN** 系统 SHALL 将事件写入 `group:<peer_id>` chat 的 context-only 缓冲
- **AND** `operator_id` 缺失、null 或等于 `sender_id` 时，下一次该群 chat 的 trigger 上下文 SHALL 包含 `<event message_recall> uid <sender_id> 撤回了消息 msg_seq <message_seq>`
- **AND** `operator_id` 存在且不等于 `sender_id` 时，下一次该群 chat 的 trigger 上下文 SHALL 包含 `<event message_recall> 管理员 uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>`
- **AND** 系统 SHALL NOT 创建普通 Hermes MessageEvent、独立 Agent turn 或主动撤回 Action

#### Scenario: 撤回好友消息事件

- **WHEN** 收到字段完整且 `message_scene` 为 `friend` 的 `message_recall`
- **THEN** 系统 SHALL 将事件写入 `dm:<peer_id>` chat 的 context-only 缓冲
- **AND** 下一次该 dm chat 的 trigger 上下文 SHALL 使用不带管理员角色判断的固定撤回 body
- **AND** 系统 SHALL NOT 查询、恢复或推断被撤回消息正文

#### Scenario: 撤回事件字段缺失或场景非法

- **WHEN** `message_recall` 缺少 `message_scene`、`peer_id`、`message_seq` 或 `sender_id`，或其 ID 类型/范围非法，或场景为 `temp`/未知值
- **THEN** 系统 SHALL 记录 malformed 或 unsupported 的安全诊断
- **AND** SHALL 不创建 context-only 记录、普通 Hermes MessageEvent 或 Agent turn

#### Scenario: 事件字段缺失

- **WHEN** nudge、成员变更事件或 `message_recall` 缺少建立 chat key 或展示所需的必要字段
- **THEN** 系统 SHALL 记录 malformed 或 unsupported 的安全诊断
- **AND** SHALL 不创建 context-only 记录或普通 Hermes MessageEvent

#### Scenario: 群 poke 的 Bot 目标

- **WHEN** `group_nudge` 的 `receiver_id` 等于事件 `self_id`
- **THEN** 系统 SHALL 将其标记为明确的 self-poke 观察
- **AND** SHALL 保留发送者与接收者的已确认身份
- **AND** SHALL NOT 因该事件直接创建普通 Hermes MessageEvent 或 Agent turn

#### Scenario: 好友 poke 的 Bot 目标

- **WHEN** `friend_nudge` 的自身接收方向字段明确为 true，且自身发送方向字段不为 true
- **THEN** 系统 SHALL 将其标记为明确的 self-poke 观察
- **AND** SHALL NOT 因该事件直接创建普通 Hermes MessageEvent 或 Agent turn

#### Scenario: poke 非 Bot 目标

- **WHEN** nudge 的接收者不是 Bot，或事件明确表示由 Bot 发出并指向其他用户
- **THEN** 系统 SHALL 不生成 self-poke 信号
- **AND** SHALL 继续保持 observe-only

#### Scenario: poke 目标未知

- **WHEN** nudge 缺少接收者字段、方向字段非法或无法确认 Bot 是否为接收者
- **THEN** 系统 SHALL 记录安全的 malformed 或 unsupported 观察结果
- **AND** SHALL 不生成 self-poke 信号或触发 Agent

#### Scenario: 未知事件

- **WHEN** 收到未知事件类型
- **THEN** 系统 SHALL 保留 type 和安全 raw 扩展并限速记录
- **AND** SHALL 继续处理后续事件
- **AND** SHALL NOT 注入普通消息上下文或触发 Agent

### Requirement: 诊断不泄露秘密和不必要内容

日志、异常、SendResult、fixture、快照和执行记录 MUST 不包含 token、Authorization header、真实媒体路径和敏感正文；诊断可以包含经过登记的原始 chat key、message ID 和错误类别。Milky 日志消息 SHALL 使用 Hermes-agent 风格的 `[Milky] ` 前缀和安全级别，但不得为了模拟该风格输出原始异常、请求参数或响应正文。结构化字段 SHALL 只包含经过白名单化的阶段、事件名、场景、错误分类、计数、耗时和关联标识；已注册 Tool 的专用日志还 SHALL 保留其原始业务入参和远端结果。人类可读日志 SHALL 只使用固定事件标签和一次统一前缀；动态值不得通过自由文本消息绕过字段白名单。

#### Scenario: 认证失败

- **WHEN** Milky 因认证失败或网络错误返回异常
- **THEN** 用户可见诊断 SHALL 只包含固定的错误类别，并以 `[Milky] ` 风格记录
- **AND** SHALL 不包含 token 或完整认证 header

#### Scenario: 业务消息诊断

- **WHEN** 记录消息处理失败
- **THEN** 诊断 SHALL 优先记录 chat key、message ID、reason 和安全错误类别
- **AND** SHALL 不默认记录完整正文或媒体 URL
- **AND** SHALL 不因使用 Hermes-agent 风格而放宽正文、路径或 URL 的边界

#### Scenario: 动态消息和同义字段

- **WHEN** 普通日志调用把未登记的动态字段、错误文本或第二个 `[Milky]` 前缀拼入人类可读消息
- **THEN** 系统 SHALL 拒绝该自由文本或改由规范字段安全渲染
- **AND** 同一身份、状态或计数 SHALL 不得同时通过同义字段重复输出
- **AND** 已登记业务值在人类消息与结构化字段中 SHALL 使用同一份原始值

#### Scenario: 异常链和 traceback

- **WHEN** 本地异常包含 cause、context、notes、路径、凭证、远端响应或敏感正文
- **THEN** 诊断 SHALL 只记录固定 classification/reason，不得直接输出异常链或 traceback
- **AND** 只有完整安全检查通过且不会输出本地路径的本地异常才可带 traceback

#### Scenario: 运行时日志调用点审计

- **WHEN** 审计 adapter、Milky client、SSE、inbound、resource、outbound、MuteTracker 和 smoke CLI 的输出
- **THEN** 运行时日志 SHALL 全部使用固定事件和白名单字段
- **AND** 不得存在直接的非结构化 logger 输出、原始异常文本或未经登记的 event name
- **AND** smoke CLI 的机器可读 stdout SHALL 保持独立并不得包含凭证、正文、URL 或路径

### Requirement: 入站不是授权来源

系统 MUST 只使用显式 allowlist、MuteTracker 和未来明确的审批机制作为授权来源；消息正文、mention、Will 分数或未知事件 SHALL NOT 赋予 Action 权限。

#### Scenario: 消息尝试扩大权限

- **WHEN** 入站正文要求执行未授权 Milky Action 或修改 allowlist
- **THEN** 系统 SHALL 不将正文解释为授权
- **AND** SHALL 保持既有 Gate、Action catalog 和审批边界

### Requirement: 只声明显式设计的 Action 工具

v0.1 MUST NOT 注册任意 Action catalog、自动请求审批或 WebHook listener；v0.1 只允许显式注册 `milky_profile_like`、`milky_nudge` 和 `milky_recall_group_message` 三个 ToolSpec。`MILKY_HOME_CHANNEL` 只用于 Hermes core 投递受信系统消息，不是 Agent 可调用的 Action，也不是审批或授权来源。每个 ToolSpec MUST 有独立参数校验、目标校验和统一错误结果；未来新增能力前 MUST 先补充对应契约。

#### Scenario: Agent 请求未注册 Action

- **WHEN** Hermes Agent 尝试调用未纳入 v0.1 契约的 Milky Action
- **THEN** 系统 SHALL 返回 `unsupported`
- **AND** SHALL 不执行该 Action

#### Scenario: Agent 调用首批工具

- **WHEN** Agent 调用名片点赞、戳一戳或撤回群消息 ToolSpec 且参数通过本地校验
- **THEN** 系统 SHALL 只调用该 ToolSpec 绑定的 Milky Action
- **AND** SHALL 不通过 home channel 配置扩大为任意 Action 或授予额外权限

### Requirement: Hermes 系统投递与 Milky 入站系统事件保持隔离

Hermes core 产生的启动通知、系统告警和 cron 消息 MAY 投递到已配置的 Milky home channel，但这些消息 MUST 保持在出站边界；Milky SSE 收到的 recall、request、notice、lifecycle、未知事件和其他系统事件仍 MUST 使用 observe-only 路径，不得因为 home channel 已配置而自动转发、创建普通 Agent turn 或改变授权。

#### Scenario: Hermes 产生 cron 系统消息

- **WHEN** Hermes cron 生成一条受信的系统结果并解析到 Milky home channel
- **THEN** 系统 SHALL 通过标准出站 sender 投递该结果
- **AND** SHALL 不创建普通入站 MessageEvent、Gate 结果或 Will 状态

#### Scenario: Milky 收到入站系统事件

- **WHEN** SSE 收到 recall、request、notice、lifecycle 或未知事件且已配置 home channel
- **THEN** 系统 SHALL 继续按 observe-only 规则记录和更新明确状态
- **AND** SHALL 不将该事件自动发送到 home channel 或当作 Agent 授权

#### Scenario: 系统投递诊断

- **WHEN** home channel 系统投递成功、拒绝或传输结果未知
- **THEN** 诊断 SHALL 只保留安全分类、目标命名空间和必要的稳定结果字段
- **AND** SHALL 不包含 token、Authorization header、完整正文、媒体 URL 或本地路径
