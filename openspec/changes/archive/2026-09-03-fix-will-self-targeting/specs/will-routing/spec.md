## MODIFIED Requirements

### Requirement: routing 按场景和信号优先级决策

routing MUST 对 direct、mention、mentionAll、quote、poke 和 allMessage 分别接受 `wait`
或 `trigger`，并接受字符串数组 `keywords`；routing MUST NOT 接受 `image` 或
`mentionHere`。对每条普通 `message_receive`，系统 SHALL 同时评估所有适用规则，不得按
优先级短路；只要任一命中规则的动作是 `trigger`，Will SHALL 返回 `trigger`，否则 SHALL
返回 `wait`。`allMessage` SHALL 匹配每条普通 `message_receive`，不再表示仅普通群消息。
其中，`mention` 只有在消息明确提及当前 Bot 时才命中，`quote` 只有在遍历
`message.segments` 的 `reply` segment 时确认 `reply.data.sender_id == self_id` 才命中；
当前消息的 `message.sender_id` 只表示引用者，不参与判断。普通引用、他人提及和无法确认
`reply.data.sender_id` 的信号 SHALL 不命中这两个规则；`reply.data.segments` 中的 mention
不参与 quote 判断。
对于明确提供给 Will 的 poke/nudge 观察，`poke` 只有在协议确认 Bot 是接收者时才命中；
该观察仍受系统事件的 observe-only 边界约束。

#### Scenario: 私聊优先于其他信号

- **WHEN** friend 消息包含文本或媒体，direct 为 `trigger`，且 allMessage 为 `wait`
- **THEN** Will SHALL 返回 trigger
- **AND** SHALL 不因 allMessage 的 `wait` 结果抵消 direct 的 `trigger`

#### Scenario: 群消息多信号并存

- **WHEN** 群消息同时直接提及 Bot，并且某个 reply segment 的 `reply.data.sender_id == self_id`，且 mention 为 `wait`、quote 为 `trigger`
- **THEN** Will SHALL 返回 `trigger`
- **AND** SHALL 继续合并所有已命中的规则，不使用固定优先级覆盖 quote

#### Scenario: 引用他人消息不命中 quote

- **WHEN** 群消息的 reply segment 的 `reply.data.sender_id != self_id`，quote 为 `trigger`，且没有其他配置为 `trigger` 的命中规则
- **THEN** Will SHALL 不把该引用视为 quote 命中
- **AND** SHALL 按其余适用规则返回 `wait` 或 `trigger`

#### Scenario: reply.data.sender_id 缺失时不猜测目标

- **WHEN** 消息包含 reply segment，但 `reply.data.sender_id` 缺失、非法或无法确认
- **THEN** Will SHALL 不命中 quote
- **AND** SHALL 不从引用正文、显示名称或普通文本推断 Bot 目标

#### Scenario: 普通群消息

- **WHEN** 群消息未命中关键词，且 mention、mentionAll、quote 和 allMessage 的命中动作均为
  `wait`
- **THEN** Will SHALL 返回 `wait`

#### Scenario: 多个规则命中且至少一个触发

- **WHEN** friend 消息同时命中 direct 和 allMessage，且 direct 为 `wait`、allMessage 为
  `trigger`
- **THEN** Will SHALL 返回 `trigger`
- **AND** SHALL 不因 direct 的 `wait` 结果提前结束

#### Scenario: 所有命中规则都等待

- **WHEN** 消息命中的 direct、mention、mentionAll、quote、keywords 和 allMessage 动作均为
  `wait`
- **THEN** Will SHALL 返回 `wait`

#### Scenario: allMessage 触发所有普通消息

- **WHEN** 任意 friend 或 group `message_receive` 命中 allMessage，且 allMessage 配置为
  `trigger`
- **THEN** Will SHALL 返回 `trigger`
- **AND** 其他命中规则配置为 `wait` SHALL 不阻止该触发结果

### Requirement: mention 类型映射保持独立

群消息的 self 和 all mention MUST 分别使用 `mention` 和 `mentionAll` 配置；`mention` MUST
只匹配 `mention.user_id` 等于当前 Bot `self_id` 的直接提及，MUST NOT 将他人提及、
`mention_all` 或未知 mention 当作 self mention。routing MUST NOT 再提供 `mentionHere` 配置，
也不得通过正文、名称或普通 mention segment 推断 here mention。

#### Scenario: self mention 与全体提及使用独立动作

- **WHEN** 一条消息仅包含 self mention，另一条消息仅包含 `mention_all`，且 mention 为
  `trigger`、mentionAll 为 `wait`
- **THEN** 第一条消息 SHALL 命中 mention 并参与 routing 合并
- **AND** 第二条消息 SHALL 命中 mentionAll 并参与 routing 合并

#### Scenario: 提及其他用户不命中 mention

