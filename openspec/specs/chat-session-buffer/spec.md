# chat-session-buffer Specification

## Purpose

为每个聊天提供有界、顺序稳定且不污染 Hermes transcript 的 wait 上下文，使 Will
可以积累待触发消息，并在 trigger 时一次性、安全地交接历史与当前消息。由于 Hermes
公开的平台适配器入口是触发型 turn，wait 消息不能逐条写入 Agent 或 transcript；批量
注入有界历史可以保留触发前的语义上下文，同时不为每条 wait 消息创建独立 Agent turn。

## Requirements

### Requirement: 每个 chat 使用独立 admission 且不维护 Agent 队列

canonical、Gate、wait buffer、Will 和 trigger batch 的交接 MUST 在同一 chat 的短暂 admission 串行边界中按 ingress sequence 完成。trigger batch 脱离该边界后，资源补全、mapper 和 Hermes `handle_message()` 提交 MUST NOT 等待同 chat 的 Agent turn 执行，且插件 MUST NOT 为 Agent turn 维护 ordered handoff、pending 或其他执行队列。不同 chat MAY 并行处理；Hermes Gateway 的 `busy_input_mode` MUST 决定 Agent 忙碌时的 queue、steer、interrupt 和 follow-up 行为。

#### Scenario: 同 chat 并发消息

- **WHEN** 同一 chat 的两条消息并发到达
- **THEN** 它们 SHALL 按该 chat 的到达顺序完成 canonical、Gate、buffer 和 Will 处理
- **AND** SHALL 不产生交叉的 trigger drain

#### Scenario: 不同 chat 并行

- **WHEN** group A 和 dm B 同时处理慢速业务
- **THEN** 一个 chat 的等待 SHALL 不改变另一个 chat 的顺序或状态

#### Scenario: Agent 忙碌时不建立插件执行队列

- **WHEN** 一个 trigger 已交给 Hermes 且 Agent 仍在执行，随后同一 chat 又产生 trigger
- **THEN** 插件 SHALL 释放 admission 并继续处理后续消息，不等待前一个 Agent turn
- **AND** 后续消息 SHALL 交给 Hermes 的 `busy_input_mode` 处理，而不是写入插件侧 Agent 队列

### Requirement: wait buffer 有界且可配置

系统 MUST 为每个 chat 使用独立的有界 wait buffer，默认上限为 20；配置为 0 时 SHALL 不保存历史；超限时 SHALL 丢弃最早消息并提供诊断。

#### Scenario: 缓冲区溢出

- **WHEN** 已有 maxlen 条历史消息又收到一条 wait 消息
- **THEN** buffer SHALL 保留最新 maxlen 条消息
- **AND** SHALL 记录最早消息被丢弃的安全 reason

#### Scenario: 禁用历史

- **WHEN** session buffer size 为 0 且 Will 返回 wait
- **THEN** 当前消息 SHALL 不写入历史 buffer
- **AND** 后续 trigger SHALL 不获得虚假的历史上下文

### Requirement: trigger 先原子 drain 再交接 detached batch

trigger MUST 在同 chat admission 边界中原子清空历史 wait buffer，并将历史构建为 detached batch；当前 trigger 消息 SHALL 只作为本次正文，不得重复放入 channel_context。batch 转交给后续资源补全处理后，admission 边界 MUST 立即释放，不得以 Agent 执行完成作为释放条件。

#### Scenario: 历史与当前消息交接

- **WHEN** buffer 中有两条历史消息且当前消息触发
- **THEN** 两条历史消息 SHALL 只进入一次 channel_context
- **AND** 当前消息 SHALL 只作为本次 MessageEvent 正文
- **AND** buffer SHALL 在 detached batch 交接开始前被清空

#### Scenario: detached 交接失败

- **WHEN** detached batch 交给后续处理失败
- **THEN** 系统 SHALL 只重试同一 batch 或记录不可恢复失败
- **AND** SHALL NOT 无条件把同一批消息重新追加到 buffer

### Requirement: 历史上下文使用稳定紧凑文本格式

detached batch 转换为 `channel_context` 时 MUST 按 ingress sequence 保留其中的普通历史消息
和已登记的 context-only 系统事件。普通消息每条 MUST 使用单行格式：

~~~text
<sender uid <sender_id> msg_id <message_id> reply_to <reply_id>> <body>
~~~

`msg_id` 和 `reply_to` 没有值时 MUST 省略，并保持字段顺序；普通消息 header 和 body 之间
使用一个空格。若被实际渲染的 `reply` 目标的 `sender_id` 等于当前 Bot 的 `self_id`，
Agent-facing header 中的 `reply_to <reply_id>` MUST 改为 `reply_to your_previous_msg`，
不得在同一个 `reply_to` 字段中展示该 Bot 消息的数字 ID。当前消息自身的 `msg_id` MUST
继续展示真实 Milky 消息 ID（若可用）。该展示替换只适用于交给 Agent 的
`MessageEvent.text` 和 `channel_context`；Hermes `MessageEvent.reply_to_message_id`
及其他内部引用字段 MUST 继续保留真实的 Milky `message_seq`。

