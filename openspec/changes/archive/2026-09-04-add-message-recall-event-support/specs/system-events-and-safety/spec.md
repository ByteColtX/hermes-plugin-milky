## MODIFIED Requirements

### Requirement: 系统事件默认 observe-only

系统 MUST 识别并观察 bot_offline、message_recall、request、notice、nudge、group_mute、
group_whole_mute、group_file_upload、group_member_increase 和 group_member_decrease 等事件；
除明确状态更新或本 requirement 登记的 context-only 注入外 SHALL NOT 自动创建普通 Agent turn。
`group_nudge`、`friend_nudge`、`group_member_increase` 和 `group_member_decrease` MAY 作为
context-only 事件写入对应 chat 的下一次 `channel_context`；字段完整且场景为 `friend` 或
`group` 的 `message_recall` SHALL 以同样方式写入对应 chat。上述事件仍属于 observe-only，
不经过普通消息的 Gate/Will，不扣 reply cost，不自动发送回复。对 nudge 事件，系统 MAY 生成
供 Will routing 使用的 self-poke 信号，但只有协议明确确认 Bot 是接收者时才可生成；非 Bot
接收者、Bot 发出的 nudge 和方向未知的事件 SHALL 不生成该信号。无论是否生成 self-poke
信号，nudge 仍 SHALL 遵守 observe-only 边界。

`message_recall` 只有在 `message_scene`、`peer_id`、`message_seq` 和 `sender_id` 均为已确认的
非负十进制 ID，且场景为 `friend` 或 `group` 时，才可建立 context-only 记录；friend 必须
使用 `dm:<peer_id>`，group 必须使用 `group:<peer_id>`。`operator_id` 为缺失或 null 时
不得补默认值；存在时必须是已确认的非负十进制 ID。

对于 `group` 撤回事件，body MUST 根据 `operator_id` 是否存在使用以下两种文案之一：

~~~text
uid <sender_id> 撤回了消息 msg_seq <message_seq>
管理员 uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>
~~~

`operator_id` 缺失或 null 时使用第一种文案；存在时使用第二种文案。对于 `friend` 撤回事件，
无 `operator_id` 时使用第一种文案；若协议提供操作人，则使用不带“管理员”角色判断的
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
- **AND** `operator_id` 缺失或 null 时，下一次该群 chat 的 trigger 上下文 SHALL 包含 `<event message_recall> uid <sender_id> 撤回了消息 msg_seq <message_seq>`
- **AND** `operator_id` 存在时，下一次该群 chat 的 trigger 上下文 SHALL 包含 `<event message_recall> 管理员 uid <operator_id> 撤回了 uid <sender_id> 的消息 msg_seq <message_seq>`
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