- **WHEN** 消息只提及其他用户，mention 为 `trigger`，且没有其他配置为 `trigger` 的命中规则
- **THEN** Will SHALL 不命中 mention
- **AND** SHALL 按 allMessage 和其他实际命中的规则返回结果

#### Scenario: 全体提及

- **WHEN** 消息只有 `mention_all` 且 `mentionAll` 配置为 wait
- **THEN** Will SHALL 返回 wait
- **AND** SHALL 不使用 self mention 的 trigger 配置

#### Scenario: here 提及

- **WHEN** 规范化输入带有未来扩展提供的 here mention 信号，但配置中不存在
  `routing.mentionHere`
- **THEN** Will SHALL 不为 here mention 选择独立 routing 动作
- **AND** SHALL 只依据其他命中规则（包括 allMessage）返回 `wait` 或 `trigger`

#### Scenario: here mention 配置被移除

- **WHEN** 启动配置包含 `routing.mentionHere`
- **THEN** 配置 SHALL 失败并报告不支持的 routing 字段
- **AND** SHALL 不将该字段静默映射为 mention 或 mentionAll

### Requirement: routing 关键词命中确定性触发

`routing.keywords` MUST 是字符串数组。规范化正文包含任意一个非空配置关键词时，Will
SHALL 将关键词规则视为 `trigger` 命中；关键词规则不使用随机抽样、willingness 分数或
force 配置。关键词匹配 SHALL 使用规范化正文的直接子串匹配，不按命中次数累加，也不将
未知 raw、媒体引用或敏感字段加入匹配文本。关键词数组为空时 SHALL 不产生关键词命中，
最终结果 SHALL 由其他命中规则（包括 allMessage）决定。

#### Scenario: 命中任意关键词

- **WHEN** `routing.keywords` 为 `["项目", "提醒"]`，消息规范化正文包含“提醒”，且
  allMessage 为 `wait`
- **THEN** Will SHALL 返回 `trigger`
- **AND** SHALL 不调用随机源或 willingness engine

#### Scenario: 关键词数组为空

- **WHEN** `routing.keywords` 为空数组，消息不命中其他配置为 `trigger` 的规则，且
  allMessage 为 `wait`
- **THEN** Will SHALL 返回 `wait`

#### Scenario: 关键词规则与等待规则同时命中

- **WHEN** 消息同时命中一个关键词和配置为 `wait` 的 direct、mention、mentionAll 或
  quote 规则
- **THEN** Will SHALL 返回 `trigger`
- **AND** SHALL 不因其他规则为 `wait` 而抵消关键词触发

#### Scenario: 图片仍可进入消息流水线但不再拥有 routing 分支

- **WHEN** 群消息包含 image segment，且没有 self/all mention、quote 或关键词命中
- **THEN** Will SHALL 只依据 allMessage 的配置返回 `wait` 或 `trigger`
- **AND** SHALL 不读取或要求 `routing.image`

### Requirement: nudge 不绕过系统事件边界

nudge/poke 的 routing 配置 MAY 提供 poke 决策，但 `poke` SHALL 只接受协议明确确认 Bot 为
接收者的 self-poke 信号。group nudge MUST 使用接收者与当前 Bot `self_id` 的一致性判断；
friend nudge MUST 使用协议的自身接收方向字段判断，并排除 Bot 自身发送的 nudge。接收者字段
缺失、非法或方向未知时 SHALL 不命中 poke。v0.1 的 friend_nudge 和 group_nudge MUST 继续
observe-only，且 SHALL NOT 直接创建普通 Hermes MessageEvent 或 Agent turn。

#### Scenario: self-poke 命中 poke routing

- **WHEN** Will 收到一个协议确认 Bot 为接收者的 group 或 friend poke 观察，且 poke 配置为
  `trigger`
- **THEN** 该观察 SHALL 命中 poke routing
- **AND** Will SHALL 返回 `trigger`
- **AND** 系统 SHALL 仍不因该事件创建普通 Hermes MessageEvent 或独立 Agent turn

#### Scenario: poke 他人不命中 poke routing

- **WHEN** Bot 戳了其他用户，或其他用户在群中戳了非 Bot 接收者，且 poke 配置为 `trigger`
- **THEN** 该观察 SHALL 不命中 poke routing
- **AND** 系统 SHALL 保持 observe-only

#### Scenario: poke 目标未知时安全等待

- **WHEN** poke/nudge 缺少接收者、方向字段非法或无法确认 Bot 是否为接收者
- **THEN** 该观察 SHALL 不命中 poke
- **AND** SHALL 不从 display 文本、动作图片 URL 或其他未知字段推断目标

#### Scenario: 观察 nudge

- **WHEN** 收到 friend_nudge 或 group_nudge
- **THEN** 系统 SHALL 可更新观察状态或 Will 所需信号
- **AND** SHALL 不将其伪装为普通 message_receive
