## MODIFIED Requirements

### Requirement: pipeline 顺序不可越过门禁和去重

普通消息 MUST 按 message_receive → tolerant parse/normalize → canonical/dedup → per-chat admission → Gate → wait buffer → Will → drain → detached trigger 的分类引用查询与 Hermes attachment materialization → mapper → 会话 metadata 快照登记 → Hermes `handle_message()` 的顺序处理。resolver 必须在 mapper 前 await 所有实际使用的异步资源 helper；会话 metadata 快照登记 MUST 只使用已通过 canonical 校验的最小场景字段，并 MUST 发生在 `handle_message()` 前。插件 MUST NOT 为同 chat 的 Agent turn 建立 ordered handoff 或其他执行队列，也 MUST NOT 等待 Agent turn 执行；`handle_message()` 提交正常返回后 detached 处理即可结束。Agent 忙碌时的 `queue`、`steer`、`interrupt`、follow-up 和 pending/FIFO 行为 MUST 由 Hermes Gateway 根据 `busy_input_mode` 处理。

#### Scenario: 重复消息

- **WHEN** 相同 canonical message ID 再次到达
- **THEN** pipeline SHALL 在资源、Will、会话 metadata 快照和 Hermes 之前停止
- **AND** Hermes turn 次数 SHALL 不增加

#### Scenario: Gate 拒绝

- **WHEN** Self、allowlist 或 mute gate 拒绝消息
- **THEN** 消息 SHALL 不进入 wait buffer、Will、资源补全、会话 metadata 快照或 Hermes

#### Scenario: Hermes 忙碌策略接管后续消息

- **WHEN** 一个 trigger 已调用 Hermes `handle_message()` 且 Agent 尚未完成，后续消息通过插件 admission
- **THEN** 插件 SHALL 不等待前一个 Agent turn 或创建插件侧 Agent 执行队列
- **AND** 后续 MessageEvent SHALL 交给 Hermes Gateway 按 `busy_input_mode` 的 queue、steer 或 interrupt 语义处理

#### Scenario: 资源 materialization 与 Agent turn 解耦

- **WHEN** trigger 的 `media_resource_references` 需要异步 Hermes URL helper
- **THEN** mapper SHALL 只在 helper 返回本地路径后构造 MessageEvent，并将该路径放入 Hermes media 字段
- **AND** 会话 metadata 快照 SHALL 在 mapper 完成后、`handle_message()` 前登记
- **AND** `handle_message()` 返回后插件 SHALL 结束本次提交等待，不得继续等待 Agent turn 完成

#### Scenario: wait 历史不提前建立会话介绍

- **WHEN** 消息通过 Gate 但 Will 返回 `wait`
- **THEN** 消息 SHALL 只进入既有 wait buffer
- **AND** SHALL 不登记会话 metadata 快照、不调用 Hermes `handle_message()` 或创建 system prompt

#### Scenario: trigger handoff 前完成快照登记

- **WHEN** 一条合法 friend 或 group 消息完成 trigger 决策、资源解析和 mapper
- **THEN** pipeline SHALL 在 Hermes `handle_message()` 前登记与 `dm:<id>` 或 `group:<id>` 对应的最小会话 metadata
- **AND** 登记失败 SHALL 不改变既有 Hermes handoff 的目标、正文、附件或 reply cost 语义

### Requirement: friend 和 group 映射到明确 MessageEvent

正常 friend 消息 MUST 映射为 private message，正常 group 消息 MUST 映射为 group message，并保留 sender ID/name、Milky message ID 字符串、`source=milky`、正文、raw、timestamp、reply、已 materialize 的附件路径/MIME、channel_context 和安全 metadata。对于同一次 trigger，`MessageEvent.media_urls`/`media_types` MUST 将 `channel_context` 中历史消息的已 materialize 直接图片与当前 trigger 消息和可见 reply 内容的已 materialize 图片按规定顺序合并；相同图片 bytes 只保留当前 batch 中首次出现的代表，hash 不可用时仅按本地路径去重。历史图片按上下文顺序在前，当前图片按当前消息顺序在后，并同步维护两字段一一对应。原始 `media_resource_references` 与 `file_attachment_references` 不得直接写入 `MessageEvent.media_urls`。会话介绍 metadata SHALL 通过独立的会话快照边界提供，不得塞入 `MessageEvent.text`、`channel_context`、媒体字段或未声明的 source 正文。

#### Scenario: friend 消息交接

- **WHEN** 合法 friend 消息通过 Gate 并被 Will trigger
- **THEN** Hermes SHALL 收到 private MessageEvent
- **AND** event 的 source SHALL 为 `milky`
- **AND** message ID SHALL 使用 Milky ID 字符串

#### Scenario: group 消息交接

- **WHEN** 合法 group 消息通过 Gate 并被 Will trigger
- **THEN** Hermes SHALL 收到 group MessageEvent
- **AND** event SHALL 保留 group chat key、发送者身份和 mention/quote metadata

#### Scenario: 历史图片和当前图片按顺序交给 Hermes

- **WHEN** 一个 trigger batch 包含按上下文顺序排列的两张历史图片，以及当前消息中按 segment 顺序排列的两张图片
- **THEN** `MessageEvent.media_urls` SHALL 先包含历史图片代表，再包含当前图片代表
- **AND** `MessageEvent.media_types` SHALL 与 `media_urls` 按相同顺序逐项对应
- **AND** 当前消息 SHALL 仍只作为正文，历史消息 SHALL 仍只作为 `channel_context`

#### Scenario: 历史和当前图片路径重复

- **WHEN** 历史图片与当前图片的 materialized 本地路径不同但文件内容相同
- **THEN** `MessageEvent.media_urls` SHALL 只保留历史 occurrence 的首次代表路径
- **AND** 当前正文中对应的 image placeholder SHALL 使用历史代表 basename
- **AND** `MessageEvent.media_types` SHALL 保留历史代表首次出现时的 MIME 且不产生孤立项

#### Scenario: hash 不可用时不推断图片相同

- **WHEN** 两个不同本地路径的 image materialization 无法安全计算 hash
- **THEN** 两个路径 SHALL 不因 resource_id、URL、summary 或文件名相似而合并
- **AND** 系统 SHALL 仅执行既有的 exact path 去重

#### Scenario: 历史图片未 materialize

- **WHEN** 历史图片未通过 Hermes helper 生成有效本地路径
- **THEN** 该图片 SHALL 不进入 `MessageEvent.media_urls`
- **AND** MessageEvent SHALL 保留历史 `channel_context` 的可解释失败占位

#### Scenario: 历史非图片附件不被误提升

- **WHEN** 历史上下文包含音频、视频、文件或未知引用，但没有对应成功的图片 materialization
- **THEN** 这些历史引用 SHALL NOT 因为存在于 `channel_context` 而被追加为历史图片媒体
- **AND** 当前消息已有的受支持附件映射 SHALL 保持既有行为
