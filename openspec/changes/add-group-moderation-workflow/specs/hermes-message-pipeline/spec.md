# Spec Delta

## MODIFIED Requirements

### Requirement: pipeline 顺序不可越过门禁和去重

本文顺序约束普通聊天路径。对显式启用的群管，系统 MUST 在 canonical/dedup 与同群有序接纳之后、聊天缓冲消费之前独立执行资格检查、本地筛查和证据截取；审核资格遵守 group-moderation，不受聊天 mute gate 或 Will wait 阻断。群管网络审核 SHALL 不占用聊天接纳等待，不修改 Will、reply cost 或会话 snapshot，不进入普通 Agent turn。

普通消息 MUST 按 message_receive → tolerant parse/normalize → canonical/dedup → per-chat admission → Gate → wait buffer → Will → drain → detached trigger 的分类引用查询与 Hermes attachment materialization → mapper → 会话 metadata snapshot 登记 → Hermes `handle_message()` 的顺序处理。resolver 必须在 mapper 前 await 所有实际使用的异步资源 helper；snapshot 登记 MUST 只使用 canonical 已校验的最小 friend/group 字段，且失败不得改变既有 handoff、正文、附件或 reply cost 语义。插件 MUST NOT 为同 chat 的 Agent turn 建立 ordered handoff 或其他执行队列，也 MUST NOT 等待 Agent turn 执行；`handle_message()` 提交正常返回后 detached 处理即可结束。Agent 忙碌时的 `queue`、`steer`、`interrupt`、follow-up 和 pending/FIFO 行为 MUST 由 Hermes Gateway 根据 `busy_input_mode` 处理。

#### Scenario: 重复消息

- **WHEN** 相同 canonical message ID 再次到达
- **THEN** pipeline SHALL 在资源、Will 和 Hermes 之前停止
- **AND** Hermes turn 次数 SHALL 不增加
- **AND** 会话 metadata snapshot SHALL 不更新

#### Scenario: Gate 拒绝

- **WHEN** Self、allowlist 或 mute gate 拒绝消息
- **THEN** 消息 SHALL 不进入 wait buffer、Will、资源补全或 Hermes
- **AND** SHALL 不登记会话 metadata snapshot

#### Scenario: Hermes 忙碌策略接管后续消息

- **WHEN** 一个 trigger 已调用 Hermes `handle_message()` 且 Agent 尚未完成，后续消息通过插件 admission
- **THEN** 插件 SHALL 不等待前一个 Agent turn 或创建插件侧 Agent 执行队列
- **AND** 后续 MessageEvent SHALL 交给 Hermes Gateway 按 `busy_input_mode` 的 queue、steer 或 interrupt 语义处理

#### Scenario: 资源 materialization 与 Agent turn 解耦

- **WHEN** trigger 的 `media_resource_references` 需要异步 Hermes URL helper
- **THEN** mapper SHALL 只在 helper 返回本地路径后构造 MessageEvent，并将该路径放入 Hermes media 字段
- **AND** `handle_message()` 返回后插件 SHALL 结束本次提交等待，不得继续等待 Agent turn 完成

#### Scenario: trigger handoff 前完成快照登记

- **WHEN** 合法 friend 或 group 消息完成资源解析和 mapper
- **THEN** 插件 SHALL 在 `handle_message()` 前登记 `dm:<id>` 或 `group:<id>` 对应的安全 snapshot
- **AND** snapshot 不得改变 MessageEvent 的正文、历史上下文、媒体或 source 字段

#### Scenario: wait 历史不提前建立会话介绍

- **WHEN** 消息通过 Gate 但 Will 返回 `wait`
- **THEN** 消息 SHALL 在普通聊天路径只进入既有 wait buffer；符合群管资格时仍须独立筛查
- **AND** SHALL 不登记会话 metadata snapshot

#### Scenario: 独立审核不被聊天抑制

- **WHEN** 合资格群消息命中本地规则，聊天因 mute 或 Will wait 没有产生回复
- **THEN** 系统 SHALL 独立提交审核，普通路径仍遵守原有门禁和缓冲规则
- **AND** 重复 canonical 消息 SHALL 同时停止两条路径，不重复创建案件
