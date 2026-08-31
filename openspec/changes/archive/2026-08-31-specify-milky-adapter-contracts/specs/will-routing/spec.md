## Purpose

定义基于消息属性的确定性 Will routing，让直接私聊、不同提及、引用、图片和普通
群消息按明确优先级选择 wait 或 trigger，同时将 nudge 等系统事件留在安全边界内。

## ADDED Requirements

### Requirement: routing 按场景和信号优先级决策

routing MUST 对 direct、mention、mentionAll、mentionHere、quote、image、poke 和 group 分别接受 `wait` 或 `trigger`，并按 direct → mention → quote → image → group 的优先级选择消息动作。

#### Scenario: 私聊优先于其他信号

- **WHEN** friend 消息包含文本或媒体且 direct routing 配置为 trigger
- **THEN** Will SHALL 返回 trigger
- **AND** SHALL 不被 group 或其他群信号配置覆盖

#### Scenario: 群消息多信号并存

- **WHEN** 群消息同时直接提及 Bot、引用消息并包含图片
- **THEN** Will SHALL 使用 mention self 的动作
- **AND** SHALL 不继续使用 quote 或 image 动作

#### Scenario: 普通群消息

- **WHEN** 群消息没有 mention、reply 或 image 信号
- **THEN** Will SHALL 使用 group 动作

### Requirement: mention 类型映射保持独立

群消息的 self、all 和 here mention MUST 分别使用 `mention`、`mentionAll` 和 `mentionHere` 配置，不得因都属于提及而合并为同一个动作。

#### Scenario: 全体提及

- **WHEN** 消息只有 `mention_all` 且 `mentionAll` 配置为 wait
- **THEN** Will SHALL 返回 wait
- **AND** SHALL 不使用 self mention 的 trigger 配置

#### Scenario: here 提及

- **WHEN** 消息包含 here mention 且 `mentionHere` 配置为 trigger
- **THEN** Will SHALL 返回 trigger

### Requirement: nudge 不绕过系统事件边界

nudge/poke 的 routing 配置 MAY 提供 poke 决策，但 v0.1 的 friend_nudge 和 group_nudge MUST 默认 observe-only，且 SHALL NOT 直接创建普通 Hermes MessageEvent 或 Agent turn。

#### Scenario: 观察 nudge

- **WHEN** 收到 friend_nudge 或 group_nudge
- **THEN** 系统 SHALL 可更新观察状态或 Will 所需信号
- **AND** SHALL 不将其伪装为普通 message_receive