当被实际渲染的引用目标不是 Bot，或无法确认其 `sender_id` 时，系统 MUST 不使用
`your_previous_msg`；有可用目标 ID 时继续展示 `reply_to <reply_id>`，没有目标 ID 时省略
该字段。系统 MUST NOT 从 sender name、正文、嵌套 mention 或其他未被渲染的 reply 目标
推断自引用。

系统事件 MUST 使用 `<event <event_type>> <body>` 格式，不得伪装成普通消息或 segment
placeholder。普通消息的 `body` MUST 来自规范化消息内容和本 change 定义的结构化占位符；
系统事件的 body MUST 来自事件字段的可读渲染。普通消息和系统事件之间 MUST 使用一个换行
拼接；不得添加额外历史标题。

当前 trigger 消息 MUST 只进入本次 `MessageEvent.text`，不得进入 `channel_context`；没有
历史消息和待注入系统事件时，`channel_context` MUST 为 `None`，而不是空字符串。

header 中的非可信值 MUST 将尖括号、反斜杠、回车和换行编码为不会改变记录边界的字面量；
body 中的回车和换行也 MUST 编码为字面量 `\\n`。上下文 MUST NOT 包含 timestamp、dedup key、
认证信息或插件本地媒体路径。

#### Scenario: 当前消息引用 Bot 时使用 Agent-facing 自引用文案

- **WHEN** 当前 trigger 消息包含 `reply`，且被实际渲染的 `reply.data.sender_id` 等于当前
  Bot 的 `self_id`
- **THEN** `MessageEvent.text` 的 header SHALL 使用 `reply_to your_previous_msg`
- **AND** 该 header SHALL 保留当前消息真实的 `msg_id`（若可用）
- **AND** Hermes `MessageEvent.reply_to_message_id` SHALL 仍为被引用消息的真实
  `message_seq`

#### Scenario: 历史消息引用 Bot 时使用相同文案

- **WHEN** wait 历史消息包含引用 Bot 的 `reply`，并在下一次 trigger 中进入
  `channel_context`
- **THEN** 对应历史记录 SHALL 使用 `reply_to your_previous_msg`
- **AND** 当前 trigger SHALL 不因该历史记录被复制进 `channel_context`

#### Scenario: 引用他人时保留真实 reply ID

- **WHEN** 被实际渲染的 `reply.data.sender_id` 与当前 Bot 的 `self_id` 不一致，且目标 ID 可用
- **THEN** Agent-facing header SHALL 继续使用 `reply_to <reply_id>`
- **AND** 系统 SHALL NOT 使用 `your_previous_msg`
- **AND** Hermes 内部引用字段 SHALL 继续使用真实目标 ID

#### Scenario: 引用发送者未知时不猜测 Bot

- **WHEN** `reply.data.sender_id` 缺失、非法或无法确认，且引用目标 ID可用
- **THEN** Agent-facing header SHALL 使用真实 `reply_to <reply_id>`
- **AND** 系统 SHALL NOT 根据 sender name、正文或嵌套 mention 改写为 `your_previous_msg`
- **AND** 既有 malformed 或安全诊断 SHALL 保持有效

#### Scenario: 多个 reply 只依据实际渲染目标

- **WHEN** 一条消息包含多个 `reply`，而 header 选择展示其中一个目标的 `reply_id`
- **THEN** 自引用文案 SHALL 只由该被展示目标的 `sender_id` 决定
- **AND** 其他未被展示的 Bot reply SHALL NOT 将他人目标的 `reply_to <reply_id>` 改写为
  `your_previous_msg`

#### Scenario: 没有引用时不增加自引用字段

- **WHEN** 消息不包含可用 `reply` 目标
- **THEN** header SHALL NOT 添加 `reply_to your_previous_msg`
- **AND** 现有 `msg_id` 缺省、省略和转义规则 SHALL 保持不变

#### Scenario: 普通历史和当前消息分离

- **WHEN** detached batch 包含两条 wait 普通消息，当前 trigger 另有一条消息
- **THEN** `channel_context` SHALL 只包含两条历史的单行记录
- **AND** 每条记录 SHALL 使用 `<sender uid ... msg_id ... reply_to ...> body` 格式
- **AND** 当前 trigger 消息 SHALL 只出现在 `MessageEvent.text`

#### Scenario: 多条历史消息按 FIFO 拼接

- **WHEN** detached batch 依次包含两条历史普通消息
- **THEN** `channel_context` SHALL 按最早到最新的 ingress sequence 形成单行记录
- **AND** 每条记录 SHALL 包含可用的 sender、uid、msg_id 和 reply_to 字段
- **AND** SHALL 不包含当前 trigger 消息或额外群 ID

#### Scenario: 系统事件与普通历史按顺序合并

- **WHEN** 一个 chat 先后产生普通 wait 消息、`group_nudge` 和 `group_member_increase`
- **THEN** 下次 trigger 的 `channel_context` SHALL 按 ingress sequence 混合排列这些记录
- **AND** 系统事件 SHALL 使用 `<event group_nudge> ...` 或 `<event group_member_increase> ...` 格式
- **AND** 系统事件 SHALL NOT 形成独立 Hermes turn

