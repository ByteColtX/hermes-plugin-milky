## MODIFIED Requirements

### Requirement: 系统事件默认 observe-only

系统 MUST 识别并观察 bot_offline、message_recall、request、notice、nudge、group_mute、
group_whole_mute、group_file_upload、group_member_increase 和 group_member_decrease 等事件；
除明确状态更新或本 requirement 登记的 context-only/notification 注入外 SHALL NOT 自动创建普通 Agent turn。
`group_nudge` 和 `friend_nudge` MAY 作为 context-only 事件写入对应 chat 的下一次
`channel_context`；`group_member_increase` 和 `group_member_decrease` SHALL 以基础英文 body
写入对应群 chat 的 system context，且仅在 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 开启时在 body
末尾附加 `Tip` 并尝试立即通知 Agent。字段完整且场景为 `friend` 或 `group` 的
`message_recall` SHALL 以同样方式写入对应 chat。除成员通知明确触发的 Agent turn 外，上述事件
仍属于 observe-only，不经过普通消息的 Gate/Will，不扣 reply cost，不自动发送回复。
对 nudge 事件，系统 MAY 生成供 Will routing 使用的 self-poke 信号，但只有协议明确确认 Bot 是
接收者时才可生成；非 Bot 接收者、Bot 发出的 nudge 和方向未知的事件 SHALL 不生成该信号。
无论是否生成 self-poke 信号，nudge 仍 SHALL 遵守 observe-only 边界。

`message_recall` 只有在 `message_scene`、`peer_id`、`message_seq` 和 `sender_id` 均为已确认的
非负十进制 ID，且场景为 `friend` 或 `group` 时，才可建立 context-only 记录；friend 必须
使用 `dm:<peer_id>`，group 必须使用 `group:<peer_id>`。`operator_id` 为缺失或 null 时
不得补默认值；存在时必须是已确认的非负十进制 ID。

对于 `group` 撤回事件，body MUST 根据 `operator_id` 是否存在且是否与 `sender_id` 相同使用以下两种英文文案之一：

~~~text
uid <sender_id> recalled message msg_seq <message_seq>
Admin uid <operator_id> recalled uid <sender_id>'s message msg_seq <message_seq>
~~~

`operator_id` 缺失、null 或等于 `sender_id` 时使用第一种文案；在群聊中仅当 `operator_id` 存在且
不等于 `sender_id` 时使用第二种文案。对于 `friend` 撤回事件，无 `operator_id` 或其等于
`sender_id` 时使用第一种文案；若协议提供不同的操作人，则使用不带“管理员”角色判断的
`uid <operator_id> recalled uid <sender_id>'s message msg_seq <message_seq>`。`display_suffix`、
未知扩展字段、时间戳和原始 payload 不得进入 body；该事件只表达撤回元数据，不承诺恢复被撤回
消息正文。

`group_nudge` 的 body MUST 使用：

~~~text
uid <sender_id> poked uid <receiver_id>
~~~

`friend_nudge` 的 body MUST 使用：

~~~text
uid <user_id> poked once
~~~

群成员增加事件的基础 body MUST 使用以下英文文案；`MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 关闭时使用该基础 body：

~~~text
uid <user_id> joined the group. Details: {"group_id": <group_id>, "user_id": <user_id>, "operator_id": <operator_id>, "invitor_id": <invitor_id>}
~~~

通知启用时，群成员增加事件 MUST 在基础 body 末尾追加以下固定 Tip：

~~~text
 Tip: If relevant to the current turn, naturally acknowledge or welcome this new member using the current group context. Do not invent their nickname, background, or other unconfirmed facts.
~~~

群成员减少事件的基础 body MUST 使用以下英文文案；`MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 关闭时使用该基础 body：

~~~text
uid <user_id> left the group. Details: {"group_id": <group_id>, "user_id": <user_id>, "operator_id": <operator_id>}
~~~

通知启用时，群成员减少事件 MUST 在基础 body 末尾追加以下固定 Tip：

