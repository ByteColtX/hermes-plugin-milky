# hermes-message-pipeline Specification

## Purpose

把已通过身份、去重、Gate 和 Will 的 friend/group 消息交接为 Hermes 可消费的一次
MessageEvent，同时严格区分历史上下文、当前正文、系统观察和 trigger 决策后的策略反馈。

## Requirements

### Requirement: friend 和 group 映射到明确 MessageEvent

正常 friend 消息 MUST 映射为 private message，正常 group 消息 MUST 映射为 group message，并保留 sender ID/name、Milky message ID 字符串、`source=milky`、正文、raw、timestamp、reply、已 materialize 的附件路径/MIME、channel_context 和安全 metadata。对于同一次 trigger，`MessageEvent.media_urls`/`media_types` MUST 将 `channel_context` 中历史消息的已 materialize 直接图片与当前 trigger 消息和可见 reply 内容的已 materialize 图片按规定顺序合并；当前 trigger 中已 materialize 的 `record` 音频也 MUST 按其原始出现顺序加入这两个媒体数组，并与对应 MIME 一一配对。相同图片 bytes 只保留当前 batch 中首次出现的代表，hash 不可用时仅按本地路径去重。历史图片按上下文顺序在前，当前图片和音频按当前消息顺序在后，并同步维护两字段一一对应。原始 `media_resource_references` 与 `file_attachment_references` 不得直接写入 `MessageEvent.media_urls`；未 materialize 的远端引用、resource ID 或猜测路径不得写入媒体数组。纯 `record` 当前消息在至少一个音频成功 materialize 时 MUST 映射为 `MessageType.VOICE`，使 Hermes core 能识别其自动 STT 输入；插件不得在此边界实现或配置 STT。会话介绍资料 MUST 通过独立的本地 snapshot store 提供，不得写入 `MessageEvent.text`、`channel_context`、媒体字段或 source 正文。

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

#### Scenario: 当前 record 音频交给 Hermes core

- **WHEN** 当前 trigger 消息包含一个或多个 `record`，且 Hermes audio helper 为其返回有效本地路径和 audio MIME
- **THEN** 每个成功的音频 SHALL 按当前消息的 segment 顺序进入 `MessageEvent.media_urls`
- **AND** `MessageEvent.media_types` SHALL 为每个音频保留对应的 audio MIME
- **AND** 消息只包含 `record` 时 `message_type` SHALL 为 `MessageType.VOICE`
- **AND** 插件 SHALL 不调用或配置 STT provider

#### Scenario: 纯 record 的 Hermes 类型不能标为 AUDIO

- **WHEN** 当前消息没有文本、图片、视频或文件等其他受支持内容，且至少一个 `record` 已成功 materialize
- **THEN** `message_type` SHALL 为 `MessageType.VOICE`
- **AND** Hermes core SHALL 能按既有语音输入判定读取这些 audio `media_urls`
- **AND** 插件 SHALL NOT 将该消息映射为 `MessageType.AUDIO`

#### Scenario: record materialization 失败

- **WHEN** 当前 `record` 缺少可用资源引用、Hermes audio helper 不可用、下载失败或返回无效本地路径
- **THEN** 该 record SHALL 不进入 `MessageEvent.media_urls`
- **AND** 事件 SHALL 保留既有 `[record:NOT SUPPORTED]` 或等价安全降级及分类诊断
- **AND** 插件 SHALL 不伪造 STT 结果、远端 URL 或本地路径

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

### Requirement: pipeline 顺序不可越过门禁和去重

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
- **THEN** 消息 SHALL 只进入既有 wait buffer
- **AND** SHALL 不登记会话 metadata snapshot

### Requirement: 历史上下文和当前正文不得重复

trigger 的当前消息 MUST 只作为本次正文；已经 drain 的历史 wait 消息 MUST 只进入一次性 channel_context；wait 消息 MUST NOT 写入 Hermes transcript。

#### Scenario: 三条消息触发

- **WHEN** 两条历史 wait 消息后收到一条 trigger 消息
- **THEN** Hermes SHALL 收到一次 turn
- **AND** 当前消息 SHALL 不出现在 channel_context
- **AND** 历史两条消息 SHALL 不再次作为正文交给同一次 turn

### Requirement: Agent-facing 文本区分历史上下文和当前消息

当存在 detached 历史时，适配器 MUST 将历史紧凑记录只放入 `MessageEvent.channel_context`，
并使用资源解析及 batch 内容去重完成后的历史正文。所有历史 renderer 出口 MUST 根据同一已
确认 chat namespace 选择模板：group 历史继续使用既有单行 header，且普通消息的真实 Milky
序号 MUST 使用 `msg_seq` 标签；dm 普通历史只使用经过 body 编码的正文，不生成普通消息 header。
当前 trigger 消息 MUST 只进入本次 `MessageEvent.text`；group 当前消息继续使用带 `msg_seq`
的紧凑 header，dm 当前消息 MUST 只使用经过
body 编码的正文，不生成普通消息 header，并使用与其媒体代表一致的图片 basename。对于已经
成功 materialize 并交给 Hermes core 的当前 `record`，适配器 MUST 从当前 `text` 移除插件生成的
`[record:NOT SUPPORTED]` 占位，不得重复渲染 STT 成功文本、STT 失败提示或 STT 未启用提示；
这些提示由 Hermes core 的既有语音处理负责。资源 materialization 失败的当前 `record` MAY 保留
既有安全失败占位。历史 `record` 暂不自动 materialize 为本次 Agent 输入或自动 STT，历史 renderer
SHALL 保留既有 record 占位策略。适配器 MUST NOT 把 `[New message]` 标记或当前消息复制到
`channel_context`；Hermes 已有的 Agent 输入组装语义负责在历史块和当前消息之间加入该标记。
没有历史时，适配器 MUST 保持 `channel_context=None`，并只交付当前消息正文。