#### Scenario: 没有上下文

- **WHEN** trigger 发生时没有历史 wait 消息和待注入系统事件
- **THEN** `channel_context` SHALL 为 `None`
- **AND** 当前消息 SHALL 仍使用单行 header 和正文格式交给 Hermes

#### Scenario: 上下文包含边界字符

- **WHEN** sender name 或 body 含有尖括号、反斜杠或换行
- **THEN** 这些字符 SHALL 被编码而不伪造新的 context record
- **AND** 原始 payload SHALL NOT 被直接拼接到上下文

#### Scenario: 上下文为空或包含非可信文本

- **WHEN** detached batch 为空，或 sender name/body 含有右方括号、反斜杠、尖括号或换行
- **THEN** 空 batch 的 `channel_context` SHALL 为 `None`
- **AND** 非可信字符 SHALL 按规定编码而不改变记录边界
- **AND** 原始 payload、认证信息和插件本地媒体路径 SHALL NOT 被直接拼接

### Requirement: wait 不写入 Hermes transcript

Will 返回 wait 的消息 MUST 只保存在插件拥有的有界 buffer 中，直到被丢弃、drain 或明确失败；wait 阶段 SHALL NOT 调用 Hermes Agent 或写入 Hermes transcript。

#### Scenario: wait 消息

- **WHEN** 一条通过 Gate 的消息得到 wait 决策
- **THEN** Hermes SHALL 不收到该消息的 turn
- **AND** 插件 buffer SHALL 按配置保存或明确丢弃它

#### Scenario: Hermes 忙碌不扩大插件锁

- **WHEN** 当前 trigger 交给 Hermes 后 Agent 仍在执行
- **THEN** 插件 SHALL 释放该 chat 的 admission 边界
- **AND** 后续消息 SHALL 由 Hermes 的 `busy_input_mode`、busy/follow-up、pending/FIFO、interrupt 或 steer 语义处理，而不是在插件中等待 Agent 完成或复制 Agent 队列

### Requirement: context-only 系统事件使用独立有界缓冲

系统 MUST 为每个可识别 chat 维护独立、有界、可丢失的 context-only 事件缓冲。该缓冲与
普通 wait buffer 分离，不得进入普通 canonical、Will 或 reply cost 状态。登记的系统事件
只有在后续同 chat trigger 时作为 `channel_context` 注入一次；注入后 MUST 原子清除，溢出时
MUST 丢弃最早事件并记录安全诊断。系统事件无可确认 chat key 时 MUST 只观察，不得创建
全局或默认 chat 的上下文。字段完整的 `message_recall` MUST 按其 `message_scene` 和
`peer_id` 写入对应 `dm:` 或 `group:` chat；它与其他 context-only 事件共享相同的顺序、
容量、一次性消费和失败边界。

#### Scenario: 系统事件等待下一次 trigger

- **WHEN** `group_nudge`、群成员变更事件或字段完整的 `message_recall` 在没有 trigger 的时期到达
- **THEN** 事件 SHALL 进入对应 group chat 的 context-only 缓冲
- **AND** SHALL 不调用 Hermes、Will 或普通 wait buffer
- **AND** 下一次该 chat trigger SHALL 消费这些事件一次

#### Scenario: 撤回事件按场景隔离

- **WHEN** 一个 `message_recall` 的 `message_scene` 为 `friend` 或 `group` 且 `peer_id` 合法
- **THEN** 系统 SHALL 分别将其写入 `dm:<peer_id>` 或 `group:<peer_id>` 的 context-only 缓冲
- **AND** SHALL 不因相同数字的好友号与群号把事件写入另一种场景

#### Scenario: 系统事件缓冲与普通消息按 ingress 顺序合并

- **WHEN** 一个 chat 先后产生普通 wait 消息、`message_recall` 和 `group_nudge`
- **THEN** 下一次 trigger 的 `channel_context` SHALL 按 ingress sequence 混合排列这些记录
- **AND** 撤回事件 SHALL 使用 `<event message_recall> ...` 格式
- **AND** 所有系统事件 SHALL NOT 形成独立 Hermes turn

#### Scenario: 系统事件缓冲溢出

- **WHEN** context-only 缓冲达到上限后又收到新事件
- **THEN** 系统 SHALL 保留最新上限数量的事件
- **AND** SHALL 丢弃最早事件并记录不含正文的溢出诊断

#### Scenario: 无法建立 chat key

- **WHEN** 系统事件缺少或包含非法群号/好友号，或 `message_recall` 的场景与 `peer_id` 无法确认
- **THEN** 系统 SHALL 保持 observe-only
- **AND** SHALL NOT 写入任何 chat context、普通 buffer 或 Hermes transcript

#### Scenario: 撤回事件交接失败

- **WHEN** 包含 `message_recall` 的 detached context batch 在 trigger 交接时失败
- **THEN** 系统 SHALL 只重试同一 batch 或记录不可恢复失败
- **AND** SHALL NOT 自动重复追加撤回事件或把其升级为独立 Agent turn