~~~text
 Tip: If relevant to the current turn, naturally acknowledge the departure or offer a brief farewell based only on confirmed shared context. Do not speculate about the reason or invent memories.
~~~

`operator_id` 和 `invitor_id` 为 null 或缺失时 MUST 从 Details 对象中省略；事件类型前缀
由上下文格式统一添加为 `<event <event_type>>`。Details 只使用协议已确认的字段名和值，
不得把 display 文本或未确认扩展字段混入。`Tip` 是插件固定文案，不来自 Milky payload，
只在通知启用的 body 中出现；它 MUST 保留“仅在当前 turn 相关时自然回应”的限制，
不得要求 Agent 对每个成员事件强制回复。

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
- **AND** 下一次 trigger 的上下文 SHALL 包含 `<event group_nudge> uid <sender_id> poked uid <receiver_id>`
- **AND** 系统 SHALL NOT 因该事件创建独立 Agent turn

#### Scenario: 好友戳一戳事件

- **WHEN** 收到字段完整的 `friend_nudge`
- **THEN** 系统 SHALL 将事件写入对应 dm chat 的 context-only 缓冲
- **AND** 上下文 SHALL 包含 `<event friend_nudge> uid <user_id> poked once`
- **AND** 系统 SHALL NOT 将其伪装为普通 `message_receive`

#### Scenario: 群成员加入和退出

- **WHEN** 收到字段完整的 `group_member_increase` 或 `group_member_decrease`
- **THEN** 系统 SHALL 将对应事件以本 requirement 规定的基础英文 body 写入对应群 chat 的 system context
- **AND** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 开启时，body SHALL 在末尾带对应固定 `Tip:`；若 Hermes 接受注入，系统 SHALL 立即消费该群待处理的 system context 触发一个 Agent turn
- **AND** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 关闭时，body SHALL 不带 `Tip:`，且事件 SHALL 保留到下一次普通消息触发时消费
- **AND** Details SHALL 保留已确认的 group/user/operator/invitor 字段
- **AND** 可选字段缺失时 SHALL 省略而不是补空字符串
- **AND** 成员通知以外的普通系统事件 SHALL NOT 因该事件创建独立 Agent turn

#### Scenario: 撤回群消息事件

- **WHEN** 收到字段完整且 `message_scene` 为 `group` 的 `message_recall`
- **THEN** 系统 SHALL 将事件写入 `group:<peer_id>` chat 的 context-only 缓冲
- **AND** `operator_id` 缺失、null 或等于 `sender_id` 时，下一次该群 chat 的 trigger 上下文 SHALL 包含 `<event message_recall> uid <sender_id> recalled message msg_seq <message_seq>`
- **AND** `operator_id` 存在且不等于 `sender_id` 时，下一次该群 chat 的 trigger 上下文 SHALL 包含 `<event message_recall> Admin uid <operator_id> recalled uid <sender_id>'s message msg_seq <message_seq>`
- **AND** 系统 SHALL NOT 创建普通 Hermes MessageEvent、独立 Agent turn 或主动撤回 Action

#### Scenario: 撤回好友消息事件

- **WHEN** 收到字段完整且 `message_scene` 为 `friend` 的 `message_recall`
- **THEN** 系统 SHALL 将事件写入 `dm:<peer_id>` chat 的 context-only 缓冲
- **AND** 下一次该 dm chat 的 trigger 上下文 SHALL 使用不带管理员角色判断的固定英文撤回 body
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

## ADDED Requirements

### Requirement: 成员事件通知配置开关

