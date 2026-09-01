## MODIFIED Requirements

### Requirement: 系统事件默认 observe-only

系统 MUST 识别并观察 bot_offline、message_recall、request、notice、nudge、group_mute、
group_whole_mute 和 group_file_upload 等事件；除明确状态更新外 SHALL NOT 自动创建普通 Agent
turn。对 nudge 事件，系统 MAY 生成供 Will routing 使用的 self-poke 信号，但只有协议明确
确认 Bot 是接收者时才可生成；非 Bot 接收者、Bot 发出的 nudge 和方向未知的事件 SHALL 不
生成该信号。无论是否生成 self-poke 信号，nudge 仍 SHALL 遵守 observe-only 边界。

#### Scenario: 请求事件

- **WHEN** 收到 friend_request、group_join_request 或 group_invitation
- **THEN** 系统 SHALL 记录观察结果
- **AND** SHALL NOT 自动批准或拒绝请求

#### Scenario: 文件上传事件

- **WHEN** 收到 group_file_upload
- **THEN** 系统 SHALL 可记录安全元数据
- **AND** SHALL NOT 自动下载文件或触发 Agent

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
