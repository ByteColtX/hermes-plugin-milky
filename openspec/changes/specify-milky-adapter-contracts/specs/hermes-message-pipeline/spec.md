## Purpose

把已通过身份、去重、Gate 和 Will 的 friend/group 消息交接为 Hermes 可消费的一次
MessageEvent，同时严格区分历史上下文、当前正文、系统观察和 trigger 提交后的策略反馈。

## ADDED Requirements

### Requirement: friend 和 group 映射到明确 MessageEvent

正常 friend 消息 MUST 映射为 private message，正常 group 消息 MUST 映射为 group message，并保留 sender ID/name、Milky message ID 字符串、`source=milky`、正文、raw、timestamp、reply、媒体结果、channel_context 和安全 metadata。

#### Scenario: friend 消息交接

- **WHEN** 合法 friend 消息通过 Gate 并被 Will trigger
- **THEN** Hermes SHALL 收到 private MessageEvent
- **AND** event 的 source SHALL 为 `milky`
- **AND** message ID SHALL 使用 Milky ID 字符串

#### Scenario: group 消息交接

- **WHEN** 合法 group 消息通过 Gate 并被 Will trigger
- **THEN** Hermes SHALL 收到 group MessageEvent
- **AND** event SHALL 保留 group chat key、发送者身份和 mention/quote metadata

### Requirement: pipeline 顺序不可越过门禁和去重

普通消息 MUST 按 message_receive → tolerant parse/normalize → canonical/dedup → per-chat admission → Gate → wait buffer → Will → drain → per-chat ordered handoff（资源补全与 mapper）→ Hermes `handle_message()` 的顺序处理。ordered handoff MUST 按 ingress sequence 提交同 chat 的 trigger，且 MUST NOT 等待 Agent turn 执行；提交正常返回后立即释放。Agent 忙碌、follow-up、interrupt 和 Hermes 单槽 pending 行为 MUST 由 Hermes Gateway 处理。

#### Scenario: 重复消息

- **WHEN** 相同 canonical message ID 再次到达
- **THEN** pipeline SHALL 在资源、Will 和 Hermes 之前停止
- **AND** Hermes turn 次数 SHALL 不增加

#### Scenario: Gate 拒绝

- **WHEN** Self、allowlist 或 mute gate 拒绝消息
- **THEN** 消息 SHALL 不进入 wait buffer、Will、资源补全或 Hermes

### Requirement: 历史上下文和当前正文不得重复

trigger 的当前消息 MUST 只作为本次正文；已经 drain 的历史 wait 消息 MUST 只进入一次性 channel_context；wait 消息 MUST NOT 写入 Hermes transcript。

#### Scenario: 三条消息触发

- **WHEN** 两条历史 wait 消息后收到一条 trigger 消息
- **THEN** Hermes SHALL 收到一次 turn
- **AND** 当前消息 SHALL 不出现在 channel_context
- **AND** 历史两条消息 SHALL 不再次作为正文交给同一次 turn

### Requirement: Agent-facing 文本区分历史上下文和当前消息

当存在 detached 历史时，适配器 MUST 将历史紧凑记录只放入 `MessageEvent.channel_context`，
并将当前 trigger 消息以同一紧凑 header 格式放入 `MessageEvent.text`。适配器 MUST NOT
把 `[New message]` 标记或当前消息复制到 `channel_context`；Hermes 已有的 Agent 输入组装
语义负责在历史块和当前消息之间加入该标记。没有历史时，适配器 MUST 保持
`channel_context=None`，并只交付当前消息正文。

#### Scenario: Agent 收到历史和当前消息

- **WHEN** 两条历史消息后收到一条当前 trigger 消息
- **THEN** `channel_context` SHALL 仅为历史记录块，例如：
  ~~~text
  [Alice uid 101 msg_id 7]
  第一条
  [Bob uid 202 msg_id 8]
  第二条
  ~~~
- **AND** `text` SHALL 仅为当前消息记录，例如：
  ~~~text
  [Carol uid 303 msg_id 9]
  触发
  ~~~
- **AND** Hermes 的有效 Agent 输入 SHALL 在历史块后以空行和 `[New message]` 分隔当前消息
- **AND** 当前消息 SHALL 不出现在 `channel_context`

#### Scenario: 没有历史时交付当前消息

- **WHEN** trigger 发生时 detached batch 为空
- **THEN** `channel_context` SHALL 为 `None`
- **AND** `text` SHALL 仍使用当前消息的紧凑 header 和规范化正文
- **AND** 适配器 SHALL 不伪造历史标题或空的上下文 block

### Requirement: trigger 提交后反馈 Will

只有 Hermes `handle_message()` 正常返回、表明 trigger 已提交后，系统 SHALL 通知 Will 执行一次 reply cost；mapping 失败、提交异常、Gate deny 或 wait SHALL NOT 扣费。v0.1 不等待 Agent 最终 turn 完成。

#### Scenario: Hermes 接受提交

- **WHEN** `handle_message()` 正常返回
- **THEN** Will SHALL 执行一次成功回复反馈

#### Scenario: Hermes 提交失败

- **WHEN** mapper 或 `handle_message()` 抛出异常
- **THEN** 系统 SHALL 保留未扣费状态
- **AND** SHALL 不把该次 trigger 伪装成已提交

### Requirement: temp 和系统事件不进入普通 mapper

temp 消息 MUST 在协议解析边界被忽略并记录 `ignored_temp`，系统事件和未知事件 MUST 使用 observe 路径；它们 SHALL NOT 通过 private/group mapper 触发普通 Agent turn。

#### Scenario: temp 消息

- **WHEN** 收到合法 temp `message_receive`
- **THEN** 系统 SHALL 记录 `ignored_temp`
- **AND** SHALL 不创建 canonical、普通 Hermes MessageEvent 或出站目标