系统 MUST 在启动时读取 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS`，将大小写不敏感的 `true` 和 `false`
解析为布尔值；未设置时 MUST 使用 `false`，以保持默认不产生即时成员通知的低副作用行为。
配置解析完成后该值在本次插件生命周期内 MUST 保持不变，不提供运行中热切换。除 `true`、`false`
或未设置以外的值 MUST 被视为配置错误并阻止插件启动，不得静默猜测默认值。

当该值为 `false` 时，系统 MUST 继续观察字段完整的成员增加/减少事件，并将不带 `Tip` 的基础
英文 body 写入 system context；系统 SHALL 不因该成员事件立即创建 Agent turn，事件继续等待
下一次普通消息触发时消费。该开关 MUST NOT 改变 nudge、message_recall、请求、文件上传或
其他系统事件的既有 observe-only/context-only 行为。

当该值为 `true` 时，系统 MUST 在成员事件 body 末尾附加固定 `Tip`，并在 Hermes 已确认或持久化
恢复的对应会话 session key 且 `inject_message` 被宿主接受时，立即按 ingress 顺序消费该群待处理的
system context，并触发一个 Agent turn。该即时通知 SHALL 使用 Hermes 已有会话注入接口，
不经过普通 `message_receive` 的 Gate/Will，不扣 reply cost，不直接调用 Milky Action。
注入失败、权限未授予、宿主不可用或 session key 未确认或未恢复时，系统 MUST 保留带 `Tip` 的 system
context，不得丢弃事件；系统 SHALL 记录安全的 unsupported/failed 诊断，并等待下一次普通消息
触发消费。

#### Scenario: 未配置时保持成员事件通知

- **WHEN** 启动环境未设置 `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS`，随后收到字段完整的成员增加或减少事件
- **THEN** 系统 SHALL 使用不带 `Tip` 的英文基础 body 将事件写入对应群 chat 的 system context
- **AND** 系统 SHALL NOT 因该事件立即创建 Agent turn，而是在下一次普通消息触发时消费该事件

#### Scenario: 显式启用成员事件通知

- **WHEN** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 的值为 `true`（大小写不敏感），随后收到字段完整的成员增加或减少事件
- **THEN** 系统 SHALL 使用带固定 `Tip` 的完整英文 body、JSON Details 和可选字段省略规则
- **AND** 在 Hermes 接受注入且 session key 已确认时，系统 SHALL 立即按 ingress 顺序消费该群 system context 并触发一个 Agent turn
- **AND** 该 turn SHALL 不经过普通消息 Gate/Will，且 SHALL 不扣 reply cost

#### Scenario: 显式关闭成员事件通知

- **WHEN** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 的值为 `false`（大小写不敏感），随后收到字段完整的成员增加或减少事件
- **THEN** 系统 SHALL 记录观察结果并将不带 `Tip` 的英文基础 body 放入对应群 chat 的 system context
- **AND** 系统 SHALL 不立即消费该 system context，不创建 Agent turn、修改 Gate/Will 状态或扣 reply cost

#### Scenario: 即时注入不可用

- **WHEN** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 为 `true`，但对应 Hermes session key 未确认/未恢复、注入权限未授予、宿主没有 live gateway 或 `inject_message` 返回拒绝
- **THEN** 系统 SHALL 将带固定 `Tip` 的成员事件保留在对应群 chat 的 system context
- **AND** 系统 SHALL 记录安全的 unsupported/failed 诊断
- **AND** 后续普通消息 SHALL 仍可消费该事件，系统 SHALL 不因注入失败丢弃或重复创建即时 turn

#### Scenario: 成员事件通知配置非法

- **WHEN** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 被设置为除 `true`/`false`（大小写不敏感）以外的值
- **THEN** 系统 SHALL 将其报告为启动配置错误
- **AND** SHALL 不以 `true`、`false` 或其他默认值继续运行

#### Scenario: 关闭开关不影响其他系统事件

- **WHEN** `MILKY_GROUP_MEMBER_EVENT_NOTIFICATIONS` 为 `false`，随后收到合法的 `group_nudge`、`friend_nudge` 或 `message_recall`
- **THEN** 系统 SHALL 继续按对应英文 body 和既有 context-only 规则处理这些事件
- **AND** SHALL 不把成员事件开关解释为全局系统事件开关
