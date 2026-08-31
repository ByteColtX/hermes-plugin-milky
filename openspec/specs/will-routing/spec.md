# will-routing Specification

## Purpose

定义基于消息属性的确定性 Will routing，让直接私聊、不同提及、引用、图片和普通
群消息按明确优先级选择 wait 或 trigger，同时将 nudge 等系统事件留在安全边界内。

## Requirements

### Requirement: routing 按场景和信号优先级决策

routing MUST 对 direct、mention、mentionAll、quote、poke 和 allMessage 分别接受 `wait`
或 `trigger`，并接受字符串数组 `keywords`；routing MUST NOT 接受 `image` 或
`mentionHere`。对每条普通 `message_receive`，系统 SHALL 同时评估所有适用规则，不得按
优先级短路；只要任一命中规则的动作是 `trigger`，Will SHALL 返回 `trigger`，否则 SHALL
返回 `wait`。`allMessage` SHALL 匹配每条普通 `message_receive`，不再表示仅普通群消息。

#### Scenario: 私聊优先于其他信号

- **WHEN** friend 消息包含文本或媒体，direct 为 `trigger`，且 allMessage 为 `wait`
- **THEN** Will SHALL 返回 trigger
- **AND** SHALL 不因 allMessage 的 `wait` 结果抵消 direct 的 `trigger`

#### Scenario: 群消息多信号并存

- **WHEN** 群消息同时直接提及 Bot 并引用消息，且 mention 为 `wait`、quote 为 `trigger`
- **THEN** Will SHALL 返回 `trigger`
- **AND** SHALL 继续合并所有已命中的规则，不使用固定优先级覆盖 quote

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

群消息的 self 和 all mention MUST 分别使用 `mention` 和 `mentionAll` 配置；routing
MUST NOT 再提供 `mentionHere` 配置，也不得通过正文、名称或普通 mention segment 推断
here mention。

#### Scenario: self mention 与全体提及使用独立动作

- **WHEN** 一条消息仅包含 self mention，另一条消息仅包含 `mention_all`，且 mention 为
  `trigger`、mentionAll 为 `wait`
- **THEN** 第一条消息 SHALL 命中 mention 并参与 routing 合并
- **AND** 第二条消息 SHALL 命中 mentionAll 并参与 routing 合并

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

nudge/poke 的 routing 配置 MAY 提供 poke 决策，但 v0.1 的 friend_nudge 和 group_nudge MUST 默认 observe-only，且 SHALL NOT 直接创建普通 Hermes MessageEvent 或 Agent turn。

#### Scenario: 观察 nudge

- **WHEN** 收到 friend_nudge 或 group_nudge
- **THEN** 系统 SHALL 可更新观察状态或 Will 所需信号
- **AND** SHALL 不将其伪装为普通 message_receive