#### Scenario: Agent 收到历史和当前消息

- **WHEN** 两条历史消息后收到一条当前 trigger 消息，且历史中有重复内容图片
- **THEN** `channel_context` SHALL 仅为按顺序渲染的历史记录块，并引用首次代表 basename
- **AND** `text` SHALL 仅为当前消息记录，并引用 batch 选择的图片代表 basename
- **AND** Hermes 的有效 Agent 输入 SHALL 在历史块后以空行和 `[New message]` 分隔当前消息
- **AND** 当前消息 SHALL 不出现在 `channel_context`

#### Scenario: 群聊 header 使用 Milky 消息序号标签

- **WHEN** group 历史或当前消息包含已确认的 Milky `message_seq`
- **THEN** Agent-facing 普通消息 header SHALL 使用 `msg_seq <message_seq>`
- **AND** header SHALL NOT 使用 `msg_id` 表示该序号
- **AND** `reply_to` 的值 SHALL 仍表示已确认的被引用消息 `message_seq`，或在已确认自引用时使用既有 `your_previous_msg` 标签

#### Scenario: 当前 record 不重复渲染 core 提示

- **WHEN** 当前 `record` 已成功 materialize，并且 Hermes core 会处理该 MessageEvent 的 `media_urls`
- **THEN** 当前 `MessageEvent.text` SHALL 不包含插件生成的 `[record:NOT SUPPORTED]`
- **AND** 插件 SHALL 不根据 STT 是否配置、是否失败或是否返回空文本自行追加语音提示
- **AND** core 产生的转录文本或语音降级提示 SHALL 成为该语音输入的唯一 core-level 提示来源

#### Scenario: 没有历史时交付当前消息

- **WHEN** trigger 发生时 detached batch 为空
- **THEN** `channel_context` SHALL 为 `None`
- **AND** group 的 `text` SHALL 仍使用包含 `msg_seq` 的当前消息紧凑 header，dm 的 `text` SHALL 只使用经过 body 编码的正文
- **AND** 适配器 SHALL 不伪造历史标题或空的上下文 block

#### Scenario: Agent 收到 dm 历史和当前消息

- **WHEN** 一条或多条 dm 历史消息后收到一条当前 dm trigger 消息
- **THEN** `channel_context` SHALL 只包含按 ingress sequence 排列的历史正文行
- **AND** `channel_context` SHALL NOT 包含历史消息的 sender、uid、`msg_seq` 或 `reply_to` header
- **AND** `text` SHALL 只包含当前 dm 消息的经过 body 编码的正文
- **AND** `text` SHALL NOT 包含当前消息的 sender、uid、`msg_seq` 或 `reply_to` header
- **AND** 当前 trigger SHALL 不出现在 `channel_context`

#### Scenario: Agent 收到无历史的当前 dm 消息

- **WHEN** dm trigger 发生时 detached batch 为空
- **THEN** `channel_context` SHALL 为 `None`
- **AND** `text` SHALL 只包含当前 dm 消息的经过 body 编码的正文
- **AND** `text` SHALL NOT 包含普通消息 header

#### Scenario: dm 当前消息 reply metadata 与 Agent-facing 文本分离

- **WHEN** 当前 dm 消息引用一条消息，且引用目标的 sender、message sequence 或 own-message
  归属已确认
- **THEN** `text` SHALL 只包含当前 dm 正文，不展示 reply header
- **AND** `MessageEvent.reply_to_message_id` SHALL 保留真实引用的 `message_seq`
- **AND** reply author、own-message 和资源解析字段 SHALL 保持已确认值

### Requirement: trigger 决策后反馈 Will

对于通过 Gate 且被 Will 判定为 `trigger` 的普通消息，系统 SHALL 在 trigger 决策完成后立即通知 Will 执行一次 `replyCost`；该通知 SHALL 发生在资源解析、mapper、Hermes `handle_message()` 和最终 QQ 发送之前。每次 trigger SHALL 最多通知一次；资源解析、映射、Hermes 交接失败或后续任务取消 SHALL NOT 撤销已经执行的扣分。Gate deny、wait、命令、temp 和系统事件 SHALL NOT 扣费。系统 SHALL 不等待 Agent 最终 turn 完成。

#### Scenario: trigger 决策完成

- **WHEN** 合法 friend 或 group 消息通过 Gate 且 Will 返回 trigger
- **THEN** Will SHALL 立即执行一次 reply cost 扣除
- **AND** 后续资源解析和 Hermes 交接 SHALL 不影响该次扣分

#### Scenario: Hermes 交接失败

- **WHEN** trigger 决策已经完成，但资源解析、mapper 或 Hermes `handle_message()` 抛出异常
- **THEN** 系统 SHALL 保留已经执行的 reply cost 扣除
- **AND** SHALL NOT 再次扣费或回滚该次扣费

#### Scenario: Gate、wait 和非普通消息

- **WHEN** 消息被 Gate 拒绝、Will 返回 wait，或事件属于命令、temp 或系统事件
- **THEN** 系统 SHALL 不执行 reply cost 扣除
- **AND** SHALL 不因这些事件创建普通 trigger 的扣费记录

### Requirement: temp 和系统事件不进入普通 mapper

temp 消息 MUST 在协议解析边界被忽略并记录 `ignored_temp`，系统事件和未知事件 MUST 使用 observe 路径；它们 SHALL NOT 通过 private/group mapper 触发普通 Agent turn。

#### Scenario: temp 消息

- **WHEN** 收到合法 temp `message_receive`
- **THEN** 系统 SHALL 记录 `ignored_temp`
- **AND** SHALL 不创建 canonical、普通 Hermes MessageEvent 或出站目标
