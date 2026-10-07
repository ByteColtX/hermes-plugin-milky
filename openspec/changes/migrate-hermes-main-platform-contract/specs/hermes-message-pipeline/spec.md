# Spec Delta

## ADDED Requirements

### Requirement: MessageEvent 保留可确认的回复预期

普通消息和显式命令 MUST 向 Hermes 传递当前回复预期。仅在已确认协议身份足以判断时设置 true 或 false；无法确认是否指向 Bot 时 MUST 保持 unknown，不得从正文、Will 结果或昵称猜测。

#### Scenario: 私聊普通消息

- **WHEN** 一条身份有效的 friend 消息通过 Gate 和 Will
- **THEN** MessageEvent SHALL 表示预期 Bot 回复

#### Scenario: 群消息明确指向 Bot

- **WHEN** 群消息含有已确认的 Bot mention 或已确认回复目标是 Bot
- **THEN** MessageEvent SHALL 表示预期 Bot 回复

#### Scenario: 群消息确定未指向 Bot

- **WHEN** 协议解析完整且确认群消息既没有 Bot mention 也没有指向 Bot 的回复
- **THEN** MessageEvent SHALL 表示未预期 Bot 回复

#### Scenario: 回复目标无法确认

- **WHEN** mention、引用目标或消息片段无法可靠确定是否指向 Bot
- **THEN** MessageEvent SHALL 将回复预期保持为 unknown
- **AND** SHALL 不以缺失或 malformed 字段推断为确定的未指向 Bot

#### Scenario: 显式 Milky 命令

- **WHEN** 一条纯文本消息被识别为有效 Milky slash command 并交给 Hermes
- **THEN** MessageEvent SHALL 表示预期 Bot 回复

### Requirement: Gateway handoff 结果依据接收回执

普通 trigger MUST 只向 Hermes 提交一次。只有明确的正向 Gateway admission receipt 才能将 handoff 分类为 Gateway accepted；回执不得解释为 Agent turn 完成或 QQ 消息已送达。回执为 false 时 SHALL 分类为未接收；回执缺失、无法读取或无法识别时 MUST 分类为 unknown。任何未确认结果 MUST NOT 自动重提同一 trigger。

#### Scenario: Gateway 接收普通 trigger

- **WHEN** Hermes 明确确认已接收或排队一条 MessageEvent
- **THEN** handoff SHALL 分类为 Gateway accepted
- **AND** SHALL 不宣称 Agent turn 已完成或出站回复已送达

#### Scenario: Gateway 未接收 trigger

- **WHEN** handoff 正常返回但 Hermes 的接收回执未确认接收
- **THEN** 插件 SHALL 保留未接收或 unknown 结果，不记录 accepted
- **AND** SHALL 不再次提交同一 MessageEvent

#### Scenario: Gateway handler 抛出异常

- **WHEN** 提交 MessageEvent 时 Gateway handler 抛出异常
- **THEN** 插件 SHALL 分类记录 handoff 失败
- **AND** SHALL 不报告 Gateway accepted、turn 完成或 QQ 送达

#### Scenario: Gateway admission receipt 缺失或不可识别

- **WHEN** `handle_message()` 返回但事件没有可读取的明确正向 admission receipt，或 receipt 不是可识别的布尔值
- **THEN** 插件 SHALL 将 handoff 分类为 unknown
- **AND** SHALL 不记录 Gateway accepted、Agent 完成或 QQ 送达
- **AND** SHALL 不再次提交同一 MessageEvent
