## MODIFIED Requirements

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
- **AND** 系统事件 SHALL 使用 `<event group_nudge> ...` 或 `<event group_member_increase> ...`
  格式
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
